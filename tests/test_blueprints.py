"""Every blueprint loads, and behaves as described: right trigger, right conditions, right variables."""

import shutil
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pytest
from homeassistant.components.blueprint import models, schemas
from homeassistant.core import Event, HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from homeassistant.util.yaml import load_yaml
from pytest_homeassistant_custom_component.common import async_capture_events, async_fire_time_changed

from .common import CLIENT, make_entry, meal_day, setup_integration

BLUEPRINT_DIR = Path(__file__).parent.parent / "blueprints" / "automation" / "kitaplus"
SOURCE = "https://github.com/dbl-mm/ha-kitaplus/blob/main/blueprints/automation/kitaplus/"
RESULT = "kitaplus_test_result"  # the "user action" of every test fires this event


@pytest.fixture
def stack():
    with ExitStack() as s:
        yield s


def blueprint_files() -> list[Path]:
    return sorted(BLUEPRINT_DIR.glob("*.yaml"))


def user_action(**extra: str) -> list[dict]:
    """A stand-in for what a user chooses: it records every variable the blueprint hands over."""
    data = {"message": "{{ message }}", **extra}
    return [{"event": RESULT, "event_data": data}]


def _install(hass: HomeAssistant, name: str) -> None:
    target = Path(hass.config.path("blueprints/automation/kitaplus"))
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy(BLUEPRINT_DIR / name, target / name)


async def start(hass: HomeAssistant, name: str, inputs: dict) -> None:
    await hass.async_add_executor_job(_install, hass, name)
    assert await async_setup_component(hass, "homeassistant", {})  # always present in a real installation
    config = {"automation": {"alias": name, "use_blueprint": {"path": f"kitaplus/{name}", "input": inputs}}}
    assert await async_setup_component(hass, "automation", config)
    await hass.async_block_till_done()


async def at(hass: HomeAssistant, freezer, local: str) -> None:
    """Move the clock to a local time and let time triggers fire."""
    when = dt_util.parse_datetime(local).replace(tzinfo=dt_util.get_default_time_zone())
    freezer.move_to(when)
    async_fire_time_changed(hass, when)
    await hass.async_block_till_done()


def results(hass: HomeAssistant) -> list[Event]:
    return async_capture_events(hass, RESULT)


# ---------------------------------------------------------------------------- structure of every file


@pytest.mark.parametrize("path", blueprint_files(), ids=lambda p: p.name)
def test_blueprint_is_valid_and_complete(path: Path) -> None:
    data = load_yaml(str(path))
    blueprint = models.Blueprint(data, expected_domain="automation", schema=schemas.BLUEPRINT_SCHEMA)
    head = data["blueprint"]
    assert head["author"] == "dbl-mm"
    assert head["source_url"] == SOURCE + path.name  # lets users re-import and update
    assert head["homeassistant"]["min_version"] == "2025.8.0"
    assert "English" in head["description"], "every blueprint carries an English hint"
    assert blueprint.inputs, "a blueprint without inputs is not configurable"
    text = path.read_text()
    assert "device_id" not in text, "entities only, device ids break when a device is re-added"
    assert "wait_template" not in text


def test_all_eight_blueprints_exist() -> None:
    assert [p.stem for p in blueprint_files()] == [
        "bestellfrist_erinnerung",
        "essen_erinnerung",
        "guthaben_niedrig",
        "neue_mitteilung",
        "rueckmeldung_erinnerung",
        "schliesstag",
        "sitzung_laeuft_ab",
        "tagesbriefing",
    ]


# ---------------------------------------------------------------------------- essen_erinnerung

STATUS_TOMORROW = "sensor.vorname_1_order_status_tomorrow"
STATUS_TODAY = "sensor.vorname_1_order_status_today"
CLOSED_TOMORROW = "binary_sensor.kitaplus_closed_tomorrow"


def food_action() -> list[dict]:
    return user_action(child="{{ child }}", day="{{ day }}", status="{{ status }}")


