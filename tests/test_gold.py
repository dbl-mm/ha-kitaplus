"""Gold-level behaviour: stable account id, reconfigure, dynamic and stale devices, diagnostics."""

import copy
from contextlib import ExitStack
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kitaplus import async_remove_config_entry_device
from custom_components.kitaplus.api.client import Tokens
from custom_components.kitaplus.api.exceptions import KitaPlusAuthError, KitaPlusMaintenanceError
from custom_components.kitaplus.const import DOMAIN

from .common import CLIENT, api_answers, make_entry, setup_integration

LOGIN = f"{CLIENT}.async_login"
ACCOUNT = f"{CLIENT}.async_get_account_id"


def _ok_login():
    async def login(self, email, password, auth_code=None):
        self.set_tokens(Tokens("j", "new", 4102444800.0))

    return login


async def test_new_entry_is_recognised_by_the_account_id_not_the_email(hass: HomeAssistant) -> None:
    with patch(LOGIN, new=_ok_login()):
        flow = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], {"email": "A@B.de", "password": "pw"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.unique_id == "4242" and entry.data["account_id"] == 4242


async def test_same_account_under_another_email_is_still_a_duplicate(hass: HomeAssistant) -> None:
    MockConfigEntry(
        domain=DOMAIN, unique_id="4242", data={"email": "old@b.de", "account_id": 4242}
    ).add_to_hass(hass)
    with patch(LOGIN, new=_ok_login()):
        flow = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], {"email": "new@b.de", "password": "pw"}
        )
    assert result["reason"] == "already_configured"


async def test_legacy_entry_is_switched_to_the_account_id_once(hass: HomeAssistant) -> None:
    with ExitStack() as stack:
        entry = await setup_integration(hass, stack)  # make_entry() has no account_id, like a 0.1.0 entry
    assert entry.state is ConfigEntryState.LOADED
    assert entry.unique_id == "4242" and entry.data["account_id"] == 4242


async def test_reconfigure_can_change_the_email_of_the_same_account(hass: HomeAssistant) -> None:
    entry = make_entry(account_id=4242)
    with ExitStack() as stack:
        await setup_integration(hass, stack, entry=entry)
        with patch(LOGIN, new=_ok_login()):
            form = await entry.start_reconfigure_flow(hass)
            assert form["step_id"] == "reconfigure"
            done = await hass.config_entries.flow.async_configure(
                form["flow_id"], {"email": "Neu@B.de", "password": "pw"}
            )
            await hass.async_block_till_done()
    assert done["reason"] == "reconfigure_successful"
    assert entry.data["email"] == "Neu@B.de" and entry.data["refresh_token"] == "new"


async def test_reconfigure_and_reauth_refuse_a_different_account(hass: HomeAssistant) -> None:
    entry = make_entry(account_id=1111)  # the entry belongs to account 1111, the login yields 4242
    entry.add_to_hass(hass)
    with patch(LOGIN, new=_ok_login()):
        form = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            form["flow_id"], {"email": "x@b.de", "password": "pw"}
        )
        assert result["reason"] == "wrong_account"
        reauth = await entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(reauth["flow_id"], {"password": "pw"})
        assert result["reason"] == "wrong_account"
    assert entry.data["email"] == "a@b.de" and entry.data["refresh_token"] == "r"  # nothing changed


async def test_reconfigure_wrong_password_is_counted_and_stops(hass: HomeAssistant) -> None:
    entry = make_entry(account_id=4242)
    entry.add_to_hass(hass)
    wrong = KitaPlusAuthError("no", server_message="Falsches Passwort")
    with patch(LOGIN, side_effect=wrong) as login:
        form = await entry.start_reconfigure_flow(hass)
        first = await hass.config_entries.flow.async_configure(
            form["flow_id"], {"email": "a@b.de", "password": "x"}
        )
        assert first["errors"] == {"base": "invalid_auth"}
        second = await hass.config_entries.flow.async_configure(
            form["flow_id"], {"email": "a@b.de", "password": "y"}
        )
        assert second["reason"] == "too_many_attempts"
        again = await entry.start_reconfigure_flow(hass)
        paused = await hass.config_entries.flow.async_configure(
            again["flow_id"], {"email": "a@b.de", "password": "z"}
        )
    assert paused["reason"] == "cooling_down" and login.call_count == 2


def _second_child():
    kids = api_answers()["async_get_children"]
    child = copy.deepcopy(kids[0])
    child.update({"id": 5555, "vorname": "zweites-kind"})
    child["elternkonto"] = {"id": 5555}
    return [*kids, child]


async def test_a_new_child_appears_without_a_reload_and_is_never_added_twice(hass: HomeAssistant) -> None:
    with ExitStack() as stack:
        entry = await setup_integration(hass, stack)
        assert hass.states.get("sensor.zweites_kind_meal_today") is None
        stack.enter_context(patch(f"{CLIENT}.async_get_children", return_value=_second_child()))
        entry.runtime_data._children_at = None  # the child list is only re-read once a day
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get("sensor.zweites_kind_meal_today") is not None
        assert hass.states.get("calendar.zweites_kind_ordered_meals") is not None
        count = len(hass.states.async_entity_ids())
        await entry.runtime_data.async_refresh()  # nothing new: no duplicates
        await hass.async_block_till_done()
    assert len(hass.states.async_entity_ids()) == count


