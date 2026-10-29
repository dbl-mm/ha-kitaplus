"""Data update coordinator for KitaPlus."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from functools import partial
from typing import TYPE_CHECKING

from homeassistant.core import CALLBACK_TYPE, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api.client import KitaPlusClient, Tokens
from .api.exceptions import KitaPlusAuthError, KitaPlusError, KitaPlusMaintenanceError
from .api.models import Account, BoardPost, Child, Day, Event, Message
from .const import (
    CONF_ACCOUNT_ID,
    CONF_DEADLINE_DAYS,
    CONF_DEADLINE_TIME,
    CONF_DEADLINE_WORKDAYS,
    CONF_EMAIL,
    CONF_LEAD_MINUTES,
    CONF_REFRESH_EXPIRES,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    DEFAULT_DEADLINE_TIME,
    DEFAULT_LEAD_MINUTES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_NEW_BOARD_POST,
    EVENT_NEW_MESSAGE,
    EVENT_ORDER_DEADLINE,
)
from .helpers import DeadlineRule, OpenOrder, open_orders, plain_text

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

TimerKey = tuple[str, int, date]  # ("deadline" or "remind", child id, day)

CHILDREN_REFRESH = timedelta(hours=24)
MEAL_DAYS_AHEAD = 14


@dataclass
class KitaPlusData:
    """Snapshot of everything we poll."""

    children: list[Child] = field(default_factory=list)
    board: list[BoardPost] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    accounts: list[Account] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    meals: dict[int, list[Day]] = field(default_factory=dict)  # child id -> days


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
        self.deadline_rule = self._read_deadline_rule()
        self._lead = timedelta(minutes=entry.options.get(CONF_LEAD_MINUTES, DEFAULT_LEAD_MINUTES))
        self._timers: dict[TimerKey, CALLBACK_TYPE] = {}
        self._reminded: set[tuple[int, date]] = set()
        self._reminding: set[tuple[int, date]] = set()
        self._children: list[Child] = []
        self._children_at: datetime | None = None
        self._seen_board: set[int] | None = None
        self._seen_messages: set[int] | None = None

    def _read_deadline_rule(self) -> DeadlineRule | None:
        """The Kita's order deadline from the options, or None while it is not set."""
        options = self.config_entry.options
        days = options.get(CONF_DEADLINE_DAYS)
        if days is None:
            return None
        at = dt_util.parse_time(options.get(CONF_DEADLINE_TIME, DEFAULT_DEADLINE_TIME)) or time(11, 0)
        return DeadlineRule(int(days), at, bool(options.get(CONF_DEADLINE_WORKDAYS, False)))

    def next_open_order(self, child_id: int) -> OpenOrder | None:
        """The next day that can still be ordered for this child, if the Kita's deadline is known."""
        days = self.data.meals.get(child_id, [])
        return next((o for o in open_orders(days, self.deadline_rule, dt_util.now()) if o.deadline), None)

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
                "server_message": plain_text(err.server_message) or "-",
            },
        )

    async def _async_ensure_session(self) -> None:
        """Use the stored refresh token. The password is never stored, so no silent re-login."""
        if self.client.tokens is not None:
            return
        data = self.config_entry.data
        if not data.get(CONF_REFRESH_TOKEN):
            raise ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key="session_expired")
        self.client.set_tokens(Tokens("", data[CONF_REFRESH_TOKEN], float(data.get(CONF_REFRESH_EXPIRES, 0))))

    async def _async_ensure_account_id(self) -> None:
        """Entries made before 0.1.2 are recognised by e-mail. Switch them to the stable account id once."""
        if self.config_entry.data.get(CONF_ACCOUNT_ID) is not None:
            return
        account_id = await self.client.async_get_account_id()
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            unique_id=str(account_id),
            data={**self.config_entry.data, CONF_ACCOUNT_ID: account_id},
        )

    def _remove_stale_devices(self, data: KitaPlusData) -> None:
        """A child that KitaPlus no longer lists must not leave a dead device behind."""
        if not data.children:  # an empty answer is more likely a hiccup than "no more children"
            return
        entry_id = self.config_entry.entry_id
        active = {f"{entry_id}_{child['id']}" for child in data.children}
        registry = dr.async_get(self.hass)
        for device in dr.async_entries_for_config_entry(registry, entry_id):
            for domain, identifier in device.identifiers:
                if domain == DOMAIN and identifier != entry_id and identifier not in active:
                    registry.async_update_device(device.id, remove_config_entry_id=entry_id)

    async def _async_get_children(self) -> list[Child]:
        now = dt_util.utcnow()
        if not self._children or self._children_at is None or now - self._children_at > CHILDREN_REFRESH:
            self._children = await self.client.async_get_children()
            self._children_at = now
        return self._children

    async def _async_update_data(self) -> KitaPlusData:
        today = dt_util.now().date()
        try:
            await self._async_ensure_session()
            await self._async_ensure_account_id()
            children = await self._async_get_children()
            events: list[Event] = []
            for offset in (0, 1):  # this and next month
                month = today.month + offset
                year = today.year + (month - 1) // 12
                events += await self.client.async_get_events(year, (month - 1) % 12 + 1)
            events = list({e.get("id", ("no-id", i)): e for i, e in enumerate(events)}.values())
            meals: dict[int, list[Day]] = {}
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
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="auth_rejected",
                translation_placeholders={"server_message": plain_text(err.server_message) or "-"},
            ) from err
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as err:
            # KitaPlus changed its answers: say so instead of a bare "unexpected error".
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="unexpected_format",
                translation_placeholders={"error": type(err).__name__},
            ) from err
        except KitaPlusMaintenanceError as err:
            raise UpdateFailed(translation_domain=DOMAIN, translation_key="maintenance") from err
        except KitaPlusError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="api_error",
                translation_placeholders={"error": str(err)},
            ) from err

        ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)
        self._remove_stale_devices(data)
        self._schedule_deadlines(data)
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

    async def async_shutdown(self) -> None:
        """Stop the deadline timers together with the coordinator."""
        for cancel in self._timers.values():
            cancel()
        self._timers.clear()
        await super().async_shutdown()

    def _schedule_deadlines(self, data: KitaPlusData) -> None:
        """Plan what has to happen at each deadline.

        At every deadline the entities are refreshed, so the order status turns to "missed" on the minute.
        Shortly before it, a reminder is prepared for every day that is still open.

        Timers are kept per child and day and stay as long as they are wanted. They are not thrown away and
        rebuilt on every update: an update that finishes at the very moment a timer is due would otherwise
        cancel that timer before its callback has run and the reminder would be lost.
        """
        now = dt_util.now()
        self._reminded = {key for key in self._reminded if key[1] >= now.date()}
        wanted: dict[TimerKey, datetime] = {}
        for child in data.children:
            child_id = child["id"]
            for order in open_orders(data.meals.get(child_id, []), self.deadline_rule, now):
                if order.deadline is None:
                    continue
                wanted[("deadline", child_id, order.day)] = order.deadline
                if (
                    self._lead > timedelta(0)
                    and (child_id, order.day) not in self._reminded | self._reminding
                ):
                    wanted[("remind", child_id, order.day)] = order.deadline - self._lead
        for key in [k for k in self._timers if k not in wanted]:
            self._timers.pop(key)()  # not wanted any more, for example because the day was ordered
        for key, when in wanted.items():
            if key not in self._timers:
                callback = self._deadline_reached if key[0] == "deadline" else self._reminder_due
                # a reminder whose time has passed while the deadline has not is made up for right away
                self._timers[key] = async_track_point_in_time(
                    self.hass, partial(callback, key), max(when, now)
                )

    @callback
    def _deadline_reached(self, key: TimerKey, _now: datetime) -> None:
        self._timers.pop(key, None)
        self.async_update_listeners()  # entities work out "open" or "missed" from the clock

    @callback
    def _reminder_due(self, key: TimerKey, _now: datetime) -> None:
        self._timers.pop(key, None)
        self.hass.async_create_task(self._async_remind(key[1], key[2]))

    async def _async_remind(self, child_id: int, day: date) -> None:
        """Ask KitaPlus for current data, then remind only if the day is still open."""
        key = (child_id, day)
        if key in self._reminded or key in self._reminding:
            return
        self._reminding.add(key)  # the refresh below plans timers again; it must not plan this reminder again
        try:
            await self.async_refresh()
            now = dt_util.now()
            orders = open_orders(self.data.meals.get(child_id, []), self.deadline_rule, now)
            order = next((o for o in orders if o.day == day), None)
            if order is None or order.deadline is None:
                return  # ordered in the meantime, or the deadline has passed
            self._reminded.add(key)
            name = next((c.get("vorname") for c in self.data.children if c["id"] == child_id), None)
            self.hass.bus.async_fire(
                EVENT_ORDER_DEADLINE,
                {
                    "child": name,
                    "child_id": child_id,
                    "day": day.isoformat(),
                    "days_ahead": (day - now.date()).days,
                    "weekday": day.weekday(),
                    "deadline": order.deadline.isoformat(),
                    "minutes_left": int((order.deadline - now).total_seconds() // 60),
                    "fresh": self.last_update_success,
                },
            )
        finally:
            self._reminding.discard(key)

    def _fire_events(self, data: KitaPlusData) -> None:
        """Fire events for new items, but never on the first refresh."""
        self._seen_board = self._fire_new(
            EVENT_NEW_BOARD_POST,
            self._seen_board,
            [(post.get("id"), post.get("titel")) for post in data.board],
        )
        self._seen_messages = self._fire_new(
            EVENT_NEW_MESSAGE,
            self._seen_messages,
            [(msg.get("id"), (msg.get("nachricht") or {}).get("titel")) for msg in data.messages],
        )

    def _fire_new(
        self, event: str, seen: set[int] | None, items: Sequence[tuple[int | None, str | None]]
    ) -> set[int]:
        """Fire one event per item whose id was not seen before; return all ids seen so far."""
        current = {item_id for item_id, _ in items if item_id is not None}
        if seen is not None:
            for item_id, title in items:
                if item_id is not None and item_id not in seen:
                    self.hass.bus.async_fire(event, {"id": item_id, "title": title})
        return current