async def test_food_reminder_fires_with_variables(hass, stack, freezer) -> None:
    await at(hass, freezer, "2026-06-14T10:00:00")  # tomorrow is the 15th: offered, not ordered, still open
    meals = [meal_day("2026-06-15", ordered=False, orderable=True)]
    await setup_integration(hass, stack, async_get_meals=meals)
    assert hass.states.get(STATUS_TOMORROW).state == "open"
    fired = results(hass)
    await start(
        hass, "essen_erinnerung.yaml", {"status_tomorrow": [STATUS_TOMORROW], "notify_action": food_action()}
    )
    await at(hass, freezer, "2026-06-14T18:00:00")
    assert len(fired) == 1, "the blueprint's variables must reach the user's action"
    data = fired[0].data
    assert (data["child"], data["day"], data["status"]) == ("vorname-1", "tomorrow", "open")
    assert (
        data["message"]
        == "Für morgen ist für vorname-1 noch kein Essen bestellt. Bestellen ist noch möglich."
    )


async def test_food_reminder_never_asks_to_order_after_the_deadline(hass, stack, freezer) -> None:
    await at(hass, freezer, "2026-06-14T10:00:00")
    meals = [meal_day("2026-06-15", ordered=False, orderable=False)]  # KitaPlus no longer accepts an order
    await setup_integration(hass, stack, async_get_meals=meals)
    assert hass.states.get(STATUS_TOMORROW).state == "missed"
    fired = results(hass)
    await start(
        hass, "essen_erinnerung.yaml", {"status_tomorrow": [STATUS_TOMORROW], "notify_action": food_action()}
    )
    await at(hass, freezer, "2026-06-14T18:00:00")
    assert fired == [], "by default nobody is told to do something that is no longer possible"


async def test_food_reminder_can_report_a_missed_deadline_on_request(hass, stack, freezer) -> None:
    await at(hass, freezer, "2026-06-14T10:00:00")
    meals = [meal_day("2026-06-15", ordered=False, orderable=False)]
    await setup_integration(hass, stack, async_get_meals=meals)
    fired = results(hass)
    inputs = {"status_tomorrow": [STATUS_TOMORROW], "report_missed": True, "notify_action": food_action()}
    await start(hass, "essen_erinnerung.yaml", inputs)
    await at(hass, freezer, "2026-06-14T18:00:00")
    assert len(fired) == 1 and fired[0].data["status"] == "missed"
    assert fired[0].data["message"].endswith("nichts bestellt, und die Bestellfrist ist vorbei.")


SLOW_POLLING = {"scan_interval": 240}  # the integration itself will not poll between 17:00 and 18:00


async def test_food_reminder_asks_for_current_data_because_the_deadline_may_have_passed(
    hass, stack, freezer
) -> None:
    """The last update said "open"; by the reminder KitaPlus has closed the order window."""
    await at(hass, freezer, "2026-06-14T17:00:00")
    meals = [meal_day("2026-06-15", ordered=False, orderable=True)]
    await setup_integration(hass, stack, entry=make_entry(SLOW_POLLING), async_get_meals=meals)
    assert hass.states.get(STATUS_TOMORROW).state == "open"
    stack.enter_context(
        patch(
            f"{CLIENT}.async_get_meals", return_value=[meal_day("2026-06-15", ordered=False, orderable=False)]
        )
    )
    fired = results(hass)
    await start(
        hass, "essen_erinnerung.yaml", {"status_tomorrow": [STATUS_TOMORROW], "notify_action": food_action()}
    )
    await at(hass, freezer, "2026-06-14T18:00:00")
    assert hass.states.get(STATUS_TOMORROW).state == "missed", "the blueprint refreshed the data first"
    assert fired == [], "so it did not send a reminder that can no longer be acted on"


