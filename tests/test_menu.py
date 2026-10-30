"""The experimental menu plan reader: parser, PDF text, and the way it is wired into the integration."""

from contextlib import ExitStack
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.kitaplus.api.exceptions import KitaPlusApiError
from custom_components.kitaplus.menu import MenuDay, extract_text, parse_menu

from .common import CLIENT, make_entry, setup_integration

PLAN = """Menüplan
Kindergarten
02.-06. November
Mo.
Gemüsesuppe mit Brot
Di.
Nudeln mit Tomatensauce ( veg. )
Mi.
Hähnchenbrust mit Reis
dazu Gurkensalat
Do.
Kartoffelpfanne ( veg. )
Fr.
Fischstäbchen mit Püree
enthält: Weizen, Ei,
enthalt: Sellerie
Beispiel-Lieferant — Musterstraße 1 — Telefon: 0123-456
"""


def make_pdf(lines: list[str]) -> bytes:
    """A tiny valid PDF with one line of text per entry (no library needed)."""
    text = "BT /F1 12 Tf 50 780 Td 16 TL " + " ".join(f"({line}) Tj T*" for line in lines) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(text)} >>\nstream\n{text}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{offset:010d} 00000 n \n" for offset in offsets).encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


# ------------------------------------------------------------------------------------------------ the parser


def test_a_weekly_plan_is_read_into_dishes_vegetarian_marks_and_dates() -> None:
    days = parse_menu(PLAN, 2026)
    assert [d.day for d in days] == [date(2026, 11, d) for d in (2, 3, 4, 5, 6)]
    assert days[0] == MenuDay(date(2026, 11, 2), "Gemüsesuppe mit Brot", False, False)
    assert days[1].dish == "Nudeln mit Tomatensauce" and days[1].vegetarian
    assert days[2].dish == "Hähnchenbrust mit Reis dazu Gurkensalat", "two lines belong to one dish"
    assert days[4].dish == "Fischstäbchen mit Püree"
    assert not any("enthält" in d.dish or "Lieferant" in d.dish for d in days), (
        "allergen lines and footer stop it"
    )


def test_a_ligature_without_a_text_mapping_is_repaired_only_for_a_known_word() -> None:
    plan = PLAN.replace("Hähnchenbrust", "Ge\x00ügelbrust").replace("Fischstäbchen", "Spe\x00ial")
    days = parse_menu(plan, 2026)
    assert days[2].dish.startswith("Geflügelbrust") and not days[2].uncertain
    assert days[4].dish == "Spe?ial mit Püree" and days[4].uncertain, "an unknown word is marked, not guessed"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Irgendein Text ohne Plan",
        PLAN.replace("02.-06. November", ""),  # no date range
        PLAN.replace("02.-06. November", "31.-35. November"),  # not a date
        "Menü\n02.-06. November\nMo.\nSuppe\nDi.\nNudeln\n",  # only two days
    ],
)
def test_a_text_that_is_not_a_recognised_plan_gives_nothing(text) -> None:
    assert parse_menu(text, 2026) == []


def test_other_date_forms_repeated_days_and_words_that_only_look_like_days() -> None:
    plan = PLAN.replace("02.-06. November", "30.10.-03.11.")
    plan = plan.replace("Mo.\nGemüsesuppe", "Mo.\nDoppelte Portion Suppe")
    days = {d.day: d for d in parse_menu(plan, 2026)}
    assert date(2026, 10, 30) in days, "the plan starts on a Friday, as the heading says"
    assert days[date(2026, 11, 2)].dish == "Doppelte Portion Suppe mit Brot", "Do… in a dish is no weekday"
    assert parse_menu(PLAN.replace("02.-06. November", "30.-03. November"), 2026)[0].day == date(2026, 10, 30)
    doubled = PLAN.replace("Do.\nKartoffelpfanne ( veg. )", "Mo.\nZweites Montagsgericht")
    assert [d.dish for d in parse_menu(doubled, 2026)].count("Zweites Montagsgericht") == 0
    long = PLAN.replace("Gemüsesuppe mit Brot", "x" * 500)
    assert len(parse_menu(long, 2026)[0].dish) == 120


# ----------------------------------------------------------------------------------------------- the PDF text


def test_the_text_of_a_pdf_is_read_and_a_broken_file_is_refused() -> None:
    text = extract_text(make_pdf(PLAN.splitlines()[:8]))
    assert "Menüplan".replace("ü", "u") in text.replace("ü", "u") or "Mo." in text
    assert "Mo." in text
    with pytest.raises(ValueError, match="not a readable PDF"):
        extract_text(b"this is not a pdf")


# ------------------------------------------------------------------ inside the integration

POST = {
    "id": 5,
    "datum": "2026-10-28T00:00:00",
    "titel": "Mittagessen",
    "text": "Menüplan 02.11. -06.11",
    "anhaenge": [{"id": 77, "name": "plan", "endung": "pdf", "istDateiVorhanden": True}],
}
SAMPLE = make_pdf(
    [
        "Menu",
        "02.-06. November",
        "Mo.",
        "Suppe",
        "Di.",
        "Nudeln ( veg. )",
        "Mi.",
        "Reis",
        "Do.",
        "Fisch",
        "Fr.",
        "Brei",
    ]
)
OPTIONS = {"menu_from_pdf": True}


@pytest.fixture
def stack():
    with ExitStack() as s:
        yield s


