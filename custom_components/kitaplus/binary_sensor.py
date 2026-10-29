"""Binary sensors for KitaPlus."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import KitaPlusConfigEntry
from .coordinator import KitaPlusCoordinator
from .entity import KitaPlusChildEntity, KitaPlusEntity
from .helpers import is_closed_on, meals_on

PARALLEL_UPDATES = 0  # data comes from the coordinator, entities never call the API


class ClosedSensor(KitaPlusEntity, BinarySensorEntity):
    """Kita closed today or tomorrow (closure day or public holiday)."""

    _follows_the_day = True

    def __init__(self, coordinator: KitaPlusCoordinator, offset: int) -> None:
        super().__init__(coordinator)
        self._offset = offset
        key = "closed_tomorrow" if offset else "closed_today"
        self._attr_translation_key = key
        self._attr_unique_id = f"{self._entry_id}_{key}"

    @property
    def is_on(self) -> bool:
        day = dt_util.now().date() + timedelta(days=self._offset)
        return is_closed_on(self.coordinator.data.events, day)


class NoOrderTomorrowSensor(KitaPlusChildEntity, BinarySensorEntity):
    """Problem: meals are offered tomorrow but nothing is ordered."""

    _attr_translation_key = "no_order_tomorrow"
    _follows_the_day = True

    def __init__(self, coordinator: KitaPlusCoordinator, child: dict[str, Any]) -> None:
        super().__init__(coordinator, child)
        self._attr_unique_id = f"{self._entry_id}_{self._child_id}_no_order_tomorrow"

    def _meals(self) -> list[dict[str, Any]]:
        day = dt_util.now().date() + timedelta(days=1)
        return meals_on(self.coordinator.data.meals.get(self._child_id, []), day)

    @property
    def is_on(self) -> bool:
        meals = self._meals()
        return bool(meals) and not any(m["bestellt"] for m in meals)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"can_still_order": any(m["bestellbar"] for m in self._meals())}


async def async_setup_entry(
    hass: HomeAssistant, entry: KitaPlusConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[KitaPlusEntity] = [ClosedSensor(coordinator, 0), ClosedSensor(coordinator, 1)]
    entities += [
        NoOrderTomorrowSensor(coordinator, c)
        for c in coordinator.data.children
        if c["id"] in coordinator.data.meals
    ]
    async_add_entities(entities)