async def test_food_reminder_without_refresh_trusts_the_last_update(hass, stack, freezer) -> None:
    await at(hass, freezer, "2026-06-14T17:00:00")
    meals = [meal_day("2026-06-15", ordered=False, orderable=True)]
    await setup_integration(hass, stack, entry=make_entry(SLOW_POLLING), async_get_meals=meals)
    stack.enter_context(
        patch(
            f"{CLIENT}.async_get_meals", return_value=[meal_day("2026-06-15", ordered=False, orderable=False)]
        )
    )
    fired = results(hass)
    inputs = {"status_tomorrow": [STATUS_TOMORROW], "refresh_first": False, "notify_action": food_action()}
    await start(hass, "essen_erinnerung.yaml", inputs)
    await at(hass, freezer, "2026-06-14T18:00:00")
    assert hass.states.get(STATUS_TOMORROW).state == "open", "nothing refreshed the data"
    assert len(fired) == 1, "documented trade-off: without a refresh the data can be one poll interval old"


async def test_food_reminder_is_silent_when_everything_is_ordered(hass, stack, freezer) -> None:
    await at(hass, freezer, "2026-06-13T10:00:00")  # tomorrow (14th) is ordered in the fixture
    await setup_integration(hass, stack)
    assert hass.states.get(STATUS_TOMORROW).state == "ordered"
    fired = results(hass)
    await start(
        hass, "essen_erinnerung.yaml", {"status_tomorrow": [STATUS_TOMORROW], "notify_action": food_action()}
    )
    await at(hass, freezer, "2026-06-13T18:00:00")
    assert fired == []


async def test_food_reminder_stays_quiet_when_the_kita_is_closed_tomorrow(hass, stack, freezer) -> None:
    await at(hass, freezer, "2026-06-14T10:00:00")
    closure = {
        "id": 1,
        "name": "Brückentag",
        "istSchliesstag": True,
        "startdatum": "2026-06-15T00:00:00",
        "enddatum": "2026-06-15T23:59:00",
    }
    meals = [meal_day("2026-06-15", ordered=False, orderable=True)]
    await setup_integration(hass, stack, async_get_events=[closure], async_get_meals=meals)
    fired = results(hass)
    inputs = {
        "status_tomorrow": [STATUS_TOMORROW],
        "closed_tomorrow": [CLOSED_TOMORROW],
        "notify_action": food_action(),
    }
    await start(hass, "essen_erinnerung.yaml", inputs)
    await at(hass, freezer, "2026-06-14T18:00:00")
    assert fired == []


async def test_food_last_chance_covers_a_deadline_on_the_same_day(hass, stack, freezer) -> None:
    await at(hass, freezer, "2026-06-15T06:00:00")  # a Kita that takes orders until 9:00 on the day itself
    await setup_integration(
        hass, stack, async_get_meals=[meal_day("2026-06-15", ordered=False, orderable=True)]
    )
    assert hass.states.get(STATUS_TODAY).state == "open"
    fired = results(hass)
    inputs = {
        "status_tomorrow": [STATUS_TOMORROW],
        "status_today": [STATUS_TODAY],
        "last_chance_time": "07:30:00",
        "notify_action": food_action(),
    }
    await start(hass, "essen_erinnerung.yaml", inputs)
    await at(hass, freezer, "2026-06-15T07:30:00")
    assert len(fired) == 1
    assert (fired[0].data["day"], fired[0].data["status"]) == ("today", "open")
    assert fired[0].data["message"].startswith("Für heute ist für vorname-1 noch kein Essen bestellt")


async def test_food_last_chance_does_nothing_without_today_sensors(hass, stack, freezer) -> None:
    await at(hass, freezer, "2026-06-15T06:00:00")
    await setup_integration(
        hass, stack, async_get_meals=[meal_day("2026-06-15", ordered=False, orderable=True)]
    )
    fired = results(hass)
    await start(
        hass, "essen_erinnerung.yaml", {"status_tomorrow": [STATUS_TOMORROW], "notify_action": food_action()}
    )
    await at(hass, freezer, "2026-06-15T07:30:00")
    assert fired == [], "the optional morning reminder is off unless sensors are chosen"


# ---------------------------------------------------------------------------- schliesstag

CLOSED_TODAY = "binary_sensor.kitaplus_closed_today"


def closure(day: str, name: str = "Brückentag") -> dict:
    return {
        "id": 1,
        "name": name,
        "istSchliesstag": True,
        "startdatum": f"{day}T00:00:00",
        "enddatum": f"{day}T23:59:00",
    }


