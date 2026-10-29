"""Calendars for KitaPlus: Termine, Schliesstage and ordered meals."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import KitaPlusConfigEntry
from .coordinator import KitaPlusCoordinator
from .entity import KitaPlusChildEntity, KitaPlusEntity


def _parse(value: str | None) -> datetime | None:
    """KitaPlus sends local times without an offset. Unparsable values give None."""
    if not value:
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is None and (day := dt_util.parse_date(value)):
        parsed = datetime.combine(day, datetime.min.time())
    if parsed is None:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt_util.get_default_time_zone())


def _to_event(summary: str, start: datetime, end: datetime, description: str | None = None) -> CalendarEvent:
    """Midnight to midnight/23:59 spans become all-day events."""
    if start.time() == datetime.min.time() and end.time() in (
        datetime.min.time(),
        datetime(1, 1, 1, 23, 59).time(),
    ):
        return CalendarEvent(
            summary=summary,
            start=start.date(),
            end=end.date() + timedelta(days=1)
            if end.time() != datetime.min.time()
            else max(end.date(), start.date() + timedelta(days=1)),
            description=description,
        )
    return CalendarEvent(
        summary=summary, start=start, end=max(end, start + timedelta(minutes=1)), description=description
    )


def _in_range(event: CalendarEvent, start: datetime, end: datetime) -> bool:
    def as_dt(v: date | datetime) -> datetime:
        return v if isinstance(v, datetime) else dt_util.start_of_local_day(v)

    return as_dt(event.end) > start and as_dt(event.start) < end


class _EventCalendar(CalendarEntity):
    """Common event lookup."""

    def _events(self) -> list[CalendarEvent]:
        raise NotImplementedError

    @property
    def event(self) -> CalendarEvent | None:
        now = dt_util.now()
        upcoming = sorted(
            (e for e in self._events() if _in_range(e, now, now + timedelta(days=366))),
            key=lambda e: (
                dt_util.start_of_local_day(e.start) if not isinstance(e.start, datetime) else e.start
            ),
        )
        return upcoming[0] if upcoming else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [e for e in self._events() if _in_range(e, start_date, end_date)]


class AppointmentsCalendar(KitaPlusEntity, _EventCalendar):
    _attr_translation_key = "appointments"
    _closures = False

    def __init__(self, coordinator: KitaPlusCoordinator, closures: bool) -> None:
        super().__init__(coordinator)
        self._closures = closures
        self._attr_translation_key = "closures" if closures else "appointments"
        self._attr_unique_id = f"{self._entry_id}_calendar_{'closures' if closures else 'appointments'}"

    def _events(self) -> list[CalendarEvent]:
        out = []
        for raw in self.coordinator.data.events:
            is_closure = bool(raw.get("istSchliesstag") or raw.get("istFeiertag"))
            start = _parse(raw.get("startdatum"))
            if start is None or is_closure != self._closures:
                continue
            end = _parse(raw.get("enddatum")) or start  # open ended entries show their first day
            out.append(_to_event(raw.get("name") or "", start, end))
        return out


class MealsCalendar(KitaPlusChildEntity, _EventCalendar):
    """Orders (not cancelled) as all-day events."""

    _attr_translation_key = "meals"

    def __init__(self, coordinator: KitaPlusCoordinator, child: dict[str, Any]) -> None:
        super().__init__(coordinator, child)
        self._attr_unique_id = f"{self._entry_id}_{self._child_id}_calendar_meals"

    def _events(self) -> list[CalendarEvent]:
        out = []
        for day in self.coordinator.data.meals.get(self._child_id, []):
            start = _parse(day.get("datum"))
            if start is None:
                continue
            for art in day.get("mahlzeitArten", []):
                for var in art.get("varianten", []):
                    order = var.get("bestellung")
                    if order and not order.get("istAbbestellt"):
                        out.append(
                            CalendarEvent(
                                summary=var.get("name") or art.get("name") or "",
                                start=start.date(),
                                end=start.date() + timedelta(days=1),
                                description=art.get("name"),
                            )
                        )
        return out


async def async_setup_entry(
    hass: HomeAssistant, entry: KitaPlusConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[CalendarEntity] = [
        AppointmentsCalendar(coordinator, closures=False),
        AppointmentsCalendar(coordinator, closures=True),
    ]
    entities += [
        MealsCalendar(coordinator, c) for c in coordinator.data.children if c["id"] in coordinator.data.meals
    ]
    async_add_entities(entities)
