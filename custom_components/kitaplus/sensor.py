"""Sensors for KitaPlus."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import KitaPlusConfigEntry
from .api.models import BoardPost, Child, MealEntry, Message
from .coordinator import KitaPlusCoordinator
from .entity import KitaPlusChildEntity, KitaPlusEntity, async_add_when_new
from .helpers import ORDER_STATES, meals_on, order_status, pending_replies

PARALLEL_UPDATES = 0  # data comes from the coordinator, entities never call the API

_MAX_ITEMS = 5
_MAX_TEXT = 500
_NOTHING_ORDERED = {"de": "Nichts bestellt", "en": "Nothing ordered"}
_ORDERED = {"de": "Bestellt", "en": "Ordered"}


def _board_short(posts: list[BoardPost]) -> list[dict[str, Any]]:
    return [
        {
            "id": post.get("id"),
            "datum": post.get("datum"),
            "titel": post.get("titel"),
            "text": (post.get("text") or "")[:_MAX_TEXT],
        }
        for post in posts[:_MAX_ITEMS]
    ]


def _messages_short(messages: list[Message]) -> list[dict[str, Any]]:
    out = []
    for msg in messages[:_MAX_ITEMS]:
        note = msg.get("nachricht") or {}
        out.append(
            {
                "id": msg.get("id"),
                "datum": note.get("datum") or msg.get("abrufDatum"),
                "titel": note.get("titel"),
                "text": (note.get("text") or "")[:_MAX_TEXT],
            }
        )
    return out


async def async_setup_entry(
    hass: HomeAssistant, entry: KitaPlusConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    def discover(coordinator: KitaPlusCoordinator) -> dict[str, Callable[[], KitaPlusEntity]]:
        found: dict[str, Callable[[], KitaPlusEntity]] = {
            "board": lambda: BoardSensor(coordinator),
            "messages": lambda: MessagesSensor(coordinator),
            "pending": lambda: PendingRepliesSensor(coordinator),
            "session": lambda: SessionSensor(coordinator),
        }
        for child in coordinator.data.children:
            if child["id"] in coordinator.data.meals:
                for offset in (0, 1):
                    found[f"meal-{child['id']}-{offset}"] = partial(MealSensor, coordinator, child, offset)
                    found[f"status-{child['id']}-{offset}"] = partial(
                        OrderStatusSensor, coordinator, child, offset
                    )
        for account in coordinator.data.accounts:
            if "id" in account and account.get("istAktiv", True):
                found[f"balance-{account['id']}"] = partial(BalanceSensor, coordinator, account["id"])
        return found

    async_add_when_new(entry, async_add_entities, discover)


class BoardSensor(KitaPlusEntity, SensorEntity):
    """Latest bulletin board post."""

    _attr_translation_key = "board"
    _unrecorded_attributes = frozenset({"posts"})  # long texts stay out of the database

    def __init__(self, coordinator: KitaPlusCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._entry_id}_board"

    @property
    def native_value(self) -> str | None:
        board = self.coordinator.data.board
        return (board[0].get("titel") or "")[:255] if board else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"posts": _board_short(self.coordinator.data.board)}


class MessagesSensor(KitaPlusEntity, SensorEntity):
    """Number of messages in the mailbox."""

    _attr_translation_key = "messages"
    _unrecorded_attributes = frozenset({"messages"})
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: KitaPlusCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._entry_id}_messages"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.messages)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"messages": _messages_short(self.coordinator.data.messages)}


class BalanceSensor(KitaPlusEntity, SensorEntity):
    """Meal account balance."""

    _attr_translation_key = "balance"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: KitaPlusCoordinator, account_id: int) -> None:
        super().__init__(coordinator)
        self._account_id = account_id
        self._attr_unique_id = f"{self._entry_id}_balance_{account_id}"

    @property
    def native_value(self) -> float | None:
        for acc in self.coordinator.data.accounts:
            if acc.get("id") == self._account_id:
                try:
                    return float(str(acc["kontostand"]).replace(",", "."))
                except (KeyError, TypeError, ValueError):
                    return None
        return None


class PendingRepliesSensor(KitaPlusEntity, SensorEntity):
    """Messages that still need a confirmation."""

    _attr_translation_key = "pending_replies"
    _unrecorded_attributes = frozenset({"messages"})
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: KitaPlusCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._entry_id}_pending_replies"

    @property
    def native_value(self) -> int:
        return len(pending_replies(self.coordinator.data.messages))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"messages": pending_replies(self.coordinator.data.messages)}


class MealSensor(KitaPlusChildEntity, SensorEntity):
    """Ordered meal for today or tomorrow."""

    _follows_the_day = True
    _unrecorded_attributes = frozenset({"offered"})

    def __init__(self, coordinator: KitaPlusCoordinator, child: Child, offset: int) -> None:
        super().__init__(coordinator, child)
        self._offset = offset
        key = "meal_tomorrow" if offset else "meal_today"
        self._attr_translation_key = key
        self._attr_unique_id = f"{self._entry_id}_{self._child_id}_{key}"

    def _meals(self) -> list[MealEntry]:
        day = dt_util.now().date() + timedelta(days=self._offset)
        return meals_on(self.coordinator.data.meals.get(self._child_id, []), day)

    @property
    def native_value(self) -> str | None:
        meals = self._meals()
        if not meals:
            return None
        language = self.hass.config.language[:2]
        ordered = [m for m in meals if m["bestellt"]]
        if not ordered:
            return _NOTHING_ORDERED.get(language, _NOTHING_ORDERED["en"])
        names = [name for m in ordered if (name := m["variante"] or m["art"])]
        return ", ".join(names)[:255] or _ORDERED.get(language, _ORDERED["en"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"offered": self._meals()}


class SessionSensor(KitaPlusEntity, SensorEntity):
    """Until when the stored KitaPlus session works. Helps to see a pending sign-in in advance."""

    _attr_translation_key = "session_valid_until"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: KitaPlusCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._entry_id}_session_valid_until"

    @property
    def native_value(self) -> datetime | None:
        tokens = self.coordinator.client.tokens
        return datetime.fromtimestamp(tokens.refresh_expires, UTC) if tokens else None


class OrderStatusSensor(KitaPlusChildEntity, SensorEntity):
    """Ordered, open, deadline missed or no meal, for today or tomorrow.

    KitaPlus decides per meal whether it can still be ordered (each Kita sets its own deadline), and the
    integration only repeats that decision. So the status is as fresh as the last update.
    """

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ORDER_STATES
    _follows_the_day = True

    def __init__(self, coordinator: KitaPlusCoordinator, child: Child, offset: int) -> None:
        super().__init__(coordinator, child)
        self._offset = offset
        key = "order_status_tomorrow" if offset else "order_status_today"
        self._attr_translation_key = key
        self._attr_unique_id = f"{self._entry_id}_{self._child_id}_{key}"

    @property
    def native_value(self) -> str:
        day = dt_util.now().date() + timedelta(days=self._offset)
        return order_status(meals_on(self.coordinator.data.meals.get(self._child_id, []), day))