async def test_closure_notice_the_evening_before_names_the_reason(hass, stack, freezer) -> None:
    await at(hass, freezer, "2026-06-13T10:00:00")
    await setup_integration(hass, stack, async_get_events=[closure("2026-06-14")])
    fired = results(hass)
    inputs = {
        "closed_tomorrow": CLOSED_TOMORROW,
        "evening_action": user_action(when="{{ when }}", why="{{ reason }}"),
    }
    await start(hass, "schliesstag.yaml", inputs)
    await at(hass, freezer, "2026-06-13T19:00:00")
    assert len(fired) == 1
    assert fired[0].data["message"] == "Die Kita ist morgen geschlossen (Brückentag)."
    assert (fired[0].data["when"], fired[0].data["why"]) == ("tomorrow", "Brückentag")


async def test_no_closure_notice_when_the_kita_is_open(hass, stack, freezer) -> None:
    await at(hass, freezer, "2026-06-13T10:00:00")
    await setup_integration(hass, stack)
    fired = results(hass)
    await start(
        hass, "schliesstag.yaml", {"closed_tomorrow": CLOSED_TOMORROW, "evening_action": user_action()}
    )
    await at(hass, freezer, "2026-06-13T19:00:00")
    assert fired == []


async def test_closure_morning_action_runs_only_on_a_closure_day(hass, stack, freezer) -> None:
    await at(hass, freezer, "2026-06-14T05:00:00")
    await setup_integration(hass, stack, async_get_events=[closure("2026-06-14")])
    fired = results(hass)
    inputs = {
        "closed_tomorrow": CLOSED_TOMORROW,
        "closed_today": [CLOSED_TODAY],
        "morning_action": user_action(when="{{ when }}"),
    }
    await start(hass, "schliesstag.yaml", inputs)
    await at(hass, freezer, "2026-06-14T06:30:00")
    assert [e.data["when"] for e in fired] == ["today"]
    assert fired[0].data["message"] == "Die Kita ist heute geschlossen (Brückentag)."


async def test_closure_morning_does_nothing_without_a_chosen_action(hass, stack, freezer) -> None:
    await at(hass, freezer, "2026-06-14T05:00:00")
    await setup_integration(hass, stack, async_get_events=[closure("2026-06-14")])
    fired = results(hass)
    await start(
        hass, "schliesstag.yaml", {"closed_tomorrow": CLOSED_TOMORROW, "closed_today": [CLOSED_TODAY]}
    )
    await at(hass, freezer, "2026-06-14T06:30:00")  # the default morning action is "nothing"
    assert fired == []


# ---------------------------------------------------------------------------- neue_mitteilung


def announce(hass: HomeAssistant, kind: str, title: str | None) -> None:
    event = "kitaplus_new_board_post" if kind == "board" else "kitaplus_new_message"
    hass.bus.async_fire(event, {"id": 1, "title": title})


def new_item_action() -> list[dict]:
    return user_action(title="{{ title }}", source="{{ source }}", label="{{ source_label }}")


async def test_new_item_notification_carries_title_and_source(hass) -> None:
    fired = results(hass)
    await start(hass, "neue_mitteilung.yaml", {"notify_action": new_item_action()})
    announce(hass, "board", "Ausflug am Freitag")
    announce(hass, "message", "Bitte antworten")
    await hass.async_block_till_done()
    assert [(e.data["source"], e.data["title"], e.data["label"]) for e in fired] == [
        ("board", "Ausflug am Freitag", "Schwarzes Brett"),
        ("message", "Bitte antworten", "Postfach"),
    ]
    assert fired[0].data["message"] == "Schwarzes Brett: Ausflug am Freitag"


async def test_new_item_notification_can_be_limited_to_one_source(hass) -> None:
    fired = results(hass)
    await start(hass, "neue_mitteilung.yaml", {"source": "message", "notify_action": new_item_action()})
    announce(hass, "board", "Brett")
    announce(hass, "message", "Nachricht")
    await hass.async_block_till_done()
    assert [e.data["source"] for e in fired] == ["message"]


