"""Pure helpers on the polled data (no Home Assistant objects, easy to test)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo

from .api.models import Child, Day, Event, MealEntry, Message, OrderRules, PendingReply, UpcomingEntry


def _d(value: str | None) -> date | None:
    """Parse the date part of an ISO string. Unparsable or missing values give None."""
    try:
        return datetime.fromisoformat(value).date() if value else None
    except ValueError:
        return None


def child_name(child: Child) -> str:
    """The first name as KitaPlus gives it, without stray spaces; "Kind" when there is none."""
    return (child.get("vorname") or "").strip() or "Kind"


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
    """A Kita's order deadline, e.g. "1 day before the meal at 11:00" (days_before=1, at=11:00).

    With `shift_to_workday` a deadline that falls on a Saturday, Sunday or public holiday moves back to the
    previous workday. KitaPlus says so in its help text ("auf den vorhergehenden Werktag verschoben").
    """

    days_before: int
    at: time
    shift_to_workday: bool = False


def deadline_for(
    day: date, rule: DeadlineRule, tz: tzinfo, holidays: frozenset[date] = frozenset()
) -> datetime:
    """The moment ordering for `day` closes: `days_before` calendar days earlier, moved back if required."""
    target = day - timedelta(days=rule.days_before)
    if rule.shift_to_workday:
        while target.weekday() >= 5 or target in holidays:
            target -= timedelta(days=1)
    return datetime.combine(target, rule.at, tzinfo=tz)


def holiday_dates(events: list[Event]) -> frozenset[date]:
    """Public holidays among the appointments. Kita closure days are not holidays and do not count."""
    found: set[date] = set()
    for event in events:
        if not event.get("istFeiertag"):
            continue
        start = _d(event.get("startdatum"))
        end = _d(event.get("enddatum")) or start
        if start and end:
            found.update(
                start + timedelta(days=i)
                for i in range((min(end, start + timedelta(days=30)) - start).days + 1)
            )
    return frozenset(found)


_DEADLINE_TEXT = re.compile(
    r"(\d{1,2})\s*Tag(?:e|en)?\s+vor\s+Essenausgabe\s+um\s+(\d{1,2}):(\d{2})\s*Uhr", re.I
)


def parse_deadline_text(text: str | None) -> tuple[int, time] | None:
    """Days before and time of day from "... 1 Tage vor Essenausgabe um 11:00 Uhr". Anything else gives None.

    Other wordings are not guessed: without a rule the status relies on what KitaPlus reports per meal.
    """
    match = _DEADLINE_TEXT.search(text or "")
    if match is None:
        return None
    days, hour, minute = int(match[1]), int(match[2]), int(match[3])
    if hour > 23 or minute > 59:
        return None
    return days, time(hour, minute)


def shifts_to_workday(text: str | None) -> bool:
    """True if the Kita says a deadline on a weekend or holiday moves to the previous workday."""
    return bool(re.search(r"vorhergehenden\s+Werktag", text or "", re.I))


def rule_from_texts(rules: list[OrderRules]) -> DeadlineRule | None:
    """The deadline all facilities agree on. Different or unreadable texts give None, nothing is guessed."""
    found = set()
    for entry in rules:
        parsed = parse_deadline_text(entry.get("bestellfristEinzelText"))
        if parsed is None:
            return None
        found.add(DeadlineRule(parsed[0], parsed[1], shifts_to_workday(entry.get("fristSonstigesText"))))
    return found.pop() if len(found) == 1 else None


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


def open_orders(
    days: list[Day], rule: DeadlineRule | None, now: datetime, holidays: frozenset[date] = frozenset()
) -> list[OpenOrder]:
    """Days from today on with meals offered, nothing ordered and ordering still possible, soonest first."""
    found: list[OpenOrder] = []
    for entry in days:
        day = _d(entry.get("datum"))
        if day is None or day < now.date():
            continue
        deadline = deadline_for(day, rule, now.tzinfo or UTC, holidays) if rule else None
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


def _dt(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def upcoming_entries(events: list[Event], today: date, limit: int = 5) -> list[UpcomingEntry]:
    """The next appointments and closure days from today on, soonest first.

    A multi-day entry that is already running is listed with today's date. Entries without a usable start
    are skipped.
    """
    found: list[tuple[date, time, UpcomingEntry]] = []
    for event in events:
        start = _dt(event.get("startdatum"))
        if start is None:
            continue
        end = _dt(event.get("enddatum")) or start
        if end.date() < today:
            continue
        all_day = start.time() == time.min and end.time() in (time.min, time(23, 59))
        shown = max(start.date(), today)
        found.append(
            (
                shown,
                time.min if all_day else start.time(),
                UpcomingEntry(
                    datum=shown.isoformat(),
                    zeit=None if all_day else start.strftime("%H:%M"),
                    titel=event.get("name") or "",
                    schliesstag=bool(event.get("istSchliesstag") or event.get("istFeiertag")),
                ),
            )
        )
    found.sort(key=lambda item: (item[0], item[1]))
    return [entry for _, _, entry in found[:limit]]


_MARKUP = re.compile(r"[<>\[\]()*_`#&]")


def plain_text(message: str | None) -> str:
    """A server message as plain text: Home Assistant shows it as Markdown, and the text is not ours."""
    return " ".join(_MARKUP.sub("", message or "").split())[:200]
