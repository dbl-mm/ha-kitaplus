"""The KitaPlus integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api.client import KitaPlusClient
from .const import CONF_CLIENT_ID
from .coordinator import KitaPlusCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.CALENDAR, Platform.SENSOR]

type KitaPlusConfigEntry = ConfigEntry[KitaPlusCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: KitaPlusConfigEntry) -> bool:
    """Set up KitaPlus from a config entry."""
    client = KitaPlusClient(async_get_clientsession(hass), entry.data[CONF_CLIENT_ID])
    coordinator = KitaPlusCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KitaPlusConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