async def test_new_item_keywords_are_case_insensitive_and_optional(hass) -> None:
    fired = results(hass)
    inputs = {"keywords": " Ausflug , elternabend ", "notify_action": new_item_action()}
    await start(hass, "neue_mitteilung.yaml", inputs)
    announce(hass, "board", "Der AUSFLUG fällt aus")
    announce(hass, "board", "Neuer Speiseplan")
    announce(hass, "message", "Einladung zum Elternabend")
    await hass.async_block_till_done()
    assert [e.data["title"] for e in fired] == ["Der AUSFLUG fällt aus", "Einladung zum Elternabend"]


async def test_new_item_without_a_title_still_notifies(hass) -> None:
    fired = results(hass)
    await start(hass, "neue_mitteilung.yaml", {"notify_action": new_item_action()})
    announce(hass, "board", None)
    await hass.async_block_till_done()
    assert fired[0].data["message"] == "Schwarzes Brett: Neuer Eintrag"


# ---------------------------------------------------------------------------- rueckmeldung_erinnerung

PENDING = "sensor.kitaplus_pending_replies"


def needs_reply(title: str = "Einwilligung Ausflug", deadline: str | None = "2026-06-20T00:00:00") -> dict:
    note = {"titel": title, "istBestaetigungspflichtig": True, "rueckmeldefrist": deadline}
    return {"id": 7, "istBeantwortet": False, "nachricht": note}


def reply_action() -> list[dict]:
    return user_action(count="{{ count }}", titles="{{ titles | join('|') }}")


async def test_open_reply_reminder_names_title_and_deadline(hass, stack, freezer) -> None:
    await at(hass, freezer, "2026-06-13T10:00:00")
    await setup_integration(hass, stack, async_get_messages=[needs_reply()])
    fired = results(hass)
    await start(hass, "rueckmeldung_erinnerung.yaml", {"pending": PENDING, "notify_action": reply_action()})
    await at(hass, freezer, "2026-06-13T17:00:00")
    assert len(fired) == 1
    assert fired[0].data["count"] == 1 and fired[0].data["titles"] == "Einwilligung Ausflug"
    assert fired[0].data["message"] == "1 Rückmeldung ist offen: Einwilligung Ausflug (bis 20.06.)"


async def test_reply_reminder_is_silent_when_nothing_is_open(hass, stack, freezer) -> None:
    await at(hass, freezer, "2026-06-13T10:00:00")
    await setup_integration(hass, stack, async_get_messages=[])
    fired = results(hass)
    await start(hass, "rueckmeldung_erinnerung.yaml", {"pending": PENDING, "notify_action": reply_action()})
    await at(hass, freezer, "2026-06-13T17:00:00")
    assert fired == []


async def test_reply_reminder_daily_part_can_be_switched_off(hass, stack, freezer) -> None:
    await at(hass, freezer, "2026-06-13T10:00:00")
    await setup_integration(hass, stack, async_get_messages=[needs_reply()])
    fired = results(hass)
    inputs = {"pending": PENDING, "remind_daily": False, "notify_action": reply_action()}
    await start(hass, "rueckmeldung_erinnerung.yaml", inputs)
    await at(hass, freezer, "2026-06-13T17:00:00")
    assert fired == []


async def test_a_new_reply_request_is_announced_immediately(hass, stack, freezer) -> None:
    await at(hass, freezer, "2026-06-13T10:00:00")
    entry = await setup_integration(hass, stack, async_get_messages=[])
    fired = results(hass)
    inputs = {"pending": PENDING, "remind_daily": False, "notify_action": reply_action()}
    await start(hass, "rueckmeldung_erinnerung.yaml", inputs)
    stack.enter_context(patch(f"{CLIENT}.async_get_messages", return_value=[needs_reply(deadline=None)]))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert len(fired) == 1
    assert (
        fired[0].data["message"] == "1 Rückmeldung ist offen: Einwilligung Ausflug"
    )  # no deadline, no "(bis …)"


