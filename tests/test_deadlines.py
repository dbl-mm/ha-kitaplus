"""The Kita's order deadline: "1 day before the meal at 11:00" (the rule of the user's Kita).

Example from the KitaPlus app: meals for Thursday 29.10.2026 can be ordered until
Wednesday 28.10.2026 at 11:00.
"""

from contextlib import ExitStack
from datetime import date, datetime, time
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_capture_events, async_fire_time_changed

from custom_components.kitaplus.api.exceptions import KitaPlusConnectionError
from custom_components.kitaplus.helpers import (
    DeadlineRule,
    deadline_for,
    meals_on,
    open_orders,
    order_status,
)

from .common import CLIENT, make_entry, meal_day, setup_integration

THURSDAY = "2026-10-29"
RULE_OPTIONS = {"order_deadline_days": 1, "order_deadline_time": "11:00:00", "reminder_lead_minutes": 120}
STATUS_TOMORROW = "sensor.vorname_1_order_status_tomorrow"
STATUS_TODAY = "sensor.vorname_1_order_status_today"
DEADLINE = "sensor.vorname_1_next_order_deadline"
EVENT = "kitaplus_order_deadline"


def local(text: str) -> datetime:
    return dt_util.parse_datetime(text).replace(tzinfo=dt_util.get_default_time_zone())


async def clock(hass: HomeAssistant, freezer, text: str) -> None:
    """Move the clock to a local time and let every timer that is due run."""
    freezer.move_to(local(text))
    async_fire_time_changed(hass, local(text))
    await hass.async_block_till_done()


@pytest.fixture
def stack():
    with ExitStack() as s:
        yield s


# ------------------------------------------------------------------------------------------ the maths


def test_the_rule_of_the_users_kita_gives_wednesday_eleven_for_a_thursday_meal() -> None:
    tz = dt_util.get_default_time_zone()
    rule = DeadlineRule(days_before=1, at=time(11, 0))
    assert deadline_for(date(2026, 10, 29), rule, tz) == datetime(2026, 10, 28, 11, 0, tzinfo=tz)


def test_deadlines_for_other_rules() -> None:
    tz = dt_util.get_default_time_zone()
    same_day = DeadlineRule(0, time(9, 0))
    assert deadline_for(date(2026, 10, 29), same_day, tz) == datetime(2026, 10, 29, 9, 0, tzinfo=tz)
    # a Monday meal, one day before: Sunday as calendar days, Friday when weekends do not count
    calendar = DeadlineRule(1, time(11, 0))
    weekdays = DeadlineRule(1, time(11, 0), workdays_only=True)
    assert deadline_for(date(2026, 11, 2), calendar, tz).date() == date(2026, 11, 1)
    assert deadline_for(date(2026, 11, 2), weekdays, tz).date() == date(2026, 10, 30)
    assert deadline_for(date(2026, 11, 3), DeadlineRule(2, time(11, 0), True), tz).date() == date(
        2026, 10, 30
    )


def meals(*, ordered: bool, orderable: bool) -> list:
    return meals_on([meal_day(THURSDAY, ordered=ordered, orderable=orderable)], date(2026, 10, 29))


def test_the_status_turns_to_missed_exactly_at_the_deadline() -> None:
    tz = dt_util.get_default_time_zone()
    deadline = datetime(2026, 10, 28, 11, 0, tzinfo=tz)
    stale_open = meals(ordered=False, orderable=True)  # the last update still said "open"
    assert order_status(stale_open, deadline, deadline.replace(minute=59, hour=10)) == "open"
    assert order_status(stale_open, deadline, deadline) == "missed"
    assert order_status(meals(ordered=True, orderable=True), deadline, deadline.replace(hour=12)) == "ordered"
    assert order_status(stale_open) == "open", "without a rule only what KitaPlus reports counts"


def test_open_orders_lists_only_days_that_can_still_be_ordered_soonest_first() -> None:
    tz = dt_util.get_default_time_zone()
    rule = DeadlineRule(1, time(11, 0))
    days = [
        meal_day("2026-10-31", ordered=False, orderable=True),
        meal_day("2026-10-29", ordered=False, orderable=True),
        meal_day("2026-10-30", ordered=True, orderable=True),  # already ordered
        meal_day("2026-10-27", ordered=False, orderable=True),  # in the past
        {"datum": None},
    ]
    now = datetime(2026, 10, 28, 8, 0, tzinfo=tz)
    found = open_orders(days, rule, now)
    assert [o.day for o in found] == [date(2026, 10, 29), date(2026, 10, 31)]
    assert found[0].deadline == datetime(2026, 10, 28, 11, 0, tzinfo=tz)
    assert [o.day for o in open_orders(days, rule, now.replace(hour=12))] == [date(2026, 10, 31)]
    assert all(o.deadline is None for o in open_orders(days, None, now))


