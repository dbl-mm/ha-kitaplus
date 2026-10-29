"""The user must always understand what happened during sign-in."""

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kitaplus.api.client import Tokens
from custom_components.kitaplus.api.exceptions import (
    KitaPlusAuthError,
    KitaPlusMaintenanceError,
    KitaPlusTwoFactorRequired,
)
from custom_components.kitaplus.const import DOMAIN

LOGIN = "custom_components.kitaplus.api.client.KitaPlusClient.async_login"
CREDS = {"email": "A@B.de", "password": "pw"}


async def _start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})


async def test_wrong_password_tells_attempt_and_server_message(hass: HomeAssistant) -> None:
    wrong = KitaPlusAuthError("rejected", server_message="Falsches Passwort")
    with patch(LOGIN, side_effect=wrong) as login:
        result = await hass.config_entries.flow.async_configure((await _start(hass))["flow_id"], CREDS)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert result["description_placeholders"]["attempt"] == "1"
    assert result["description_placeholders"]["server_message"] == "Falsches Passwort"
    assert login.call_count == 1


async def test_flow_stops_after_second_failed_attempt(hass: HomeAssistant) -> None:
    wrong = KitaPlusAuthError("rejected", server_message="Falsches Passwort")
    with patch(LOGIN, side_effect=wrong) as login:
        flow_id = (await _start(hass))["flow_id"]
        await hass.config_entries.flow.async_configure(flow_id, CREDS)
        result = await hass.config_entries.flow.async_configure(flow_id, CREDS)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "too_many_attempts"
    assert login.call_count == 2  # never more than MAX attempts


async def test_locked_account_aborts_immediately_with_server_text(hass: HomeAssistant) -> None:
    locked = KitaPlusAuthError("rejected", server_message="Ihr Benutzerzugang wurde gesperrt")
    with patch(LOGIN, side_effect=locked) as login:
        result = await hass.config_entries.flow.async_configure((await _start(hass))["flow_id"], CREDS)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "account_locked"
    assert "gesperrt" in result["description_placeholders"]["server_message"]
    assert login.call_count == 1


async def test_maintenance_is_not_counted_as_failed_attempt(hass: HomeAssistant) -> None:
    with patch(LOGIN, side_effect=KitaPlusMaintenanceError("maintenance")):
        result = await hass.config_entries.flow.async_configure((await _start(hass))["flow_id"], CREDS)
    assert result["errors"] == {"base": "maintenance"}
    assert result["description_placeholders"]["attempt"] == "0"


async def test_two_factor_step_then_success(hass: HomeAssistant) -> None:
    async def fake_login(self, email, password, auth_code=None):
        if auth_code is None:
            raise KitaPlusTwoFactorRequired(1)
        self.set_tokens(Tokens("j", "r", 4102444800.0))

    with patch(LOGIN, new=fake_login):
        flow_id = (await _start(hass))["flow_id"]
        step = await hass.config_entries.flow.async_configure(flow_id, CREDS)
        assert step["step_id"] == "two_factor"
        result = await hass.config_entries.flow.async_configure(flow_id, {"auth_code": "000000"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["email"] == "A@B.de"  # exactly as typed, KitaPlus may be case sensitive
    assert result["data"]["refresh_token"] == "r"
    assert "password" not in result["data"]  # the password is never stored


async def test_runtime_auth_failure_creates_visible_repair_issue(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="a@b.de",
        data={
            "email": "a@b.de",
            "password": "pw",
            "client_id": "c",
            "refresh_token": "r",
            "refresh_expires": 4102444800,
        },
    )
    entry.add_to_hass(hass)
    err = KitaPlusAuthError("x", server_message="Ihr Benutzerzugang wurde gesperrt")
    with patch("custom_components.kitaplus.api.client.KitaPlusClient.async_get_children", side_effect=err):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"auth_{entry.entry_id}")
    assert issue is not None
    assert issue.translation_key == "account_locked"
    assert "gesperrt" in issue.translation_placeholders["server_message"]


async def test_missing_token_means_reauth_and_never_a_silent_login(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="a@b.de", data={"email": "a@b.de", "client_id": "c"})
    entry.add_to_hass(hass)
    with patch(LOGIN) as login:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    login.assert_not_called()
    assert any(f["context"]["source"] == "reauth" for f in hass.config_entries.flow.async_progress())


async def test_options_reject_intervals_below_15_minutes(hass: HomeAssistant) -> None:
    import voluptuous as vol

    entry = MockConfigEntry(domain=DOMAIN, unique_id="a@b.de", data={"email": "a@b.de", "client_id": "c"})
    entry.add_to_hass(hass)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    try:
        await hass.config_entries.options.async_configure(flow["flow_id"], {"scan_interval": 5})
    except vol.Invalid:
        return
    raise AssertionError("an interval of 5 minutes must be rejected")


async def test_login_name_is_sent_exactly_as_typed(hass: HomeAssistant) -> None:
    seen = {}

    async def fake_login(self, email, password, auth_code=None):
        seen["email"] = email
        self.set_tokens(Tokens("j", "r", 4102444800.0))

    with patch(LOGIN, new=fake_login):
        await hass.config_entries.flow.async_configure(
            (await _start(hass))["flow_id"], {"email": "  Mixed.Case@Example.DE ", "password": "pw"}
        )
    assert seen["email"] == "Mixed.Case@Example.DE"  # stripped, but never lower-cased


async def test_restarting_the_flow_does_not_reset_the_failure_counter(hass: HomeAssistant) -> None:
    wrong = KitaPlusAuthError("rejected", server_message="Falsches Passwort")
    with patch(LOGIN, side_effect=wrong) as login:
        first = (await _start(hass))["flow_id"]
        await hass.config_entries.flow.async_configure(first, CREDS)
        await hass.config_entries.flow.async_configure(first, CREDS)  # second failure -> abort
        result = await hass.config_entries.flow.async_configure((await _start(hass))["flow_id"], CREDS)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cooling_down"
    assert login.call_count == 2  # the third attempt never reached KitaPlus
