"""Shared helpers: set the integration up against the anonymised fixtures (no network)."""

from contextlib import ExitStack
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kitaplus.const import DOMAIN

from .conftest import load

CLIENT = "custom_components.kitaplus.api.client.KitaPlusClient"


def make_entry(options: dict | None = None, **data) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="a@b.de",
        data={
            "email": "a@b.de",
            "client_id": "cid",
            "refresh_token": "r",
            "refresh_expires": 4102444800,
            **data,
        },
        options=options or {},
    )


def api_answers(**overrides):
    """The fixtures as client answers; any of them can be replaced per test."""
    kids = load("get_einrichtungen_kinder")
    answers = {
        "async_get_children": kids["kinder"],
        "async_get_events": load("termine")["data"],
        "async_get_meals": load("bestelldaten")["data"][0]["tage"],
        "async_get_board": load("schwarzesbrett")["data"],
        "async_get_messages": load("getNachrichten")["data"],
        "async_get_accounts": kids["verpflegungskonten"],
    }
    answers.update(overrides)
    return answers


async def setup_integration(hass: HomeAssistant, stack: ExitStack, entry=None, **overrides):
    """Patch the client with fixture answers (or errors) and set the entry up."""
    entry = entry or make_entry()
    entry.add_to_hass(hass)
    for name, value in api_answers(**overrides).items():
        kwargs = {"side_effect": value} if isinstance(value, BaseException) else {"return_value": value}
        stack.enter_context(patch(f"{CLIENT}.{name}", **kwargs))
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def meal_day(day: str, *, ordered: bool, orderable: bool) -> dict:
    """One offered meal, with or without an order and with or without an open order deadline."""
    variant: dict = {"name": "Menü", "istBestellbar": orderable, "istAbbestellbar": orderable}
    if ordered:
        variant["bestellung"] = {"istAbbestellt": False}
    return {"datum": f"{day}T00:00:00", "mahlzeitArten": [{"name": "Mittag", "varianten": [variant]}]}