async def test_a_child_that_disappears_loses_its_device(hass: HomeAssistant) -> None:
    registry = dr.async_get(hass)
    with ExitStack() as stack:
        entry = await setup_integration(hass, stack, async_get_children=_second_child())
        second = (DOMAIN, f"{entry.entry_id}_5555")
        assert registry.async_get_device(identifiers={second}) is not None
        stack.enter_context(
            patch(f"{CLIENT}.async_get_children", return_value=api_answers()["async_get_children"])
        )
        entry.runtime_data._children_at = None  # force the daily children refresh
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert registry.async_get_device(identifiers={second}) is None
        assert (
            registry.async_get_device(identifiers={(DOMAIN, entry.entry_id)}) is not None
        )  # the account stays


async def test_an_empty_children_answer_does_not_wipe_the_devices(hass: HomeAssistant) -> None:
    registry = dr.async_get(hass)
    with ExitStack() as stack:
        entry = await setup_integration(hass, stack)
        stack.enter_context(patch(f"{CLIENT}.async_get_children", return_value=[]))
        entry.runtime_data._children_at = None
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
    assert len(dr.async_entries_for_config_entry(registry, entry.entry_id)) >= 2


async def test_only_stale_devices_can_be_removed_by_the_user(hass: HomeAssistant) -> None:
    registry = dr.async_get(hass)
    with ExitStack() as stack:
        entry = await setup_integration(hass, stack)
        account = registry.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
        child_id = entry.runtime_data.data.children[0]["id"]
        active = registry.async_get_device(identifiers={(DOMAIN, f"{entry.entry_id}_{child_id}")})
        stale = registry.async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={(DOMAIN, f"{entry.entry_id}_9999")}
        )
        assert not await async_remove_config_entry_device(hass, entry, account)
        assert not await async_remove_config_entry_device(hass, entry, active)
        assert await async_remove_config_entry_device(hass, entry, stale)


async def test_devices_describe_themselves(hass: HomeAssistant) -> None:
    with ExitStack() as stack:
        entry = await setup_integration(hass, stack)
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device.model == "Eltern-App" and device.manufacturer == "kitaplus"
    assert device.configuration_url == "https://eltern.kitaplus.de"


async def test_session_sensor_is_a_diagnostic_entity_and_off_by_default(hass: HomeAssistant) -> None:
    with ExitStack() as stack:
        entry = await setup_integration(hass, stack)
        registry = er.async_get(hass)
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_session_valid_until")
        assert entity_id is not None
        item = registry.async_get(entity_id)
        assert item.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        assert item.entity_category.value == "diagnostic"
        registry.async_update_entity(entity_id, disabled_by=None)
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
    assert hass.states.get(entity_id).state.startswith("2100-01-01")  # the stored refresh expiry


async def test_errors_carry_translation_keys_for_the_user_interface(hass: HomeAssistant) -> None:
    with ExitStack() as stack:
        entry = await setup_integration(hass, stack)
        coordinator = entry.runtime_data
        for error, key in (
            (KitaPlusMaintenanceError("x"), "maintenance"),
            (KeyError("k"), "unexpected_format"),
        ):
            stack.enter_context(patch(f"{CLIENT}.async_get_board", side_effect=error))
            await coordinator.async_refresh()
            assert coordinator.last_exception.translation_key == key
            assert coordinator.last_exception.translation_domain == DOMAIN


async def test_problems_while_reading_the_account_id_are_not_counted_as_wrong_passwords(
    hass: HomeAssistant,
) -> None:
    from custom_components.kitaplus.api.exceptions import KitaPlusApiError, KitaPlusConnectionError

    cases = (
        (KitaPlusMaintenanceError("x"), "maintenance"),
        (KitaPlusConnectionError("x"), "cannot_connect"),
        (KitaPlusApiError("x"), "unknown"),
        (KeyError("id"), "unknown"),
    )
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    for error, key in cases:
        with patch(LOGIN, new=_ok_login()), patch(ACCOUNT, side_effect=error):
            result = await hass.config_entries.flow.async_configure(
                flow["flow_id"], {"email": "a@b.de", "password": "pw"}
            )
        assert result["errors"] == {"base": key}
        assert result["description_placeholders"]["attempt"] == "0"


async def test_a_login_that_yields_no_session_is_an_unknown_error(hass: HomeAssistant) -> None:
    async def login(self, email, password, auth_code=None):
        return None  # answered, but no tokens were stored

    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    with patch(LOGIN, new=login):
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], {"email": "a@b.de", "password": "pw"}
        )
    assert result["errors"] == {"base": "unknown"}


async def test_reconfigure_with_two_factor(hass: HomeAssistant) -> None:
    from custom_components.kitaplus.api.exceptions import KitaPlusTwoFactorRequired

    entry = make_entry(account_id=4242)
    entry.add_to_hass(hass)

    async def login(self, email, password, auth_code=None):
        if auth_code is None:
            raise KitaPlusTwoFactorRequired(1)
        self.set_tokens(Tokens("j", "after-2fa", 4102444800.0))

    with patch(LOGIN, new=login):
        form = await entry.start_reconfigure_flow(hass)
        step = await hass.config_entries.flow.async_configure(
            form["flow_id"], {"email": "a@b.de", "password": "pw"}
        )
        assert step["step_id"] == "two_factor"
        done = await hass.config_entries.flow.async_configure(form["flow_id"], {"auth_code": "000000"})
    assert done["reason"] == "reconfigure_successful"
    assert entry.data["refresh_token"] == "after-2fa"
