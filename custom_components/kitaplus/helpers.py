"""Pure helpers on the polled data (no Home Assistant objects, easy to test)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def _d(value: str | None) -> date | None:
    """Parse the date part of an ISO string. Unparsable or missing values give None."""
    try:
        return datetime.fromisoformat(value).date() if value else None
    except ValueError:
        return None


def is_closed_on(events: list[dict[str, Any]], day: date) -> bool:
    """True if a closure day or public holiday covers `day`."""
    for event in events:
        if not (event.get("istSchliesstag") or event.get("istFeiertag")):
            continue
        start = _d(event.get("startdatum"))
        end = _d(event.get("enddatum")) or start  # open ended entries count for their first day
        if start and end and start <= day <= end:
            return True
    return False


def meals_on(days: list[dict[str, Any]], day: date) -> list[dict[str, Any]]:
    """Flatten the plan for one day: one entry per meal variant."""
    out: list[dict[str, Any]] = []
    for entry in days:
        if _d(entry.get("datum")) != day:
            continue
        for art in entry.get("mahlzeitArten", []):
            for var in art.get("varianten", []):
                order = var.get("bestellung")
                out.append(
                    {
                        "art": art.get("name"),
                        "variante": var.get("name"),
                        "preis": var.get("preis"),
                        "bestellt": bool(order and not order.get("istAbbestellt")),
                        "bestellbar": bool(var.get("istBestellbar")),
                        "abbestellbar": bool(var.get("istAbbestellbar")),
                    }
                )
    return out


def pending_replies(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Messages that need a confirmation and have not been answered yet."""
    out = []
    for msg in messages:
        note = msg.get("nachricht") or {}
        if note.get("istBestaetigungspflichtig") and not msg.get("istBeantwortet"):
            out.append(
                {"id": msg.get("id"), "titel": note.get("titel"), "frist": note.get("rueckmeldefrist")}
            )
    return out
