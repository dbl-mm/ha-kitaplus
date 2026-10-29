"""Data update coordinator for KitaPlus."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api.client import KitaPlusClient, Tokens
from .api.exceptions import KitaPlusAuthError, KitaPlusError, KitaPlusMaintenanceError
from .const import (
    CONF_EMAIL,
    CONF_REFRESH_EXPIRES,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_NEW_BOARD_POST,
    EVENT_NEW_MESSAGE,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

CHILDREN_REFRESH = timedelta(hours=24)
MEAL_DAYS_AHEAD = 14


@dataclass
class KitaPlusData:
    """Snapshot of everything we poll."""

    children: list[dict[str, Any]] = field(default_factory=list)
    board: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    accounts: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    meals: dict[int, list[dict[str, Any]]] = field(default_factory=dict)  # child id -> days


class KitaPlusCoordinator(DataUpdateCoordinator[KitaPlusData]):
    """Poll KitaPlus. Auth errors suspend polling until the user reauthenticates."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: KitaPlusClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
        )
        self.client = client
        client.set_token_listener(self._save_tokens)
        self._children: list[dict[str, Any]] = []
        self._children_at = None
        self._seen_board: set[int] | None = None
        self._seen_messages: set[int] | None = None

    @property
    def _issue_id(self) -> str:
        return f"auth_{self.config_entry.entry_id}"

    def _report_auth_problem(self, err: KitaPlusAuthError) -> None:
        """Tell the user openly in Settings > Repairs what happened and what to do."""
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self._issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key="account_locked" if err.locked else "auth_failed",
            translation_placeholders={
                "email": self.config_entry.data.get(CONF_EMAIL, ""),
                "server_message": err.server_message or "-",
            },
        )

    async def _async_ensure_session(self) -> None:
        """Use the stored refresh token. The password is never stored, so no silent re-login."""
        if self.client.tokens is not None:
            return
        data = self.config_entry.data
        if not data.get(CONF_REFRESH_TOKEN):
            raise ConfigEntryAuthFailed("No stored session, please sign in again")
        self.client.set_tokens(Tokens("", data[CONF_REFRESH_TOKEN], float(data.get(CONF_REFRESH_EXPIRES, 0))))

    async def _async_get_children(self) -> list[dict[str, Any]]:
        now = dt_util.utcnow()
        if not self._children or self._children_at is None or now - self._children_at > CHILDREN_REFRESH:
            self._children = await self.client.async_get_children()
            self._children_at = now
        return self._children

    async def _async_update_data(self) -> KitaPlusData:
        today = dt_util.now().date()
        try:
            await self._async_ensure_session()
            children = await self._async_get_children()
            events: list[dict[str, Any]] = []
            for offset in (0, 1):  # this and next month
                month = today.month + offset
                year = today.year + (month - 1) // 12
                events += await self.client.async_get_events(year, (month - 1) % 12 + 1)
            events = list({e.get("id", ("no-id", i)): e for i, e in enumerate(events)}.values())
            meals: dict[int, list[dict[str, Any]]] = {}
            for child in children:
                parent = (child.get("elternkonto") or {}).get("id")
                if child.get("istVppAktiv") and parent:
                    meals[child["id"]] = await self.client.async_get_meals(
                        child["id"],
                        parent,
                        today.isoformat(),
                        (today + timedelta(days=MEAL_DAYS_AHEAD)).isoformat(),
                    )
            data = KitaPlusData(
                children=children,
                board=await self.client.async_get_board(),
                messages=await self.client.async_get_messages(),
                accounts=await self.client.async_get_accounts(),
                events=events,
                meals=meals,
            )
        except KitaPlusAuthError as err:
            self._report_auth_problem(err)
            raise ConfigEntryAuthFailed from err
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as err:
            # KitaPlus changed its answers: say so instead of a bare "unexpected error".
            raise UpdateFailed(
                "KitaPlus hat ein unerwartetes Antwortformat geliefert "
                f"({type(err).__name__}). Bitte Diagnostics im Issue teilen."
            ) from err
        except KitaPlusMaintenanceError as err:
            raise UpdateFailed("KitaPlus meldet Wartungsarbeiten, es wird später erneut versucht") from err
        except KitaPlusError as err:
            raise UpdateFailed(str(err)) from err

        ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)
        self._fire_events(data)
        return data

    def _save_tokens(self, tokens: Tokens) -> None:
        """Persist at once: a rotated refresh token must survive a failed poll or a restart."""
        if tokens.refresh_token != self.config_entry.data.get(
            CONF_REFRESH_TOKEN
        ) or tokens.refresh_expires != self.config_entry.data.get(CONF_REFRESH_EXPIRES):
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={
                    **self.config_entry.data,
                    CONF_REFRESH_TOKEN: tokens.refresh_token,
                    CONF_REFRESH_EXPIRES: tokens.refresh_expires,
                },
            )

    def _fire_events(self, data: KitaPlusData) -> None:
        """Fire events for new items, but never on the first refresh."""
        for items, attr, event, title in (
            (data.board, "_seen_board", EVENT_NEW_BOARD_POST, lambda i: i.get("titel")),
            (
                data.messages,
                "_seen_messages",
                EVENT_NEW_MESSAGE,
                lambda i: (i.get("nachricht") or {}).get("titel"),
            ),
        ):
            ids = {i["id"] for i in items if "id" in i}
            seen = getattr(self, attr)
            if seen is not None:
                for item in items:
                    if item.get("id") not in seen:
                        self.hass.bus.async_fire(event, {"id": item.get("id"), "title": title(item)})
            setattr(self, attr, ids)
