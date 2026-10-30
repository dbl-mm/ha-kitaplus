"""Entity states, attributes, calendars and the midnight refresh, at fixed times."""

from contextlib import ExitStack
from datetime import datetime, timedelta

import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.kitaplus.calendar import _parse, _to_event
from custom_components.kitaplus.helpers import pending_replies

from .common import make_entry, meal_day, setup_integration
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


async def test_an_ordered_meal_without_any_name_does_not_break_the_sensor(hass, stack, freezer) -> None:
    at(freezer, "2026-06-13T10:00:00")
    day = {
        "datum": "2026-06-13T00:00:00",
        "mahlzeitArten": [
            {"name": None, "varianten": [{"name": None, "bestellung": {"istAbbestellt": False}}]}
        ],
    }
    await setup_integration(hass, stack, async_get_meals=[day])
    assert (
        hass.states.get("sensor.vorname_1_meal_today").state == "Ordered"  # ordered, only the name is missing
    )  # nothing to show by name


async def test_closed_sensor_tells_the_reason_for_notifications(hass, stack, freezer) -> None:
    at(freezer, "2026-06-13T10:00:00")
    closure = {
        "id": 1,
        "name": "Brückentag",
        "istSchliesstag": True,
        "startdatum": "2026-06-14T00:00:00",
        "enddatum": "2026-06-14T23:59:00",
    }
    await setup_integration(hass, stack, async_get_events=[closure])
    assert hass.states.get("binary_sensor.kitaplus_closed_tomorrow").attributes["reason"] == "Brückentag"
    assert hass.states.get("binary_sensor.kitaplus_closed_today").attributes["reason"] is None


STATUS_TODAY = "sensor.vorname_1_order_status_today"
STATUS_TOMORROW = "sensor.vorname_1_order_status_tomorrow"


async def test_order_status_has_four_clear_states(hass, stack, freezer) -> None:
    at(freezer, "2026-06-14T10:00:00")
    meals = [
        meal_day("2026-06-14", ordered=True, orderable=False),  # today: ordered
        meal_day("2026-06-15", ordered=False, orderable=True),  # tomorrow: nothing ordered, still possible
    ]
    await setup_integration(hass, stack, async_get_meals=meals)
    assert hass.states.get(STATUS_TODAY).state == "ordered"
    assert hass.states.get(STATUS_TOMORROW).state == "open"
    assert hass.states.get(STATUS_TOMORROW).attributes["options"] == [
        "ordered",
        "open",
        "missed",
        "not_offered",
    ]


async def test_order_status_tells_a_missed_deadline_from_an_open_order(hass, stack, freezer) -> None:
    at(freezer, "2026-06-14T10:00:00")
    meals = [meal_day("2026-06-14", ordered=False, orderable=False)]  # KitaPlus no longer accepts an order
    await setup_integration(hass, stack, async_get_meals=meals)
    assert hass.states.get(STATUS_TODAY).state == "missed"
    assert hass.states.get(STATUS_TOMORROW).state == "not_offered"  # nothing offered on the 15th


async def test_order_status_follows_the_deadline_of_the_next_poll(hass, stack, freezer) -> None:
    """KitaPlus flips `istBestellbar` when the deadline passes; the status follows with the next update."""
    at(freezer, "2026-06-14T08:00:00")
    entry = await setup_integration(
        hass, stack, async_get_meals=[meal_day("2026-06-14", ordered=False, orderable=True)]
    )
    assert hass.states.get(STATUS_TODAY).state == "open"
    from unittest.mock import patch

    from .common import CLIENT

    stack.enter_context(
        patch(
            f"{CLIENT}.async_get_meals", return_value=[meal_day("2026-06-14", ordered=False, orderable=False)]
        )
    )
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(STATUS_TODAY).state == "missed"


async def test_order_status_moves_to_the_next_day_at_midnight(hass, stack, freezer) -> None:
    at(freezer, "2026-06-14T23:59:00")
    meals = [
        meal_day("2026-06-14", ordered=True, orderable=False),
        meal_day("2026-06-15", ordered=False, orderable=True),
    ]
    await setup_integration(hass, stack, async_get_meals=meals)
    assert (hass.states.get(STATUS_TODAY).state, hass.states.get(STATUS_TOMORROW).state) == (
        "ordered",
        "open",
    )
    freezer.tick(timedelta(minutes=2))
    async_fire_time_changed(hass, dt_util.now() + timedelta(seconds=10))
    await hass.async_block_till_done()
    assert hass.states.get(STATUS_TODAY).state == "open"  # the 15th is "today" now, still not ordered


