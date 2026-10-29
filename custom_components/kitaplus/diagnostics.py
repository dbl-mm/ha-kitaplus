"""Diagnostics with personal data removed."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import KitaPlusConfigEntry

# Fields of the API answers that may be shown. Everything else is dropped, so a field KitaPlus adds later
# never ends up in a report that people post in public issues.
SAFE_EVENT_FIELDS = ("startdatum", "enddatum", "istSchliesstag", "istFeiertag")
SAFE_CHILD_FIELDS = ("istVppAktiv",)

TO_REDACT = {
    "account_id",
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
            "children": [{k: child.get(k) for k in SAFE_CHILD_FIELDS} for child in data.children],
            "events": [{k: event.get(k) for k in SAFE_EVENT_FIELDS} for event in data.events],
        },
        TO_REDACT,
    )
