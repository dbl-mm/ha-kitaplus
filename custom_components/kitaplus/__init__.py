"""The KitaPlus integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntry

from .api.client import KitaPlusClient
from .attachments import KitaPlusAttachmentView
from .const import CONF_CLIENT_ID, CONF_DASHBOARD_HINT, DOMAIN, SERVICE_DASHBOARD_YAML
from .coordinator import KitaPlusCoordinator
from .services import async_register_services

PLATFORMS = [Platform.BINARY_SENSOR, Platform.CALENDAR, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type KitaPlusConfigEntry = ConfigEntry[KitaPlusCoordinator]

# Shown once after a new account was set up. Notifications are not translated by Home Assistant, so the
# text follows the language of the installation.
DASHBOARD_HINT = {
    "de": (
        "KitaPlus ist eingerichtet. Ein fertiges Dashboard für deine Kinder bekommst du so: "
        "**Entwicklerwerkzeuge → Aktionen → „KitaPlus: Dashboard erzeugen“** ausführen und die ganze "
        "Antwort kopieren. Einbau: Einstellungen → Dashboards → Dashboard hinzufügen → "
        "Raw-Konfigurationseditor. Es ist nichts zu ersetzen. Unter **Konfigurieren** kannst du noch die "
        "Bestellfrist deiner Kita prüfen (sie wird sonst aus KitaPlus gelesen)."
    ),
    "en": (
        "KitaPlus is set up. To get a ready-made dashboard for your children: run "
        '**Developer tools → Actions → "KitaPlus: Create dashboard"** and copy the whole '
        "response. Install it under Settings → Dashboards → Add dashboard → Raw configuration editor. "
        "Nothing needs replacing. Under **Configure** you can check your Kita's order deadline (otherwise "
        "it is read from KitaPlus)."
    ),
}


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register the actions once (they belong to the integration, not to one account)."""
    async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: KitaPlusConfigEntry) -> bool:
    """Set up KitaPlus from a config entry."""
    client = KitaPlusClient(async_get_clientsession(hass), entry.data[CONF_CLIENT_ID])
    coordinator = KitaPlusCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    if f"{DOMAIN}_view" not in hass.data:  # one web address for all entries
        hass.data[f"{DOMAIN}_view"] = view = KitaPlusAttachmentView()
        hass.http.register_view(view)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if entry.data.get(CONF_DASHBOARD_HINT):
        _show_dashboard_hint(hass, entry)
    return True


def _show_dashboard_hint(hass: HomeAssistant, entry: KitaPlusConfigEntry) -> None:
    """Tell a new user once how to get the dashboard, then forget that it is due."""
    language = "de" if hass.config.language.startswith("de") else "en"
    persistent_notification.async_create(
        hass,
        DASHBOARD_HINT[language],
        title="KitaPlus",
        notification_id=f"{DOMAIN}_{SERVICE_DASHBOARD_YAML}_{entry.entry_id}",
    )
    data = {key: value for key, value in entry.data.items() if key != CONF_DASHBOARD_HINT}
    hass.config_entries.async_update_entry(entry, data=data)


async def async_unload_entry(hass: HomeAssistant, entry: KitaPlusConfigEntry) -> bool:
    """Unload a config entry."""
    if (view := hass.data.get(f"{DOMAIN}_view")) is not None:
        view.forget(entry.entry_id)  # downloaded files are not kept after unloading
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: KitaPlusConfigEntry, device: DeviceEntry
) -> bool:
    """Let the user delete a child's device only when KitaPlus no longer lists that child."""
    active = {f"{entry.entry_id}_{child['id']}" for child in entry.runtime_data.data.children}
    for domain, identifier in device.identifiers:
        if domain == DOMAIN and (identifier == entry.entry_id or identifier in active):
            return False
    return True
