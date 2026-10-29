"""Load the whole integration against the anonymised fixtures (no network)."""

from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kitaplus.api.exceptions import KitaPlusAuthError
from custom_components.kitaplus.const import DOMAIN

from .conftest import load

CLIENT = "custom_components.kitaplus.api.client.KitaPlusClient"


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="a@b.de",
        data={
            "email": "a@b.de",
            "password": "pw",
            "client_id": "cid",
            "refresh_token": "r",
            "refresh_expires": 4102444800,
        },
    )


def _patches():
    days = load("bestelldaten")["data"][0]["tage"]
    return [
        patch(f"{CLIENT}.async_get_children", return_value=load("get_einrichtungen_kinder")["kinder"]),
        patch(f"{CLIENT}.async_get_events", return_value=load("termine")["data"]),
        patch(f"{CLIENT}.async_get_meals", return_value=days),
        patch(f"{CLIENT}.async_get_board", return_value=load("schwarzesbrett")["data"]),
        patch(f"{CLIENT}.async_get_messages", return_value=load("getNachrichten")["data"]),
        patch(
            f"{CLIENT}.async_get_accounts",
            return_value=load("get_einrichtungen_kinder")["verpflegungskonten"],
        ),
    ]


async def test_setup_creates_entities(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    ps = _patches()
    for p in ps:
        p.start()
    try:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    finally:
        for p in ps:
            p.stop()

    assert entry.state is ConfigEntryState.LOADED
    ids = hass.states.async_entity_ids()
    assert any(i.startswith("calendar.") for i in ids)
    assert any(i.startswith("binary_sensor.") for i in ids)
    assert len([i for i in ids if i.startswith("sensor.")]) >= 5
    assert hass.states.get("sensor.kitaplus_mailbox").state == str(len(load("getNachrichten")["data"]))


async def test_auth_error_starts_reauth_and_does_not_retry(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    with (
        patch(f"{CLIENT}.async_get_children", side_effect=KitaPlusAuthError),
        patch(f"{CLIENT}.async_login") as login,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    login.assert_not_called()  # no automatic password login after a rejected token
    assert any(f["context"]["source"] == "reauth" for f in hass.config_entries.flow.async_progress())


async def test_events_spanning_two_months_are_not_duplicated(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    ps = _patches()
    for p in ps:
        p.start()
    try:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    finally:
        for p in ps:
            p.stop()
    coordinator = entry.runtime_data
    ids = [e["id"] for e in coordinator.data.events]
    assert len(ids) == len(set(ids))  # the same fixture is returned for both months


async def test_diagnostics_redacts_names_ids_and_tokens(hass: HomeAssistant) -> None:
    from custom_components.kitaplus.diagnostics import async_get_config_entry_diagnostics

    entry = _entry()
    entry.add_to_hass(hass)
    ps = _patches()
    for p in ps:
        p.start()
    try:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    finally:
        for p in ps:
            p.stop()
    text = str(await async_get_config_entry_diagnostics(hass, entry))
    assert "a@b.de" not in text
    assert str(entry.data["account_id"]) not in text.replace("**REDACTED**", "")
    data = await async_get_config_entry_diagnostics(hass, entry)
    for event in data["events"]:
        assert set(event) <= {"startdatum", "enddatum", "istSchliesstag", "istFeiertag"}, (
            "only a fixed set of fields"
        )
    assert all(set(child) <= {"istVppAktiv"} for child in data["children"])
    assert "'refresh_token': 'r'" not in text
    for child in entry.runtime_data.data.children:
        assert str(child["id"]) not in text.replace("**REDACTED**", "")


# ---- coordinator behaviour: errors, events, token persistence, unload


async def _setup_with(hass, **overrides):
    from contextlib import ExitStack

    from .common import setup_integration

    with ExitStack() as stack:
        entry = await setup_integration(hass, stack, **overrides)
    return entry


async def test_maintenance_and_format_errors_are_retried_not_treated_as_login_problems(
    hass: HomeAssistant,
) -> None:
    from custom_components.kitaplus.api.exceptions import KitaPlusApiError, KitaPlusMaintenanceError

    for error in (
        KitaPlusMaintenanceError("x"),
        KitaPlusApiError("x"),
        KeyError("kinder"),
        AttributeError("x"),
    ):
        entry = await _setup_with(hass, async_get_children=error)
        assert entry.state is ConfigEntryState.SETUP_RETRY
        assert not any(f["context"]["source"] == "reauth" for f in hass.config_entries.flow.async_progress())
        await hass.config_entries.async_remove(entry.entry_id)


async def test_new_posts_and_messages_fire_events_but_never_on_the_first_poll(hass: HomeAssistant) -> None:
    from contextlib import ExitStack

    from pytest_homeassistant_custom_component.common import async_capture_events

    from .common import setup_integration

    posts = load("schwarzesbrett")["data"]
    new_posts, new_messages = (
        async_capture_events(hass, "kitaplus_new_board_post"),
        async_capture_events(hass, "kitaplus_new_message"),
    )
    with ExitStack() as stack:
        entry = await setup_integration(hass, stack, async_get_board=posts[1:])
        assert not new_posts and not new_messages  # first poll: silence
        stack.enter_context(patch(f"{CLIENT}.async_get_board", return_value=posts))
        stack.enter_context(
            patch(
                f"{CLIENT}.async_get_messages",
                return_value=load("getNachrichten")["data"] + [{"id": 1, "nachricht": {"titel": "Neu"}}],
            )
        )
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
    assert len(new_posts) == 1
    assert [e.data["title"] for e in new_messages] == ["Neu"]


async def test_a_rotated_refresh_token_is_saved_in_the_entry(hass: HomeAssistant) -> None:
    from custom_components.kitaplus.api.client import Tokens

    entry = await _setup_with(hass)
    entry.runtime_data._save_tokens(Tokens("jwt", "rotated", 4102444801.0))
    assert entry.data["refresh_token"] == "rotated"
    assert entry.data["refresh_expires"] == 4102444801.0


async def test_second_poll_reuses_the_session_and_entry_unloads_cleanly(hass: HomeAssistant) -> None:
    from contextlib import ExitStack

    from .common import setup_integration

    with ExitStack() as stack:
        entry = await setup_integration(hass, stack)
        await entry.runtime_data.async_refresh()  # second poll
        assert entry.runtime_data.last_update_success
        assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_entities_become_unavailable_when_polling_fails(hass: HomeAssistant) -> None:
    from contextlib import ExitStack

    from custom_components.kitaplus.api.exceptions import KitaPlusConnectionError

    from .common import setup_integration

    with ExitStack() as stack:
        entry = await setup_integration(hass, stack)
        stack.enter_context(patch(f"{CLIENT}.async_get_board", side_effect=KitaPlusConnectionError("down")))
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
    assert hass.states.get("sensor.kitaplus_mailbox").state == "unavailable"


async def test_an_account_that_disappears_gives_an_unknown_balance(hass: HomeAssistant) -> None:
    from contextlib import ExitStack

    from .common import setup_integration

    with ExitStack() as stack:
        entry = await setup_integration(hass, stack)
        stack.enter_context(patch(f"{CLIENT}.async_get_accounts", return_value=[]))
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
    assert hass.states.get("sensor.kitaplus_meal_account_balance").state == "unknown"


async def test_meal_day_without_a_date_is_skipped(hass: HomeAssistant) -> None:
    entry = await _setup_with(hass, async_get_meals=[{"datum": None, "mahlzeitArten": []}])
    assert entry.state is ConfigEntryState.LOADED