# ---------------------------------------------------------------------------- guthaben_niedrig

BALANCE = "sensor.kitaplus_meal_account_balance"


def account(balance: str) -> list[dict]:
    return [{"id": 1, "istAktiv": True, "kontostand": balance}]


def balance_action() -> list[dict]:
    return user_action(balance="{{ balance }}", limit="{{ threshold }}")


async def test_low_balance_is_reported_when_it_drops_below_the_limit(hass, stack, freezer) -> None:
    await at(hass, freezer, "2026-06-13T10:00:00")
    entry = await setup_integration(hass, stack, async_get_accounts=account("50.00"))
    fired = results(hass)
    inputs = {
        "balance_sensor": BALANCE,
        "threshold": 10,
        "settle_time": {"seconds": 1},
        "notify_action": balance_action(),
    }
    await start(hass, "guthaben_niedrig.yaml", inputs)
    stack.enter_context(patch(f"{CLIENT}.async_get_accounts", return_value=account("4.50")))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    await at(hass, freezer, "2026-06-13T10:00:05")  # the value stayed low for the settle time
    assert len(fired) == 1
    assert fired[0].data["message"] == "Das Verpflegungs-Guthaben beträgt nur noch 4.50 € (Grenze 10.00 €)."
    assert fired[0].data["balance"] == 4.5 and fired[0].data["limit"] == 10


async def test_low_balance_stays_quiet_above_the_limit(hass, stack, freezer) -> None:
    await at(hass, freezer, "2026-06-13T10:00:00")
    entry = await setup_integration(hass, stack, async_get_accounts=account("50.00"))
    fired = results(hass)
    await start(
        hass,
        "guthaben_niedrig.yaml",
        {"balance_sensor": BALANCE, "threshold": 10, "notify_action": balance_action()},
    )
    stack.enter_context(patch(f"{CLIENT}.async_get_accounts", return_value=account("40.00")))
    await entry.runtime_data.async_refresh()
    await at(hass, freezer, "2026-06-13T09:00:00")
    assert fired == []


async def test_low_balance_daily_reminder_is_optional(hass, stack, freezer) -> None:
    for remind, expected in ((False, 0), (True, 1)):
        await at(hass, freezer, "2026-06-13T08:00:00")
        entry = await setup_integration(hass, stack, async_get_accounts=account("3.00"))
        fired = results(hass)
        inputs = {
            "balance_sensor": BALANCE,
            "threshold": 10,
            "remind_daily": remind,
            "notify_action": balance_action(),
        }
        await start(hass, "guthaben_niedrig.yaml", inputs)
        await at(hass, freezer, "2026-06-13T09:00:00")
        assert len(fired) == expected, f"remind_daily={remind}"
        await hass.config_entries.async_remove(entry.entry_id)
        await hass.async_block_till_done()
        hass.states.async_remove("automation.guthaben_niedrig_yaml")


# ---------------------------------------------------------------------------- sitzung_laeuft_ab


async def test_session_warning_comes_the_chosen_time_before_expiry(hass, stack, freezer) -> None:
    from homeassistant.helpers import entity_registry as er

    await at(hass, freezer, "2026-06-10T10:00:00")
    expires = dt_util.parse_datetime("2026-06-20T12:00:00+00:00").timestamp()
    entry = make_entry(refresh_expires=expires)
    await setup_integration(hass, stack, entry=entry)
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", "kitaplus", f"{entry.entry_id}_session_valid_until")
    registry.async_update_entity(entity_id, disabled_by=None)  # it is off by default
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state.startswith("2026-06-20T12:00")

    fired = results(hass)
    inputs = {
        "session_sensor": entity_id,
        "warn_before": "-72:00:00",
        "notify_action": user_action(days="{{ days }}"),
    }
    await start(hass, "sitzung_laeuft_ab.yaml", inputs)
    freezer.move_to("2026-06-17T11:59:00+00:00")
    async_fire_time_changed(hass, dt_util.parse_datetime("2026-06-17T11:59:00+00:00"))
    await hass.async_block_till_done()
    assert fired == [], "not yet"
    freezer.move_to("2026-06-17T12:00:01+00:00")
    async_fire_time_changed(hass, dt_util.parse_datetime("2026-06-17T12:00:01+00:00"))
    await hass.async_block_till_done()
    assert len(fired) == 1 and fired[0].data["days"] == 3
    assert "Neu konfigurieren" in fired[0].data["message"]