async def test_order_status_names_the_meal_for_compact_tiles(hass, stack, freezer) -> None:
    from unittest.mock import patch

    from .common import CLIENT

    at(freezer, "2026-06-14T10:00:00")
    ordered = meal_day("2026-06-14", ordered=True, orderable=False)
    open_day = meal_day("2026-06-15", ordered=False, orderable=True)
    open_day["mahlzeitArten"][0]["varianten"][0]["name"] = "Pasta"
    entry = await setup_integration(hass, stack, async_get_meals=[ordered, open_day])
    assert hass.states.get(STATUS_TODAY).attributes["meal"] == "Menü"
    assert hass.states.get(STATUS_TOMORROW).attributes["meal"] == "Pasta", "an open day names what is offered"

    stack.enter_context(patch(f"{CLIENT}.async_get_meals", return_value=[]))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(STATUS_TODAY).attributes["meal"] is None, "no meal, no name"


async def test_upcoming_sensor_lists_the_next_entries_and_names_the_first(hass, stack, freezer) -> None:
    at(freezer, "2026-10-29T10:00:00")
    events = [
        {
            "id": 1,
            "name": "Elternabend",
            "startdatum": "2026-11-02T19:30:00",
            "enddatum": "2026-11-02T21:00:00",
        },
        {
            "id": 2,
            "name": "Teamtag",
            "istSchliesstag": True,
            "startdatum": "2026-11-16T00:00:00",
            "enddatum": "2026-11-16T23:59:00",
        },
    ]
    await setup_integration(hass, stack, async_get_events=events)
    state = hass.states.get("sensor.kitaplus_upcoming_dates")
    assert state.state == "Elternabend"
    assert [(e["datum"], e["zeit"], e["schliesstag"]) for e in state.attributes["entries"]] == [
        ("2026-11-02", "19:30", False),
        ("2026-11-16", None, True),
    ]

    from unittest.mock import patch

    from .common import CLIENT

    entry = hass.config_entries.async_entries("kitaplus")[0]
    stack.enter_context(patch(f"{CLIENT}.async_get_events", return_value=[]))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get("sensor.kitaplus_upcoming_dates")
    assert state.state == "unknown" and state.attributes["entries"] == [], (
        "nothing coming up: no state, empty list"
    )


def test_attached_files_are_listed_with_name_and_link_only() -> None:
    from custom_components.kitaplus.sensor import _attachments, _board_short

    files = [
        {"id": 7, "name": "Menüplan  02.11.", "istDateiVorhanden": True, "pfad": "folder/secret.pdf"},
        {"id": 8, "name": "Gelöscht", "istDateiVorhanden": False},
        {"id": 9, "name": None},
        {"id": 10, "name": "x" * 200},
        {"name": "Ohne Id"},
        {"id": 11, "name": "Vierte"},
    ]
    result = _attachments(files, lambda i: f"/api/kitaplus/attachment/e/{i}")
    assert result[0] == {"name": "Menüplan 02.11.", "url": "/api/kitaplus/attachment/e/7"}
    assert len(result) == 3 and len(result[1]["name"]) == 80 and result[2] == {"name": "Ohne Id", "url": None}
    assert _attachments(None, str) == [] and _attachments([], str) == []
    short = _board_short([{"id": 1, "titel": "t", "anhaenge": files}], lambda i: None)
    assert "secret" not in str(short) and short[0]["attachments"][0]["url"] is None


async def test_pending_replies_follow_each_update_and_are_worked_out_once(hass, stack) -> None:
    from unittest.mock import patch

    answered = [
        {"id": 7, "istBeantwortet": True, "nachricht": {"titel": "x", "istBestaetigungspflichtig": True}}
    ]
    open_one = [
        {"id": 8, "istBeantwortet": False, "nachricht": {"titel": "y", "istBestaetigungspflichtig": True}}
    ]
    entry = await setup_integration(hass, stack, async_get_messages=answered)
    assert hass.states.get("sensor.kitaplus_pending_replies").state == "0"
    stack.enter_context(
        patch(
            "custom_components.kitaplus.api.client.KitaPlusClient.async_get_messages", return_value=open_one
        )
    )
    with patch("custom_components.kitaplus.sensor.pending_replies", wraps=pending_replies) as spy:
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert spy.call_count == 1
    state = hass.states.get("sensor.kitaplus_pending_replies")
    assert state.state == "1" and state.attributes["messages"][0]["id"] == 8
