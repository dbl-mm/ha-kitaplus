"""Entity states, attributes, calendars and the midnight refresh, at fixed times."""

from contextlib import ExitStack
from datetime import datetime, timedelta

import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.kitaplus.calendar import _parse, _to_event

from .common import make_entry, setup_integration
from .conftest import load


@pytest.fixture
def stack():
    with ExitStack() as s:
        yield s


def at(freezer, text: str) -> None:
    """Freeze at a local time of the Home Assistant test time zone."""
    freezer.move_to(dt_util.parse_datetime(text).replace(tzinfo=dt_util.get_default_time_zone()))


async def test_meals_today_and_tomorrow_are_ordered(hass, stack, freezer) -> None:
    at(freezer, "2026-06-13T10:00:00")
    await setup_integration(hass, stack)
    today = hass.states.get("sensor.vorname_1_meal_today")
    tomorrow = hass.states.get("sensor.vorname_1_meal_tomorrow")
    assert today.state not in ("unknown", "Nothing ordered")
    assert tomorrow.state not in ("unknown", "Nothing ordered")
    assert today.attributes["offered"][0]["bestellt"] is True
    assert hass.states.get("binary_sensor.vorname_1_nothing_ordered_tomorrow").state == "off"


async def test_nothing_ordered_tomorrow_is_reported_as_problem(hass, stack, freezer) -> None:
    at(freezer, "2026-06-14T10:00:00")  # tomorrow = 2026-06-15: offered, but not ordered
    await setup_integration(hass, stack)
    assert hass.states.get("sensor.vorname_1_meal_tomorrow").state == "Nothing ordered"
    problem = hass.states.get("binary_sensor.vorname_1_nothing_ordered_tomorrow")
    assert problem.state == "on"
    assert "can_still_order" in problem.attributes


async def test_day_without_meals_is_unknown_not_a_problem(hass, stack, freezer) -> None:
    at(freezer, "2026-06-15T10:00:00")  # tomorrow = 2026-06-16: nothing offered
    await setup_integration(hass, stack)
    assert hass.states.get("sensor.vorname_1_meal_tomorrow").state == "unknown"
    assert hass.states.get("binary_sensor.vorname_1_nothing_ordered_tomorrow").state == "off"


async def test_closure_days_drive_the_closed_sensors(hass, stack, freezer) -> None:
    at(freezer, "2026-06-13T10:00:00")
    closure = {
        "id": 1,
        "name": "Schließtag",
        "istSchliesstag": True,
        "istFeiertag": False,
        "startdatum": "2026-06-14T00:00:00",
        "enddatum": "2026-06-14T23:59:00",
    }
    await setup_integration(hass, stack, async_get_events=[closure])
    assert hass.states.get("binary_sensor.kitaplus_closed_today").state == "off"
    assert hass.states.get("binary_sensor.kitaplus_closed_tomorrow").state == "on"


async def test_midnight_moves_today_and_tomorrow_without_a_new_poll(hass, stack, freezer) -> None:
    at(freezer, "2026-06-14T23:59:00")
    closure = {
        "id": 1,
        "istSchliesstag": True,
        "startdatum": "2026-06-15T00:00:00",
        "enddatum": "2026-06-15T23:59:00",
    }
    await setup_integration(hass, stack, async_get_events=[closure])
    assert hass.states.get("binary_sensor.kitaplus_closed_today").state == "off"
    assert hass.states.get("binary_sensor.kitaplus_closed_tomorrow").state == "on"

    freezer.tick(timedelta(minutes=2))  # 00:01 on the 15th, no coordinator refresh happened
    async_fire_time_changed(hass, dt_util.now() + timedelta(seconds=10))
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.kitaplus_closed_today").state == "on"