# ----------------------------------------------------------------------------- in Home Assistant


async def test_the_deadline_sensor_and_the_status_follow_the_rule(hass, stack, freezer) -> None:
    await clock(hass, freezer, "2026-10-27T20:00:00")
    entry = make_entry(RULE_OPTIONS | {"scan_interval": 240})
    await setup_integration(
        hass, stack, entry=entry, async_get_meals=[meal_day(THURSDAY, ordered=False, orderable=True)]
    )
    state = hass.states.get(DEADLINE)
    assert dt_util.parse_datetime(state.state) == local("2026-10-28T11:00:00")
    assert state.attributes["day"] == THURSDAY and state.attributes["rule_set"] is True

    await clock(hass, freezer, "2026-10-28T10:59:00")
    assert hass.states.get(STATUS_TOMORROW).state == "open"
    await clock(hass, freezer, "2026-10-28T11:00:05")  # no update from KitaPlus in between
    assert hass.states.get(STATUS_TOMORROW).state == "missed", (
        "the status flips on the minute, not at the next poll"
    )
    assert hass.states.get(DEADLINE).state == "unknown", "nothing can be ordered any more"


async def test_a_reminder_comes_two_hours_before_the_deadline_with_fresh_data(hass, stack, freezer) -> None:
    await clock(hass, freezer, "2026-10-27T20:00:00")
    await setup_integration(
        hass,
        stack,
        entry=make_entry(RULE_OPTIONS),
        async_get_meals=[meal_day(THURSDAY, ordered=False, orderable=True)],
    )
    fired = async_capture_events(hass, EVENT)
    calls = stack.enter_context(
        patch(f"{CLIENT}.async_get_meals", return_value=[meal_day(THURSDAY, ordered=False, orderable=True)])
    )
    await clock(hass, freezer, "2026-10-28T08:59:00")
    assert fired == []
    await clock(hass, freezer, "2026-10-28T09:00:00")
    assert calls.called, "KitaPlus is asked for current data before the reminder"
    assert len(fired) == 1
    assert fired[0].data == {
        "child": "vorname-1",
        "child_id": fired[0].data["child_id"],
        "day": THURSDAY,
        "days_ahead": 1,
        "weekday": 3,  # Thursday
        "deadline": local("2026-10-28T11:00:00").isoformat(),
        "minutes_left": 120,
        "fresh": True,
    }
    await clock(hass, freezer, "2026-10-28T09:30:00")  # a later update does not remind a second time
    assert len(fired) == 1


async def test_no_reminder_when_it_was_ordered_in_the_meantime(hass, stack, freezer) -> None:
    await clock(hass, freezer, "2026-10-27T20:00:00")
    await setup_integration(
        hass,
        stack,
        entry=make_entry(RULE_OPTIONS),
        async_get_meals=[meal_day(THURSDAY, ordered=False, orderable=True)],
    )
    fired = async_capture_events(hass, EVENT)
    stack.enter_context(
        patch(f"{CLIENT}.async_get_meals", return_value=[meal_day(THURSDAY, ordered=True, orderable=True)])
    )
    await clock(hass, freezer, "2026-10-28T09:00:00")
    assert fired == []


async def test_no_reminder_when_kitaplus_already_closed_ordering(hass, stack, freezer) -> None:
    await clock(hass, freezer, "2026-10-27T20:00:00")
    await setup_integration(
        hass,
        stack,
        entry=make_entry(RULE_OPTIONS),
        async_get_meals=[meal_day(THURSDAY, ordered=False, orderable=True)],
    )
    fired = async_capture_events(hass, EVENT)
    stack.enter_context(
        patch(f"{CLIENT}.async_get_meals", return_value=[meal_day(THURSDAY, ordered=False, orderable=False)])
    )
    await clock(hass, freezer, "2026-10-28T09:00:00")
    assert fired == []


async def test_the_reminder_still_comes_when_kitaplus_cannot_be_reached_but_says_so(
    hass, stack, freezer
) -> None:
    await clock(hass, freezer, "2026-10-27T20:00:00")
    await setup_integration(
        hass,
        stack,
        entry=make_entry(RULE_OPTIONS),
        async_get_meals=[meal_day(THURSDAY, ordered=False, orderable=True)],
    )
    fired = async_capture_events(hass, EVENT)
    stack.enter_context(patch(f"{CLIENT}.async_get_meals", side_effect=KitaPlusConnectionError("down")))
    await clock(hass, freezer, "2026-10-28T09:00:00")
    assert len(fired) == 1 and fired[0].data["fresh"] is False


