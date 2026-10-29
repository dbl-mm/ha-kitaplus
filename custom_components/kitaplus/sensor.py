"""Sensors for KitaPlus."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import KitaPlusConfigEntry
from .coordinator import KitaPlusCoordinator
from .entity import KitaPlusChildEntity, KitaPlusEntity
from .helpers import meals_on, pending_replies

_MAX_ITEMS = 5
_MAX_TEXT = 500
_NOTHING_ORDERED = {"de": "Nichts bestellt", "en": "Nothing ordered"}


def _short(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for i in items[:_MAX_ITEMS]:
        src = i.get("nachricht") or i  # mailbox entries wrap the message
        out.append(
            {
                "id": i.get("id"),
                "datum": src.get("datum") or i.get("abrufDatum"),
                "titel": src.get("titel"),
                "text": (src.get("text") or "")[:_MAX_TEXT],
            }
        )
    return out


async def async_setup_entry(
    hass: HomeAssistant, entry: KitaPlusConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[KitaPlusEntity] = [
        BoardSensor(coordinator),
        MessagesSensor(coordinator),
        PendingRepliesSensor(coordinator),
    ]
    for child in coordinator.data.children:
        if child["id"] in coordinator.data.meals:
            entities += [MealSensor(coordinator, child, 0), MealSensor(coordinator, child, 1)]
    entities += [
        BalanceSensor(coordinator, a["id"])
        for a in coordinator.data.accounts
        if "id" in a and a.get("istAktiv", True)
    ]
    async_add_entities(entities)


class BoardSensor(KitaPlusEntity, SensorEntity):
    """Latest bulletin board post."""

    _attr_translation_key = "board"
    _attr_icon = "mdi:bulletin-board"
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
        return {"posts": _short(self.coordinator.data.board)}


class MessagesSensor(KitaPlusEntity, SensorEntity):
    """Number of messages in the mailbox."""

    _attr_translation_key = "messages"
    _attr_icon = "mdi:email-outline"
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
        return {"messages": _short(self.coordinator.data.messages)}


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
    _attr_icon = "mdi:email-alert-outline"
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

    _attr_icon = "mdi:silverware-fork-knife"
    _follows_the_day = True
    _unrecorded_attributes = frozenset({"offered"})

    def __init__(self, coordinator: KitaPlusCoordinator, child: dict[str, Any], offset: int) -> None:
        super().__init__(coordinator, child)
        self._offset = offset
        key = "meal_tomorrow" if offset else "meal_today"
        self._attr_translation_key = key
        self._attr_unique_id = f"{self._entry_id}_{self._child_id}_{key}"

    def _meals(self) -> list[dict[str, Any]]:
        day = dt_util.now().date() + timedelta(days=self._offset)
        return meals_on(self.coordinator.data.meals.get(self._child_id, []), day)

    @property
    def native_value(self) -> str | None:
        ordered = [m["variante"] or m["art"] for m in self._meals() if m["bestellt"]]
        if ordered:
            return ", ".join(ordered)[:255]
        if not self._meals():
            return None
        return _NOTHING_ORDERED.get(self.hass.config.language[:2], _NOTHING_ORDERED["en"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"offered": self._meals()}