async def test_balance_board_mailbox_and_pending_replies(hass, stack, freezer) -> None:
    at(freezer, "2026-06-13T10:00:00")
    pending = [
        {
            "id": 7,
            "istBeantwortet": False,
            "abrufDatum": "2026-06-12T08:00:00",
            "nachricht": {
                "titel": "Bitte bestätigen",
                "istBestaetigungspflichtig": True,
                "rueckmeldefrist": "2026-06-20T00:00:00",
            },
        }
    ]
    await setup_integration(hass, stack, async_get_messages=pending)
    assert float(hass.states.get("sensor.kitaplus_meal_account_balance").state) == 25.0
    assert hass.states.get("sensor.kitaplus_mailbox").state == "1"
    assert hass.states.get("sensor.kitaplus_pending_replies").state == "1"
    assert hass.states.get("sensor.kitaplus_pending_replies").attributes["messages"][0]["frist"]
    board = hass.states.get("sensor.kitaplus_bulletin_board")
    assert board.state and len(board.attributes["posts"]) == 5


async def test_balance_accepts_decimal_comma_and_skips_inactive_accounts(hass, stack) -> None:
    accounts = [
        {"id": 1, "istAktiv": True, "kontostand": "12,50"},
        {"id": 2, "istAktiv": False, "kontostand": "99.00"},
        {"id": 3, "istAktiv": True, "kontostand": "kaputt"},
    ]
    await setup_integration(hass, stack, async_get_accounts=accounts)
    balances = [s for s in hass.states.async_all("sensor") if "balance" in s.entity_id]
    assert sorted(s.state for s in balances) == ["12.5", "unknown"]


async def test_calendars_show_appointments_closures_and_ordered_meals(hass, stack, freezer) -> None:
    at(freezer, "2026-06-13T10:00:00")
    closure = {
        "id": 99,
        "name": "Brückentag",
        "istSchliesstag": True,
        "istFeiertag": False,
        "startdatum": "2026-06-19T00:00:00",
        "enddatum": None,  # open ended: shown for its first day, must not crash
    }
    await setup_integration(hass, stack, async_get_events=load("termine")["data"] + [closure])
    start = dt_util.now()
    window = {"start_date_time": start.isoformat(), "end_date_time": (start + timedelta(days=10)).isoformat()}

    async def events(entity_id):
        result = await hass.services.async_call(
            "calendar", "get_events", {"entity_id": entity_id, **window}, blocking=True, return_response=True
        )
        return result[entity_id]["events"]

    assert len(await events("calendar.kitaplus_appointments")) >= 1
    assert [e["summary"] for e in await events("calendar.kitaplus_closures")] == ["Brückentag"]
    assert len(await events("calendar.vorname_1_ordered_meals")) >= 2
    assert hass.states.get("calendar.kitaplus_appointments").state in ("on", "off")


def test_all_day_and_timed_events_are_told_apart() -> None:
    tz = dt_util.get_default_time_zone()
    day = datetime(2026, 6, 14, tzinfo=tz)
    all_day = _to_event("x", day, day.replace(hour=23, minute=59))
    assert (all_day.start, all_day.end) == (day.date(), (day + timedelta(days=1)).date())
    same_midnight = _to_event("x", day, day)  # 00:00 to 00:00 on the same day
    assert same_midnight.end == (day + timedelta(days=1)).date()
    next_midnight = _to_event("x", day, day + timedelta(days=2))
    assert next_midnight.end == (day + timedelta(days=2)).date()
    timed = _to_event("x", day.replace(hour=16), day.replace(hour=18))
    assert isinstance(timed.start, datetime) and timed.description is None
    zero_length = _to_event("x", day.replace(hour=16), day.replace(hour=16))
    assert zero_length.end > zero_length.start


def test_parse_handles_missing_dates_offsets_and_garbage() -> None:
    assert _parse(None) is None
    assert _parse("") is None
    assert _parse("garbage") is None
    assert _parse("2026-06-14").date().isoformat() == "2026-06-14"  # date only
    assert _parse("2026-06-14T10:00:00").tzinfo is not None
    assert _parse("2026-06-14T10:00:00+00:00").utcoffset() == timedelta(0)  # a given offset is kept


def test_entry_helper_has_no_password() -> None:
    assert "password" not in make_entry().data