async def test_no_events_without_a_rule_or_with_the_reminder_switched_off(hass, stack, freezer) -> None:
    await clock(hass, freezer, "2026-10-27T20:00:00")
    meals = [meal_day(THURSDAY, ordered=False, orderable=True)]
    entry = await setup_integration(hass, stack, async_get_meals=meals)  # no rule in the options
    fired = async_capture_events(hass, EVENT)
    assert hass.states.get(DEADLINE).state == "unknown"
    assert hass.states.get(DEADLINE).attributes["rule_set"] is False
    await clock(hass, freezer, "2026-10-28T09:00:00")
    assert fired == []
    await hass.config_entries.async_remove(entry.entry_id)

    off = make_entry(RULE_OPTIONS | {"reminder_lead_minutes": 0})
    await setup_integration(hass, stack, entry=off, async_get_meals=meals)
    await clock(hass, freezer, "2026-10-28T09:30:00")
    assert fired == [], "lead time 0 switches the reminder off"


async def test_an_invalid_time_falls_back_to_eleven(hass, stack, freezer) -> None:
    await clock(hass, freezer, "2026-10-27T20:00:00")
    entry = make_entry(RULE_OPTIONS | {"order_deadline_time": "garbage"})
    await setup_integration(
        hass, stack, entry=entry, async_get_meals=[meal_day(THURSDAY, ordered=False, orderable=True)]
    )
    assert dt_util.parse_datetime(hass.states.get(DEADLINE).state) == local("2026-10-28T11:00:00")


async def test_timers_stop_when_the_entry_is_unloaded(hass, stack, freezer) -> None:
    await clock(hass, freezer, "2026-10-27T20:00:00")
    entry = await setup_integration(
        hass,
        stack,
        entry=make_entry(RULE_OPTIONS),
        async_get_meals=[meal_day(THURSDAY, ordered=False, orderable=True)],
    )
    fired = async_capture_events(hass, EVENT)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await clock(hass, freezer, "2026-10-28T09:00:00")
    assert fired == []


async def test_a_same_day_deadline_makes_today_missed_after_nine(hass, stack, freezer) -> None:
    """A Kita that takes orders until 9:00 on the day itself."""
    await clock(hass, freezer, "2026-10-29T06:00:00")
    entry = make_entry({"order_deadline_days": 0, "order_deadline_time": "09:00:00", "scan_interval": 240})
    await setup_integration(
        hass, stack, entry=entry, async_get_meals=[meal_day(THURSDAY, ordered=False, orderable=True)]
    )
    assert hass.states.get(STATUS_TODAY).state == "open"
    await clock(hass, freezer, "2026-10-29T09:00:01")
    assert hass.states.get(STATUS_TODAY).state == "missed"


# ------------------------------------------------------------------------------------- the options


async def test_the_deadline_can_be_entered_and_removed_in_the_options(hass: HomeAssistant) -> None:
    entry = make_entry()
    entry.add_to_hass(hass)
    form = await hass.config_entries.options.async_init(entry.entry_id)
    assert {
        "order_deadline_days",
        "order_deadline_time",
        "order_deadline_workdays",
        "reminder_lead_minutes",
    } <= {str(key) for key in form["data_schema"].schema}
    saved = await hass.config_entries.options.async_configure(
        form["flow_id"],
        {"scan_interval": 30, "order_deadline_days": 1.0, "order_deadline_time": "11:00:00",
         "order_deadline_workdays": False, "reminder_lead_minutes": 120.0},
    )  # fmt: skip
    assert saved["data"]["order_deadline_days"] == 1 and isinstance(saved["data"]["order_deadline_days"], int)
    assert saved["data"]["reminder_lead_minutes"] == 120

    again = await hass.config_entries.options.async_init(entry.entry_id)
    cleared = await hass.config_entries.options.async_configure(again["flow_id"], {"scan_interval": 30})
    assert "order_deadline_days" not in cleared["data"], "leaving it empty removes the rule"


async def test_a_deadline_beyond_two_weeks_is_rejected(hass: HomeAssistant) -> None:
    from homeassistant.data_entry_flow import InvalidData

    entry = make_entry()
    entry.add_to_hass(hass)
    form = await hass.config_entries.options.async_init(entry.entry_id)
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            form["flow_id"], {"scan_interval": 30, "order_deadline_days": 30}
        )


