"""Config flow for KitaPlus.

Transparency rules:
* every submit is exactly ONE login attempt, never an automatic retry;
* the user is told which attempt this is and that KitaPlus can lock the account;
* KitaPlus' own message is shown unchanged;
* after MAX_ATTEMPTS failed attempts the flow stops, so nobody locks themselves out by trial and error.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    SOURCE_USER,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TimeSelector,
)

from .api.client import KitaPlusClient
from .api.exceptions import (
    KitaPlusAuthError,
    KitaPlusConnectionError,
    KitaPlusError,
    KitaPlusMaintenanceError,
    KitaPlusTwoFactorRequired,
)
from .const import (
    CONF_ACCOUNT_ID,
    CONF_AUTH_CODE,
    CONF_CLIENT_ID,
    CONF_DEADLINE_DAYS,
    CONF_DEADLINE_TIME,
    CONF_DEADLINE_WORKDAYS,
    CONF_EMAIL,
    CONF_LEAD_MINUTES,
    CONF_PASSWORD,
    CONF_REFRESH_EXPIRES,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    DEFAULT_DEADLINE_TIME,
    DEFAULT_LEAD_MINUTES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGIN_COOLDOWN_MINUTES,
    MAX_DEADLINE_DAYS,
    MAX_LOGIN_ATTEMPTS,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)


def _failed(hass: HomeAssistant, account: str) -> tuple[int, float]:
    """Failed sign-ins (count, time of the last one) for an account, in memory only."""
    count, last = hass.data.get(DOMAIN, {}).get("failed", {}).get(account, (0, 0.0))
    if time.time() - last > LOGIN_COOLDOWN_MINUTES * 60:
        return 0, 0.0
    return count, last


def _record_failure(hass: HomeAssistant, account: str) -> int:
    count, _ = _failed(hass, account)
    hass.data.setdefault(DOMAIN, {}).setdefault("failed", {})[account] = (count + 1, time.time())
    return count + 1


def _clear_failures(hass: HomeAssistant, account: str) -> None:
    hass.data.get(DOMAIN, {}).get("failed", {}).pop(account, None)


class KitaPlusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowWithReload:
        return KitaPlusOptionsFlow()

    def __init__(self) -> None:
        self._email = ""  # exactly as typed: KitaPlus may be case sensitive
        self._account = ""  # lower case, only used to recognise the same account
        self._password = ""
        self._client_id = uuid.uuid4().hex
        self._failed_attempts = 0
        self._server_message = ""

    def _placeholders(self) -> dict[str, str]:
        return {
            "email": self._email,
            "server_message": self._server_message or "-",
            "attempt": str(self._failed_attempts),
            "max": str(MAX_LOGIN_ATTEMPTS),
            "minutes": str(LOGIN_COOLDOWN_MINUTES),
        }

    async def _async_try_login(self, auth_code: str | None) -> tuple[dict[str, Any] | None, str | None]:
        """One single login attempt. Returns (entry data, error key)."""
        client = KitaPlusClient(async_get_clientsession(self.hass), self._client_id)
        try:
            await client.async_login(self._email, self._password, auth_code)
        except KitaPlusTwoFactorRequired:
            return None, "two_factor"
        except KitaPlusAuthError as err:
            self._failed_attempts = _record_failure(self.hass, self._account)
            self._server_message = err.server_message or ""
            return None, "account_locked" if err.locked else "invalid_auth"
        except KitaPlusMaintenanceError:
            return None, "maintenance"
        except KitaPlusConnectionError:
            return None, "cannot_connect"
        except KitaPlusError:
            return None, "unknown"
        tokens = client.tokens
        if tokens is None:
            return None, "unknown"
        try:
            account_id = await client.async_get_account_id()
        except KitaPlusMaintenanceError:
            return None, "maintenance"
        except KitaPlusConnectionError:
            return None, "cannot_connect"
        except (KitaPlusError, KeyError, TypeError, ValueError):
            return None, "unknown"
        _clear_failures(self.hass, self._account)
        return {
            CONF_EMAIL: self._email,
            CONF_ACCOUNT_ID: account_id,
            CONF_CLIENT_ID: self._client_id,
            CONF_REFRESH_TOKEN: tokens.refresh_token,
            CONF_REFRESH_EXPIRES: tokens.refresh_expires,
        }, None

    async def _async_finish(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Create, update or reject the entry once the login worked."""
        account = str(data[CONF_ACCOUNT_ID])
        if self.source == SOURCE_USER:
            await self.async_set_unique_id(account)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=self._email, data=data)
        entry = self._get_reauth_entry() if self.source == SOURCE_REAUTH else self._get_reconfigure_entry()
        known = entry.data.get(CONF_ACCOUNT_ID)
        if known is not None and str(known) != account:
            return self.async_abort(reason="wrong_account")  # another KitaPlus user, keep the entry as it is
        return self.async_update_reload_and_abort(
            entry,
            unique_id=account,
            data_updates=data,
            reason="reauth_successful" if self.source == SOURCE_REAUTH else "reconfigure_successful",
        )

    def _cooling_down(self) -> ConfigFlowResult | None:
        """Refuse to touch KitaPlus again right after too many failures, even in a new flow."""
        self._failed_attempts, _ = _failed(self.hass, self._account)
        if self._failed_attempts >= MAX_LOGIN_ATTEMPTS:
            return self.async_abort(reason="cooling_down", description_placeholders=self._placeholders())
        return None

    def _stop_or_none(self, error: str | None) -> ConfigFlowResult | None:
        """Abort instead of offering another attempt when that would be risky."""
        if error == "account_locked":
            return self.async_abort(reason="account_locked", description_placeholders=self._placeholders())
        if error == "invalid_auth" and self._failed_attempts >= MAX_LOGIN_ATTEMPTS:
            return self.async_abort(reason="too_many_attempts", description_placeholders=self._placeholders())
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._email = user_input[CONF_EMAIL].strip()
            self._account = self._email.lower()
            self._password = user_input[CONF_PASSWORD]
            if any(
                e.data.get(CONF_EMAIL, "").lower() == self._account for e in self._async_current_entries()
            ):
                return self.async_abort(reason="already_configured")  # no request to KitaPlus needed
            if stop := self._cooling_down():
                return stop
            data, error = await self._async_try_login(None)
            if error == "two_factor":
                return await self.async_step_two_factor()
            if data:
                return await self._async_finish(data)
            if stop := self._stop_or_none(error):
                return stop
            errors["base"] = error or "unknown"
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str}),
            errors=errors,
            description_placeholders=self._placeholders(),
        )

    async def async_step_two_factor(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data, error = await self._async_try_login(user_input[CONF_AUTH_CODE].strip())
            if data:
                return await self._async_finish(data)
            if stop := self._stop_or_none(error):
                return stop
            errors["base"] = (
                "invalid_code" if error in ("two_factor", "invalid_auth") else (error or "unknown")
            )
        return self.async_show_form(
            step_id="two_factor",
            data_schema=vol.Schema({vol.Required(CONF_AUTH_CODE): str}),
            errors=errors,
            description_placeholders=self._placeholders(),
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        self._email = entry_data[CONF_EMAIL]
        self._account = self._email.lower()
        self._client_id = entry_data[CONF_CLIENT_ID]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._password = user_input[CONF_PASSWORD]
            if stop := self._cooling_down():
                return stop
            data, error = await self._async_try_login(None)
            if error == "two_factor":
                return await self.async_step_two_factor()
            if data:
                return await self._async_finish(data)
            if stop := self._stop_or_none(error):
                return stop
            errors["base"] = error or "unknown"
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders=self._placeholders(),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change the e-mail address or sign in again. Only the same KitaPlus account is accepted."""
        entry = self._get_reconfigure_entry()
        self._client_id = entry.data[CONF_CLIENT_ID]
        errors: dict[str, str] = {}
        if user_input is not None:
            self._email = user_input[CONF_EMAIL].strip()
            self._account = self._email.lower()
            self._password = user_input[CONF_PASSWORD]
            if stop := self._cooling_down():
                return stop
            data, error = await self._async_try_login(None)
            if error == "two_factor":
                return await self.async_step_two_factor()
            if data:
                return await self._async_finish(data)
            if stop := self._stop_or_none(error):
                return stop
            errors["base"] = error or "unknown"
        self._email = self._email or entry.data[CONF_EMAIL]
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL, default=self._email): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
            description_placeholders=self._placeholders(),
        )


class KitaPlusOptionsFlow(OptionsFlowWithReload):
    """Polling interval and the Kita's order deadline."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            data = dict(user_input)
            if CONF_DEADLINE_DAYS in data:
                data[CONF_DEADLINE_DAYS] = int(data[CONF_DEADLINE_DAYS])
            data[CONF_LEAD_MINUTES] = int(data[CONF_LEAD_MINUTES])
            return self.async_create_entry(data=data)
        current = self.config_entry.options
        days = current.get(CONF_DEADLINE_DAYS)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL, default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)),
                    vol.Optional(CONF_DEADLINE_DAYS, description={"suggested_value": days}): NumberSelector(
                        NumberSelectorConfig(
                            min=0, max=MAX_DEADLINE_DAYS, step=1, mode=NumberSelectorMode.BOX
                        )
                    ),
                    vol.Optional(
                        CONF_DEADLINE_TIME, default=current.get(CONF_DEADLINE_TIME, DEFAULT_DEADLINE_TIME)
                    ): TimeSelector(),
                    vol.Optional(
                        CONF_DEADLINE_WORKDAYS, default=current.get(CONF_DEADLINE_WORKDAYS, False)
                    ): BooleanSelector(),
                    vol.Optional(
                        CONF_LEAD_MINUTES, default=current.get(CONF_LEAD_MINUTES, DEFAULT_LEAD_MINUTES)
                    ): NumberSelector(
                        NumberSelectorConfig(min=0, max=1440, step=15, mode=NumberSelectorMode.BOX)
                    ),
                }
            ),
        )
