"""Pure helpers on the polled data (no Home Assistant objects, easy to test)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo

from .api.models import Day, Event, MealEntry, Message, PendingReply


def _d(value: str | None) -> date | None:
    """Parse the date part of an ISO string. Unparsable or missing values give None."""
    try:
        return datetime.fromisoformat(value).date() if value else None
    except ValueError:
        return None


def closure_on(events: list[Event], day: date) -> Event | None:
    """The closure day or public holiday that covers `day`, if any."""
    for event in events:
        if not (event.get("istSchliesstag") or event.get("istFeiertag")):
            continue
        start = _d(event.get("startdatum"))
        end = _d(event.get("enddatum")) or start  # open ended entries count for their first day
        if start and end and start <= day <= end:
            return event
    return None


def is_closed_on(events: list[Event], day: date) -> bool:
    """True if a closure day or public holiday covers `day`."""
    return closure_on(events, day) is not None


def meals_on(days: list[Day], day: date) -> list[MealEntry]:
    """Flatten the plan for one day: one entry per meal variant."""
    out: list[MealEntry] = []
    for entry in days:
        if _d(entry.get("datum")) != day:
            continue
        for art in entry.get("mahlzeitArten", []):
            for var in art.get("varianten", []):
                order = var.get("bestellung")
                out.append(
                    MealEntry(
                        art=art.get("name"),
                        variante=var.get("name"),
                        preis=var.get("preis"),
                        bestellt=bool(order and not order.get("istAbbestellt")),
                        bestellbar=bool(var.get("istBestellbar")),
                        abbestellbar=bool(var.get("istAbbestellbar")),
                    )
                )
    return out


@dataclass(frozen=True)
class DeadlineRule:
    """A Kita's order deadline, e.g. "1 day before the meal at 11:00" (days_before=1, at=11:00)."""

    days_before: int
    at: time
    workdays_only: bool = False


def deadline_for(day: date, rule: DeadlineRule, tz: tzinfo) -> datetime:
    """The moment ordering for `day` closes. With `workdays_only`, Saturdays and Sundays are not counted."""
    target = day
    if rule.workdays_only:
        remaining = rule.days_before
        while remaining > 0:
            target -= timedelta(days=1)
            if target.weekday() < 5:
                remaining -= 1
    else:
        target = day - timedelta(days=rule.days_before)
    return datetime.combine(target, rule.at, tzinfo=tz)


ORDER_STATES = ["ordered", "open", "missed", "not_offered"]


def order_status(
    meals: list[MealEntry], deadline: datetime | None = None, now: datetime | None = None
) -> str:
    """Where an order stands for one day.

    ordered      something is ordered
    open         meals are offered, nothing is ordered and ordering is still possible
    missed       meals are offered, nothing is ordered and ordering is no longer possible (deadline over)
    not_offered  there is no meal that day

    "Possible" is what KitaPlus reports per meal. If the Kita's deadline is known, the status also turns to
    "missed" at that very moment, even when the last update is older.
    """
    if not meals:
        return "not_offered"
    if any(m["bestellt"] for m in meals):
        return "ordered"
    if deadline is not None and now is not None and now >= deadline:
        return "missed"
    return "open" if any(m["bestellbar"] for m in meals) else "missed"


@dataclass(frozen=True)
class OpenOrder:
    """A day that can still be ordered, with the moment ordering closes when the Kita's rule is known."""

    day: date
    deadline: datetime | None


def open_orders(days: list[Day], rule: DeadlineRule | None, now: datetime) -> list[OpenOrder]:
    """Days from today on with meals offered, nothing ordered and ordering still possible, soonest first."""
    found: list[OpenOrder] = []
    for entry in days:
        day = _d(entry.get("datum"))
        if day is None or day < now.date():
            continue
        deadline = deadline_for(day, rule, now.tzinfo or UTC) if rule else None
        if order_status(meals_on([entry], day), deadline, now) == "open":
            found.append(OpenOrder(day, deadline))
    return sorted(found, key=lambda o: o.day)


def pending_replies(messages: list[Message]) -> list[PendingReply]:
    """Messages that need a confirmation and have not been answered yet."""
    out: list[PendingReply] = []
    for msg in messages:
        note = msg.get("nachricht") or {}
        if note.get("istBestaetigungspflichtig") and not msg.get("istBeantwortet"):
            out.append(
                PendingReply(id=msg.get("id"), titel=note.get("titel"), frist=note.get("rueckmeldefrist"))
            )
    return out
