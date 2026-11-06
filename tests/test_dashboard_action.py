"""The action kitaplus.dashboard_yaml builds a dashboard with the real children and entity ids."""

import json
import re
from contextlib import ExitStack
from unittest.mock import patch

import pytest
import yaml
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kitaplus import dashboard
from custom_components.kitaplus.const import DOMAIN

from .common import make_entry, setup_integration

ENTITY_ID = re.compile(r"\b(?:sensor|binary_sensor|calendar)\.[a-z0-9_]+\b")


@pytest.fixture
def stack():
    with ExitStack() as s:
        yield s


async def run(hass: HomeAssistant, **data) -> dict:
    return await hass.services.async_call(DOMAIN, "dashboard_yaml", data, blocking=True, return_response=True)


def text_of(result: dict) -> str:
    """Everything the dashboard says, as one string to search in."""
    return json.dumps(result, ensure_ascii=False)


async def test_the_answer_is_the_dashboard_with_the_real_child_and_only_entities_that_exist(
    hass, stack
) -> None:
    await setup_integration(hass, stack)
    result = await run(hass)
    assert result["views"] and result["title"], "the answer itself is a dashboard, ready to paste"
    assert not {"yaml", "children", "language"} & set(result), "nothing around it that would break pasting"
    assert "vorname-1" in text_of(result)
    assert "KIND" not in text_of(result) and "sensor.kind_" not in text_of(result), "nothing to replace"
    ids = set(ENTITY_ID.findall(text_of(result)))
    assert ids, "the dashboard refers to entities"
    registry = er.async_get(hass)
    missing = {i for i in ids if registry.async_get(i) is None}
    assert not missing, f"entity ids that do not exist: {missing}"
    assert "sensor.vorname_1_order_status_today" in ids and "sensor.kitaplus_meal_account_balance" in ids


async def test_the_answer_survives_a_round_trip_through_yaml(hass, stack) -> None:
    """The frontend shows the answer as YAML and the user pastes it back: nothing may get lost."""
    await setup_integration(hass, stack)
    result = await run(hass)
    assert yaml.safe_load(yaml.safe_dump(result, allow_unicode=True)) == result


async def test_the_language_changes_the_texts_not_the_entity_ids(hass, stack) -> None:
    await setup_integration(hass, stack)
    german = await run(hass, language="de")
    english = await run(hass, language="en")
    assert german["views"][2]["title"] == dashboard.TEXT["de"]["view_calendar"]
    assert english["views"][2]["title"] == dashboard.TEXT["en"]["view_calendar"]
    assert set(ENTITY_ID.findall(text_of(german))) == set(ENTITY_ID.findall(text_of(english)))


async def test_the_default_language_follows_home_assistant(hass, stack) -> None:
    await setup_integration(hass, stack)
    assert (await run(hass))["views"][0]["title"] == dashboard.TEXT["en"]["view_today"]
    hass.config.language = "de"
    assert (await run(hass))["views"][0]["title"] == dashboard.TEXT["de"]["view_today"]


async def test_a_renamed_entity_is_used_with_its_new_id(hass, stack) -> None:
    await setup_integration(hass, stack)
    registry = er.async_get(hass)
    registry.async_update_entity("sensor.vorname_1_order_status_today", new_entity_id="sensor.finn_status")
    registry.async_update_entity("sensor.kitaplus_mailbox", new_entity_id="sensor.kita_post")
    ids = set(ENTITY_ID.findall(text_of(await run(hass))))
    assert "sensor.finn_status" in ids and "sensor.kita_post" in ids
    assert "sensor.vorname_1_order_status_today" not in ids and "sensor.kitaplus_mailbox" not in ids


async def test_without_a_set_up_account_the_action_explains_what_to_do(hass) -> None:
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, DOMAIN, {})
    with pytest.raises(ServiceValidationError) as err:
        await run(hass)
    assert err.value.translation_key == "no_loaded_entry"