async def test_the_option_is_off_by_default_and_nothing_is_fetched(hass: HomeAssistant, stack) -> None:
    mock = stack.enter_context(patch(f"{CLIENT}.async_get_file", AsyncMock(return_value=(SAMPLE, "x", "y"))))
    await setup_integration(hass, stack, async_get_board=[POST])
    assert hass.states.get("sensor.kitaplus_menu_today") is None
    mock.assert_not_awaited()


async def test_the_dish_of_today_and_tomorrow_comes_from_the_pdf_and_is_fetched_once(
    hass: HomeAssistant, stack, freezer
) -> None:
    freezer.move_to("2026-11-03T08:00:00+00:00")
    mock = stack.enter_context(patch(f"{CLIENT}.async_get_file", AsyncMock(return_value=(SAMPLE, "x", "y"))))
    entry = await setup_integration(hass, stack, make_entry(OPTIONS), async_get_board=[POST])
    today, tomorrow = (
        hass.states.get("sensor.kitaplus_menu_today"),
        hass.states.get("sensor.kitaplus_menu_tomorrow"),
    )
    assert today.state == "Nudeln" and today.attributes["vegetarian"] is True
    assert tomorrow.state == "Reis" and tomorrow.attributes["vegetarian"] is False
    assert today.attributes["source"] == "menu_pdf" and today.attributes["uncertain"] is False
    await entry.runtime_data.async_refresh()
    await entry.runtime_data.async_refresh()
    assert mock.await_count == 1, "the same PDF is not downloaded again"
    other = {**POST, "anhaenge": [{"id": 78, "name": "plan", "endung": "pdf"}]}
    stack.enter_context(patch(f"{CLIENT}.async_get_board", return_value=[other]))
    await entry.runtime_data.async_refresh()
    assert mock.await_count == 2, "a new attachment is read"
    assert mock.await_args.args[:2] == ("board", 78)


async def test_days_without_a_plan_are_empty(hass: HomeAssistant, stack, freezer) -> None:
    freezer.move_to("2026-11-20T08:00:00+00:00")  # three weeks after the plan
    stack.enter_context(patch(f"{CLIENT}.async_get_file", AsyncMock(return_value=(SAMPLE, "x", "y"))))
    await setup_integration(hass, stack, make_entry(OPTIONS), async_get_board=[POST])
    state = hass.states.get("sensor.kitaplus_menu_today")
    assert state.state == "unknown" and state.attributes["vegetarian"] is None


@pytest.mark.parametrize(
    "board",
    [
        [{**POST, "titel": "Elternabend", "text": "Einladung"}],  # nothing about a menu
        [{**POST, "anhaenge": [{"id": 1, "name": "plan", "endung": "docx"}]}],  # not a PDF
        [{**POST, "anhaenge": [{"id": 1, "name": "plan", "endung": "pdf", "istDateiVorhanden": False}]}],
        [{**POST, "anhaenge": [{"name": "plan", "endung": "pdf"}]}],  # no id
        [],
    ],
)
async def test_only_a_menu_plan_pdf_is_downloaded(hass: HomeAssistant, stack, board) -> None:
    mock = stack.enter_context(patch(f"{CLIENT}.async_get_file", AsyncMock(return_value=(SAMPLE, "x", "y"))))
    await setup_integration(hass, stack, make_entry(OPTIONS), async_get_board=board)
    mock.assert_not_awaited()


async def test_the_search_word_can_be_changed(hass: HomeAssistant, stack) -> None:
    mock = stack.enter_context(patch(f"{CLIENT}.async_get_file", AsyncMock(return_value=(SAMPLE, "x", "y"))))
    entry = make_entry({**OPTIONS, "menu_keyword": "speisen"})
    await setup_integration(hass, stack, entry, async_get_board=[POST])
    mock.assert_not_awaited()  # "Menüplan" does not contain "speisen"


async def test_a_failed_download_is_tried_again_but_an_unreadable_pdf_is_not(
    hass: HomeAssistant, stack, caplog
) -> None:
    mock = stack.enter_context(
        patch(f"{CLIENT}.async_get_file", AsyncMock(side_effect=KitaPlusApiError("x")))
    )
    entry = await setup_integration(hass, stack, make_entry(OPTIONS), async_get_board=[POST])
    await entry.runtime_data.async_refresh()
    assert mock.await_count == 2, "a network problem is retried at the next poll"
    assert entry.runtime_data.last_update_success, "and never fails the update"
    mock.side_effect = None
    mock.return_value = (b"garbage", "x", "y")
    await entry.runtime_data.async_refresh()
    await entry.runtime_data.async_refresh()
    assert mock.await_count == 3, "a PDF that cannot be read is not downloaded again and again"
    assert "was not recognised" in caplog.text
    assert hass.states.get("sensor.kitaplus_menu_today").state == "unknown"


async def test_switching_the_option_off_forgets_the_plan(hass: HomeAssistant, stack, freezer) -> None:
    freezer.move_to("2026-11-03T08:00:00+00:00")
    stack.enter_context(patch(f"{CLIENT}.async_get_file", AsyncMock(return_value=(SAMPLE, "x", "y"))))
    entry = await setup_integration(hass, stack, make_entry(OPTIONS), async_get_board=[POST])
    coordinator = entry.runtime_data
    assert coordinator.data.menu
    hass.config_entries.async_update_entry(entry, options={})
    await coordinator.async_refresh()
    assert coordinator.data.menu == {}