async def test_a_day_is_never_reminded_twice(hass, stack, freezer) -> None:
    await clock(hass, freezer, "2026-10-27T20:00:00")
    entry = await setup_integration(
        hass,
        stack,
        entry=make_entry(RULE_OPTIONS),
        async_get_meals=[meal_day(THURSDAY, ordered=False, orderable=True)],
    )
    fired = async_capture_events(hass, EVENT)
    await clock(hass, freezer, "2026-10-28T09:00:00")
    assert len(fired) == 1
    child_id = fired[0].data["child_id"]
    await entry.runtime_data._async_remind(
        child_id, date(2026, 10, 29)
    )  # e.g. a second timer for the same day
    await hass.async_block_till_done()
    assert len(fired) == 1


async def test_a_poll_finishing_at_the_due_moment_does_not_swallow_the_reminder(hass, stack, freezer) -> None:
    """The regular update and the reminder can become due in the same instant, in either order.

    Here the update runs first and re-plans the timers before the reminder's own timer callback has run. The
    reminder must survive that (this was a real race: the re-planning cancelled it, found by a flaky test).
    """
    await clock(hass, freezer, "2026-10-27T20:00:00")
    entry = await setup_integration(
        hass,
        stack,
        entry=make_entry(RULE_OPTIONS),
        async_get_meals=[meal_day(THURSDAY, ordered=False, orderable=True)],
    )
    fired = async_capture_events(hass, EVENT)
    coordinator = entry.runtime_data
    freezer.move_to(local("2026-10-28T09:00:00"))  # the reminder is due now, its callback has not run yet
    coordinator._schedule_deadlines(coordinator.data)  # what a finishing update does
    async_fire_time_changed(hass, local("2026-10-28T09:00:00"))
    await hass.async_block_till_done()
    assert len(fired) == 1


async def test_a_reminder_time_that_has_already_passed_is_made_up_for_while_the_day_is_open(
    hass, stack, freezer
) -> None:
    """Home Assistant starts at 10:00; the 9:00 reminder was missed but ordering is open until 11:00."""
    await clock(hass, freezer, "2026-10-28T10:00:00")
    fired = async_capture_events(hass, EVENT)
    entry = await setup_integration(
        hass,
        stack,
        entry=make_entry(RULE_OPTIONS),
        async_get_meals=[meal_day(THURSDAY, ordered=False, orderable=True)],
    )
    assert fired == [], "with a frozen test clock a timer for 'now' waits until the clock moves"
    calls = stack.enter_context(
        patch(f"{CLIENT}.async_get_meals", return_value=[meal_day(THURSDAY, ordered=False, orderable=True)])
    )
    async_fire_time_changed(
        hass, local("2026-10-28T10:00:01")
    )  # in real life time flows and it starts at once
    await hass.async_block_till_done()
    assert len(fired) == 1 and fired[0].data["minutes_left"] == 60
    assert calls.call_count == 1, (
        "making up for the reminder asks KitaPlus once and starts no loop of updates"
    )
    assert entry.runtime_data._timers.keys() == {("deadline", fired[0].data["child_id"], date(2026, 10, 29))}


async def test_two_reminders_for_the_same_day_at_the_same_time_send_one_message(hass, stack, freezer) -> None:
    import asyncio

    await clock(hass, freezer, "2026-10-27T20:00:00")
    entry = await setup_integration(
        hass,
        stack,
        entry=make_entry(RULE_OPTIONS),
        async_get_meals=[meal_day(THURSDAY, ordered=False, orderable=True)],
    )
    fired = async_capture_events(hass, EVENT)
    coordinator = entry.runtime_data
    child_id = coordinator.data.children[0]["id"]
    freezer.move_to(local("2026-10-28T09:00:00"))
    first = hass.async_create_task(coordinator._async_remind(child_id, date(2026, 10, 29)))
    second = hass.async_create_task(coordinator._async_remind(child_id, date(2026, 10, 29)))
    await asyncio.gather(first, second)
    await hass.async_block_till_done()
    assert len(fired) == 1


async def test_timers_of_days_that_are_no_longer_open_are_removed(hass, stack, freezer) -> None:
    await clock(hass, freezer, "2026-10-27T20:00:00")
    entry = await setup_integration(
        hass,
        stack,
        entry=make_entry(RULE_OPTIONS),
        async_get_meals=[meal_day(THURSDAY, ordered=False, orderable=True)],
    )
    coordinator = entry.runtime_data
    assert {key[0] for key in coordinator._timers} == {"deadline", "remind"}
    stack.enter_context(
        patch(f"{CLIENT}.async_get_meals", return_value=[meal_day(THURSDAY, ordered=True, orderable=True)])
    )
    await coordinator.async_refresh()
    assert coordinator._timers == {}, "ordered meanwhile: neither a reminder nor a deadline update is needed"