async def test_with_two_accounts_one_has_to_be_chosen(hass, stack) -> None:
    first = await setup_integration(hass, stack)
    second = MockConfigEntry(domain=DOMAIN, unique_id="other", data=dict(first.data), options={})
    second.add_to_hass(hass)
    await hass.config_entries.async_setup(second.entry_id)
    await hass.async_block_till_done()
    with pytest.raises(ServiceValidationError) as err:
        await run(hass)
    assert err.value.translation_key == "choose_entry"
    result = await run(hass, config_entry=first.entry_id)
    ids = set(ENTITY_ID.findall(text_of(result)))
    registry = er.async_get(hass)
    assert ids and all(
        registry.async_get(i).config_entry_id == first.entry_id for i in ids if registry.async_get(i)
    )


async def test_a_wrong_language_is_rejected(hass, stack) -> None:
    import voluptuous as vol

    await setup_integration(hass, stack)
    with pytest.raises(vol.Invalid):
        await run(hass, language="fr")


async def test_a_nameless_child_is_called_kind_and_stray_spaces_are_dropped(hass, stack) -> None:
    from .conftest import load

    kids = load("get_einrichtungen_kinder")["kinder"]
    await setup_integration(hass, stack, async_get_children=[{**kids[0], "vorname": None}])
    assert "'Kind'" in text_of(await run(hass)), "the name appears as a quoted text in the cards"


async def test_a_name_with_a_trailing_space_is_cleaned(hass, stack) -> None:
    from .conftest import load

    kids = load("get_einrichtungen_kinder")["kinder"]
    await setup_integration(hass, stack, async_get_children=[{**kids[0], "vorname": "Finn "}])
    out = text_of(await run(hass))
    assert "'Finn'" in out and "'Finn '" not in out


def test_ids_fall_back_to_the_usual_names_when_the_registry_does_not_know_one() -> None:
    ids = dashboard.RegistryIds("de", "entry", lambda domain, unique: None, 5)
    assert ids.account("sensor", "messages") == "sensor.kitaplus_postfach"
    assert ids.of_child("sensor", "status_today") == "sensor.kind_bestellstatus_heute"


# ----------------------------------------------------------------------------------- the hint after setup


async def test_a_new_account_gets_the_hint_once_and_the_flag_is_removed(hass, stack) -> None:
    entry = make_entry(show_dashboard_hint=True)
    with patch("custom_components.kitaplus.persistent_notification.async_create") as notify:
        await setup_integration(hass, stack, entry=entry)
        assert notify.call_count == 1
        assert "dashboard" in notify.call_args.args[1].lower()
        assert "show_dashboard_hint" not in entry.data
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert notify.call_count == 1, "shown once, not at every start"


async def test_an_existing_account_gets_no_hint(hass, stack) -> None:
    with patch("custom_components.kitaplus.persistent_notification.async_create") as notify:
        await setup_integration(hass, stack)
    notify.assert_not_called()


async def test_the_hint_follows_the_language(hass, stack) -> None:
    hass.config.language = "de"
    with patch("custom_components.kitaplus.persistent_notification.async_create") as notify:
        await setup_integration(hass, stack, entry=make_entry(show_dashboard_hint=True))
    assert "Dashboard erzeugen" in notify.call_args.args[1]


async def test_an_unknown_unique_id_is_not_found_and_a_prefix_finds_the_balance(hass, stack) -> None:
    from custom_components.kitaplus.services import _lookup

    entry = await setup_integration(hass, stack)
    lookup = _lookup(er.async_get(hass), entry.entry_id)
    assert lookup("sensor", f"{entry.entry_id}_does_not_exist") is None
    assert lookup("sensor", f"{entry.entry_id}_balance_") == "sensor.kitaplus_meal_account_balance"


def test_writing_the_templates_again_removes_cards_that_no_longer_exist(tmp_path) -> None:
    stale = tmp_path / "cards" / "de" / "gone.yaml"
    stale.parent.mkdir(parents=True)
    stale.write_text("old")
    dashboard.write_all(tmp_path)
    assert not stale.exists()
    assert (tmp_path / "kitaplus_de.yaml").exists()
