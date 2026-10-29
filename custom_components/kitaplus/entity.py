"""Base entities."""

from __future__ import annotations

from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import KitaPlusCoordinator


class KitaPlusEntity(CoordinatorEntity[KitaPlusCoordinator]):
    """Entity attached to the account device."""

    _attr_has_entity_name = True
    # Entities whose value depends on "today" are re-evaluated at midnight, not only after a poll.
    _follows_the_day = False

    def __init__(self, coordinator: KitaPlusCoordinator) -> None:
        super().__init__(coordinator)
        self._entry_id = coordinator.config_entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="KitaPlus",
            manufacturer="kitaplus",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._follows_the_day:
            self.async_on_remove(
                async_track_time_change(self.hass, self._handle_new_day, hour=0, minute=0, second=5)
            )

    @callback
    def _handle_new_day(self, _now: object) -> None:
        self.async_write_ha_state()


class KitaPlusChildEntity(KitaPlusEntity):
    """Entity attached to a child device."""

    def __init__(self, coordinator: KitaPlusCoordinator, child: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._child_id: int = child["id"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry_id}_{self._child_id}")},
            name=child.get("vorname") or "Kind",
            manufacturer="kitaplus",
            entry_type=DeviceEntryType.SERVICE,
            via_device=(DOMAIN, self._entry_id),
        )
