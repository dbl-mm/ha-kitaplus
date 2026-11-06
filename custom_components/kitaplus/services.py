"""Actions of the KitaPlus integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.loader import async_get_integration

from . import dashboard
from .const import ATTR_CONFIG_ENTRY, ATTR_LANGUAGE, DOMAIN, SERVICE_DASHBOARD_YAML

if TYPE_CHECKING:
    from . import KitaPlusConfigEntry

LANGUAGES = sorted(dashboard.TEXT)

DASHBOARD_YAML_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY): cv.string,
        vol.Optional(ATTR_LANGUAGE): vol.In(LANGUAGES),
    }
)


def _entry(hass: HomeAssistant, entry_id: str | None) -> KitaPlusConfigEntry:
    """The KitaPlus entry the action is about. Several accounts need an explicit choice."""
    loaded: list[KitaPlusConfigEntry] = list(hass.config_entries.async_loaded_entries(DOMAIN))
    if entry_id is not None:
        loaded = [entry for entry in loaded if entry.entry_id == entry_id]
    if not loaded:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_loaded_entry")
    if len(loaded) > 1:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="choose_entry")
    return loaded[0]


def _lookup(registry: er.EntityRegistry, entry_id: str) -> dashboard.Lookup:
    """Find an entity id by platform and unique id. A unique id ending in "_" matches by prefix."""
    found = {
        (entity.domain, entity.unique_id): entity.entity_id
        for entity in er.async_entries_for_config_entry(registry, entry_id)
    }

    def lookup(domain: str, unique_id: str) -> str | None:
        if (exact := found.get((domain, unique_id))) is not None:
            return exact
        if unique_id.endswith("_"):
            return next(
                (
                    eid
                    for (dom, uid), eid in sorted(found.items())
                    if dom == domain and uid.startswith(unique_id)
                ),
                None,
            )
        return None

    return lookup


async def _async_dashboard_yaml(call: ServiceCall) -> ServiceResponse:
    """Build the dashboard for the real children with the real entity ids and return it as YAML text."""
    hass = call.hass
    entry = _entry(hass, call.data.get(ATTR_CONFIG_ENTRY))
    language = call.data.get(ATTR_LANGUAGE) or ("de" if hass.config.language.startswith("de") else "en")
    children = [(child["id"], child.get("vorname") or "Kind") for child in entry.runtime_data.data.children]
    version = (await async_get_integration(hass, DOMAIN)).version
    text = dashboard.ready_yaml(
        language,
        str(version),
        entry.entry_id,
        children,
        _lookup(er.async_get(hass), entry.entry_id),
    )
    result: dict[str, Any] = {"language": language, "children": [name for _, name in children], "yaml": text}
    return result


def async_register_services(hass: HomeAssistant) -> None:
    """Register the actions once, for all entries (Home Assistant asks for this in async_setup)."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_DASHBOARD_YAML,
        _async_dashboard_yaml,
        schema=DASHBOARD_YAML_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
