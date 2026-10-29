"""Diagnostics with personal data removed."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import KitaPlusConfigEntry

TO_REDACT = {
    "id",
    "kindId",
    "elternkontoId",
    "einrichtungId",
    "email",
    "password",
    "refresh_token",
    "client_id",
    "vorname",
    "nachname",
    "name",
    "titel",
    "text",
    "bezeichnung",
    "verwendungszweck",
    "bankkontoIban",
    "ueberweisungEmpfaengerIban",
    "ueberweisungEmpfaengerBic",
    "ueberweisungEmpfaengerName",
    "ueberweisungEmpfaengerQrCode",
    "geburtsdatum",
    "kindKontakte",
    "telefon",
    "mobil",
    "strasse",
    "plz",
    "ort",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: KitaPlusConfigEntry
) -> dict[str, Any]:
    data = entry.runtime_data.data
    return async_redact_data(
        {
            "entry": dict(entry.data),
            "counts": {
                "children": len(data.children),
                "board": len(data.board),
                "messages": len(data.messages),
                "events": len(data.events),
                "accounts": len(data.accounts),
            },
            "children": data.children,
            "events": data.events,
        },
        TO_REDACT,
    )
