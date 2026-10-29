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


# ---- every branch of the flows, including recovery after an error


def _ok_login():
    async def login(self, email, password, auth_code=None):
        self.set_tokens(Tokens("j", "r", 4102444800.0))

    return login


async def test_plain_sign_in_creates_the_entry(hass: HomeAssistant) -> None:
    with patch(LOGIN, new=_ok_login()):
        result = await hass.config_entries.flow.async_configure((await _start(hass))["flow_id"], CREDS)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert "password" not in result["data"]


async def test_error_then_recovery_creates_the_entry(hass: HomeAssistant) -> None:
    """A connection problem is not a wrong password: the same form works again afterwards."""
    from custom_components.kitaplus.api.exceptions import KitaPlusApiError, KitaPlusConnectionError

    flow_id = (await _start(hass))["flow_id"]
    for error, key in (
        (KitaPlusConnectionError("down"), "cannot_connect"),
        (KitaPlusApiError("odd"), "unknown"),
    ):
        with patch(LOGIN, side_effect=error):
            result = await hass.config_entries.flow.async_configure(flow_id, CREDS)
        assert result["errors"] == {"base": key}
        assert result["description_placeholders"]["attempt"] == "0"  # never counted
    with patch(LOGIN, new=_ok_login()):
        result = await hass.config_entries.flow.async_configure(flow_id, CREDS)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_same_account_cannot_be_added_twice_and_does_not_touch_kitaplus(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id="a@b.de", data={"email": "a@b.de"}).add_to_hass(hass)
    with patch(LOGIN) as login:
        result = await hass.config_entries.flow.async_configure((await _start(hass))["flow_id"], CREDS)
    assert result["reason"] == "already_configured"
    login.assert_not_called()


async def test_wrong_two_factor_code_can_be_corrected(hass: HomeAssistant) -> None:
    from custom_components.kitaplus.api.exceptions import KitaPlusConnectionError

    calls = []

    async def login(self, email, password, auth_code=None):
        calls.append(auth_code)
        if auth_code is None or auth_code == "bad":
            raise KitaPlusTwoFactorRequired(1)
        self.set_tokens(Tokens("j", "r", 4102444800.0))

    with patch(LOGIN, new=login):
        flow_id = (await _start(hass))["flow_id"]
        await hass.config_entries.flow.async_configure(flow_id, CREDS)
        wrong = await hass.config_entries.flow.async_configure(flow_id, {"auth_code": "bad"})
        assert wrong["errors"] == {"base": "invalid_code"}
    with patch(LOGIN, side_effect=KitaPlusConnectionError("down")):
        down = await hass.config_entries.flow.async_configure(flow_id, {"auth_code": "x"})
        assert down["errors"] == {"base": "cannot_connect"}
    with patch(LOGIN, new=login):
        done = await hass.config_entries.flow.async_configure(flow_id, {"auth_code": "000000"})
    assert done["type"] is FlowResultType.CREATE_ENTRY


async def test_two_factor_failures_also_stop_the_flow(hass: HomeAssistant) -> None:
    async def login(self, email, password, auth_code=None):
        if auth_code is None:
            raise KitaPlusTwoFactorRequired(2)
        raise KitaPlusAuthError("rejected", server_message="Falscher Code")

    with patch(LOGIN, new=login):
        flow_id = (await _start(hass))["flow_id"]
        await hass.config_entries.flow.async_configure(flow_id, CREDS)
        await hass.config_entries.flow.async_configure(flow_id, {"auth_code": "1"})
        result = await hass.config_entries.flow.async_configure(flow_id, {"auth_code": "2"})
    assert result["reason"] == "too_many_attempts"


def _reauth_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="a@b.de",
        data={"email": "A@B.de", "client_id": "cid", "refresh_token": "old", "refresh_expires": 1},
    )
    entry.add_to_hass(hass)
    return entry


async def test_reauth_with_the_right_password_renews_the_session(hass: HomeAssistant) -> None:
    entry = _reauth_entry(hass)
    with patch(LOGIN, new=_ok_login()) as _:
        flow = await entry.start_reauth_flow(hass)
        assert flow["step_id"] == "reauth_confirm"
        assert flow["description_placeholders"]["email"] == "A@B.de"
        done = await hass.config_entries.flow.async_configure(flow["flow_id"], {"password": "pw"})
    assert done["reason"] == "reauth_successful"
    assert entry.data["refresh_token"] == "r"
    assert "password" not in entry.data


async def test_reauth_wrong_password_is_counted_and_then_paused(hass: HomeAssistant) -> None:
    entry = _reauth_entry(hass)
    wrong = KitaPlusAuthError("rejected", server_message="Falsches Passwort")
    with patch(LOGIN, side_effect=wrong) as login:
        flow = await entry.start_reauth_flow(hass)
        first = await hass.config_entries.flow.async_configure(flow["flow_id"], {"password": "x"})
        assert first["errors"] == {"base": "invalid_auth"}
        second = await hass.config_entries.flow.async_configure(flow["flow_id"], {"password": "y"})
        assert second["reason"] == "too_many_attempts"
    assert login.call_count == 2


async def test_reauth_with_two_factor(hass: HomeAssistant) -> None:
    entry = _reauth_entry(hass)

    async def login(self, email, password, auth_code=None):
        if auth_code is None:
            raise KitaPlusTwoFactorRequired(1)
        self.set_tokens(Tokens("j", "fresh", 4102444800.0))

    with patch(LOGIN, new=login):
        flow = await entry.start_reauth_flow(hass)
        step = await hass.config_entries.flow.async_configure(flow["flow_id"], {"password": "pw"})
        assert step["step_id"] == "two_factor"
        done = await hass.config_entries.flow.async_configure(flow["flow_id"], {"auth_code": "000000"})
    assert done["reason"] == "reauth_successful"
    assert entry.data["refresh_token"] == "fresh"


async def test_reauth_is_refused_during_the_pause(hass: HomeAssistant) -> None:
    entry = _reauth_entry(hass)
    wrong = KitaPlusAuthError("rejected", server_message="Falsches Passwort")
    with patch(LOGIN, side_effect=wrong) as login:
        flow = await entry.start_reauth_flow(hass)
        await hass.config_entries.flow.async_configure(flow["flow_id"], {"password": "x"})
        stopped = await hass.config_entries.flow.async_configure(flow["flow_id"], {"password": "y"})
        assert stopped["reason"] == "too_many_attempts"
        login.reset_mock()
        again = await entry.start_reauth_flow(hass)  # a brand new dialog must not reset the counter
        result = await hass.config_entries.flow.async_configure(again["flow_id"], {"password": "z"})
    assert result["reason"] == "cooling_down"
    login.assert_not_called()


async def test_options_flow_saves_a_valid_interval(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="a@b.de", data={"email": "a@b.de", "client_id": "c"})
    entry.add_to_hass(hass)
    form = await hass.config_entries.options.async_init(entry.entry_id)
    assert form["type"] is FlowResultType.FORM
    done = await hass.config_entries.options.async_configure(form["flow_id"], {"scan_interval": 60})
    assert done["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["scan_interval"] == 60