# ---------------------------------------------------------------------------- tagesbriefing


async def test_daily_briefing_summarises_everything_in_one_message(hass, stack, freezer) -> None:
    await at(hass, freezer, "2026-06-13T06:00:00")
    await setup_integration(
        hass,
        stack,
        async_get_events=[closure("2026-06-14", "Teamtag")],
        async_get_messages=[needs_reply()],
        async_get_accounts=account("25.00"),
    )
    fired = results(hass)
    inputs = {
        "closed_today": [CLOSED_TODAY],
        "closed_tomorrow": [CLOSED_TOMORROW],
        "meal_today": ["sensor.vorname_1_meal_today"],
        "meal_tomorrow": ["sensor.vorname_1_meal_tomorrow"],
        "pending": [PENDING],
        "balance": [BALANCE],
        "notify_action": user_action(lines="{{ lines | length }}"),
    }
    await start(hass, "tagesbriefing.yaml", inputs)
    await at(hass, freezer, "2026-06-13T07:00:00")
    assert len(fired) == 1
    message = fired[0].data["message"].split("\n")
    assert "Kita morgen geschlossen (Teamtag)" in message
    assert any(line.startswith("vorname-1 heute: ") for line in message)
    assert any(line.startswith("vorname-1 morgen: ") for line in message)
    assert "1 Rückmeldung(en) offen" in message
    assert "Guthaben: 25.00 €" in message
    assert "Kita heute geschlossen" not in " ".join(message)  # the Kita is open today
    assert fired[0].data["lines"] == len(message)


async def test_daily_briefing_is_silent_without_anything_to_report(hass, stack, freezer) -> None:
    await at(hass, freezer, "2026-06-13T06:00:00")
    await setup_integration(hass, stack)
    fired = results(hass)
    await start(hass, "tagesbriefing.yaml", {"closed_today": [CLOSED_TODAY], "notify_action": user_action()})
    await at(hass, freezer, "2026-06-13T07:00:00")
    assert fired == []


# ---------------------------------------------------------------------------- README import buttons


def test_every_blueprint_has_a_working_import_button_in_the_readme() -> None:
    from urllib.parse import parse_qs, urlparse

    readme = (BLUEPRINT_DIR.parent.parent.parent / "README.md").read_text()
    import re

    links = re.findall(r'href="(https://my\.home-assistant\.io/redirect/blueprint_import/\?[^"]+)"', readme)
    targets = {parse_qs(urlparse(link).query)["blueprint_url"][0] for link in links}
    assert targets == {SOURCE + path.name for path in blueprint_files()}, (
        "one button per blueprint, none stale"
    )
    for path in blueprint_files():
        assert (
            f"blueprints/automation/kitaplus/{path.name}"
            in (BLUEPRINT_DIR.parent.parent.parent / "docs" / "blueprints.md").read_text()
        )


async def test_daily_briefing_tells_open_and_missed_orders_apart(hass, stack, freezer) -> None:
    await at(hass, freezer, "2026-06-14T06:00:00")
    meals = [
        meal_day("2026-06-14", ordered=False, orderable=True),  # today: can still be ordered
        meal_day("2026-06-15", ordered=False, orderable=False),  # tomorrow: the deadline is over
    ]
    await setup_integration(hass, stack, async_get_meals=meals)
    fired = results(hass)
    inputs = {
        "status_today": [STATUS_TODAY],
        "status_tomorrow": [STATUS_TOMORROW],
        "notify_action": user_action(),
    }
    await start(hass, "tagesbriefing.yaml", inputs)
    await at(hass, freezer, "2026-06-14T07:00:00")
    assert len(fired) == 1
    assert fired[0].data["message"].split("\n") == [
        "vorname-1 heute: noch nichts bestellt, Bestellen ist noch möglich",
        "vorname-1 morgen: nichts bestellt, die Bestellfrist ist vorbei",
    ]


