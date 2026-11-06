"""Binary sensors for KitaPlus."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from functools import partial
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import KitaPlusConfigEntry
from .api.models import Child, MealEntry
from .const import CONF_WEEKEND_CLOSED, WEEKEND_REASON
from .coordinator import KitaPlusCoordinator
from .entity import KitaPlusChildEntity, KitaPlusEntity, async_add_when_new
from .helpers import closure_on, is_closed_on, meals_on

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

    def _day(self) -> date:
        return dt_util.now().date() + timedelta(days=self._offset)

    @property
    def _weekend(self) -> bool:
        """The day is a Saturday or Sunday and the user chose to count weekends as closed."""
        return bool(
            self.coordinator.config_entry.options.get(CONF_WEEKEND_CLOSED, False)
            and self._day().weekday() >= 5
        )

    @property
    def is_on(self) -> bool:
        return is_closed_on(self.coordinator.data.events, self._day()) or self._weekend

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Why the Kita is closed (the name KitaPlus gives the closure day), for notifications."""
        event = closure_on(self.coordinator.data.events, self._day())
        reason = (event.get("name") or None) if event else None
        if reason is None and self._weekend:
            language = "de" if self.coordinator.hass.config.language.startswith("de") else "en"
            reason = WEEKEND_REASON[language]
        return {"reason": reason}


class NoOrderTomorrowSensor(KitaPlusChildEntity, BinarySensorEntity):
    """Problem: meals are offered tomorrow but nothing is ordered."""

    _attr_translation_key = "no_order_tomorrow"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _follows_the_day = True

    def __init__(self, coordinator: KitaPlusCoordinator, child: Child) -> None:
        super().__init__(coordinator, child)
        self._attr_unique_id = f"{self._entry_id}_{self._child_id}_no_order_tomorrow"

    def _meals(self) -> list[MealEntry]:
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
    def discover(coordinator: KitaPlusCoordinator) -> dict[str, Callable[[], KitaPlusEntity]]:
        found: dict[str, Callable[[], KitaPlusEntity]] = {
            "closed-0": lambda: ClosedSensor(coordinator, 0),
            "closed-1": lambda: ClosedSensor(coordinator, 1),
        }
        for child in coordinator.data.children:
            if child["id"] in coordinator.data.meals:
                found[f"no-order-{child['id']}"] = partial(NoOrderTomorrowSensor, coordinator, child)
        return found

    async_add_when_new(entry, async_add_entities, discover)
