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
    assert "'refresh_token': 'r'" not in text
    for child in entry.runtime_data.data.children:
        assert str(child["id"]) not in text.replace("**REDACTED**", "")