# ---------------------------------------------------------------------------- bestellfrist_erinnerung


def deadline_event(**override) -> dict:
    """What the integration fires 2 hours before a deadline of "1 day before at 11:00"."""
    data = {
        "child": "Anna",
        "child_id": 1,
        "day": "2026-10-29",
        "days_ahead": 1,
        "weekday": 3,
        "deadline": "2026-10-28T11:00:00+01:00",
        "minutes_left": 120,
        "fresh": True,
    }
    return data | override


def deadline_action() -> list[dict]:
    return user_action(
        child="{{ child }}",
        label="{{ day_label }}",
        left="{{ time_left }}",
        at="{{ deadline_time }}",
        fresh="{{ fresh }}",
    )


async def test_deadline_reminder_says_how_long_is_left_and_for_which_day(hass) -> None:
    fired = results(hass)
    await start(hass, "bestellfrist_erinnerung.yaml", {"notify_action": deadline_action()})
    hass.bus.async_fire("kitaplus_order_deadline", deadline_event())
    await hass.async_block_till_done()
    assert len(fired) == 1
    data = fired[0].data
    assert (
        data["message"]
        == "Bestellfrist in 2 Std. (bis 11:00 Uhr): Für Anna ist für morgen noch kein Essen bestellt."
    )
    assert (data["child"], data["label"], data["left"], data["at"], data["fresh"]) == (
        "Anna",
        "morgen",
        "2 Std.",
        "11:00",
        True,
    )


async def test_deadline_reminder_wording_for_today_a_weekday_and_short_times(hass) -> None:
    fired = results(hass)
    await start(hass, "bestellfrist_erinnerung.yaml", {"notify_action": deadline_action()})
    for override in (
        {"days_ahead": 0, "minutes_left": 45},
        {"days_ahead": 4, "weekday": 0, "minutes_left": 150},
        {"child": None, "minutes_left": 60},
    ):
        hass.bus.async_fire("kitaplus_order_deadline", deadline_event(**override))
    await hass.async_block_till_done()
    labels = [(e.data["label"], e.data["left"], e.data["child"]) for e in fired]
    assert labels == [
        ("heute", "45 Min.", "Anna"),
        ("am Montag", "2 Std. 30 Min.", "Anna"),
        ("morgen", "1 Std.", "dein Kind"),
    ]


async def test_deadline_reminder_reaches_every_child_in_order(hass) -> None:
    fired = results(hass)
    await start(hass, "bestellfrist_erinnerung.yaml", {"notify_action": deadline_action()})
    for name in ("Anna", "Ben", "Cleo"):
        hass.bus.async_fire("kitaplus_order_deadline", deadline_event(child=name))
    await hass.async_block_till_done()
    assert [e.data["child"] for e in fired] == ["Anna", "Ben", "Cleo"], "mode queued: none is lost"


async def test_deadline_reminder_blueprint_works_with_the_real_integration_event(
    hass, stack, freezer
) -> None:
    """End to end with the rule of the user's Kita: the integration fires, the blueprint writes."""
    await at(hass, freezer, "2026-10-27T20:00:00")
    options = {"order_deadline_days": 1, "order_deadline_time": "11:00:00", "reminder_lead_minutes": 120}
    meals = [meal_day("2026-10-29", ordered=False, orderable=True)]
    await setup_integration(hass, stack, entry=make_entry(options), async_get_meals=meals)
    fired = results(hass)
    await start(hass, "bestellfrist_erinnerung.yaml", {"notify_action": deadline_action()})
    await at(hass, freezer, "2026-10-28T09:00:00")
    assert len(fired) == 1
    assert fired[0].data["message"] == (
        "Bestellfrist in 2 Std. (bis 11:00 Uhr): Für vorname-1 ist für morgen noch kein Essen bestellt."
    )
