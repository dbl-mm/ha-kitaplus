"""Base entities."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api.models import Child
from .attachments import signed_link
from .const import CONFIGURATION_URL, DOMAIN, MANUFACTURER
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
            manufacturer=MANUFACTURER,
            model="Eltern-App",
            configuration_url=CONFIGURATION_URL,
            entry_type=DeviceEntryType.SERVICE,
        )

    def _file_link(self, attachment_id: int) -> str | None:
        """A signed address for an attached file, valid until the data is certainly refreshed."""
        interval = self.coordinator.update_interval or timedelta(minutes=30)
        return signed_link(self.hass, self._entry_id, attachment_id, interval + timedelta(minutes=30))

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

    def __init__(self, coordinator: KitaPlusCoordinator, child: Child) -> None:
        super().__init__(coordinator)
        self._child_id: int = child["id"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry_id}_{self._child_id}")},
            name=child.get("vorname") or "Kind",
            manufacturer=MANUFACTURER,
            model="Kind",
            configuration_url=CONFIGURATION_URL,
            entry_type=DeviceEntryType.SERVICE,
            via_device=(DOMAIN, self._entry_id),
        )


if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import KitaPlusConfigEntry


@callback
def async_add_when_new(
    entry: KitaPlusConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    discover: Callable[[KitaPlusCoordinator], Mapping[str, Callable[[], KitaPlusEntity]]],
) -> None:
    """Add entities now and whenever a later update brings something new (a new child, a new account).

    `discover` maps a stable key to a factory. Keys seen before are skipped, so nothing is added twice.
    """
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add() -> None:
        new = {key: factory for key, factory in discover(coordinator).items() if key not in known}
        if new:
            known.update(new)
            async_add_entities([factory() for factory in new.values()])

    _add()
    entry.async_on_unload(coordinator.async_add_listener(_add))
