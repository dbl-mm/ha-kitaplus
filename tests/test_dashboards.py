"""The dashboard templates are generated, follow the design rules, and match the real entities."""

import importlib.util
import re
from contextlib import ExitStack
from pathlib import Path

import pytest
import yaml
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.template import Template
from homeassistant.util import slugify as ha_slugify

from .common import make_entry, setup_integration

ROOT = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("build_dashboards", ROOT / "scripts" / "build_dashboards.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

LANGUAGES = ("de", "en")
BUILT_IN_CARDS = {
    "heading",
    "tile",
    "conditional",
    "vertical-stack",
    "markdown",
    "calendar",
    "entities",
    "grid",
}
THEME_COLOURS = {"orange", "red", "green", "blue", "state"}
ENTITY_ID = re.compile(r"\b(?:sensor|binary_sensor|calendar)\.[a-z0-9_]+\b")
CHILD = "vorname-1"  # the anonymised child in the fixtures, entity ids use vorname_1


@pytest.fixture
def stack():
    with ExitStack() as s:
        yield s


def walk(node):
    """Every dict below a node, depth first."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def iter_cards(node):
    """Every card (and grid section) of a dashboard or of a single card file."""
    if isinstance(node, list):
        for item in node:
            yield from iter_cards(item)
    elif isinstance(node, dict):
        if node.get("type") not in (None, "sections"):  # a view of type `sections` is no card
            yield node
        for key in ("views", "sections", "cards", "card"):
            if key in node:
                yield from iter_cards(node[key])


def all_files(language: str) -> dict[str, str]:
    """The committed templates plus what the generator would produce right now (also for two children).

    The design rules must hold for both, so a rule broken in the generator is caught before files are rebuilt.
    """
    files = {f"kitaplus_{language}.yaml": (ROOT / "dashboards" / f"kitaplus_{language}.yaml").read_text()}
    for path in sorted((ROOT / "dashboards" / "cards" / language).glob("*.yaml")):
        files[f"cards/{language}/{path.name}"] = path.read_text()
    return files


def design_subjects(language: str) -> dict[str, str]:
    files = all_files(language)
    files["generated"] = gen.dump(gen.build(language))
    files["generated for two children"] = gen.dump(gen.build(language, ["Anna", "Ben"]))
    for name, card in gen.single_cards(language).items():
        files[f"generated card {name}"] = gen.dump(card)
    return files


# ------------------------------------------------------------------------------------ generated files


@pytest.mark.parametrize("language", LANGUAGES)
def test_committed_files_are_exactly_what_the_generator_writes(language, tmp_path) -> None:
    gen.write_all(tmp_path)
    for name, committed in all_files(language).items():
        assert (tmp_path / name).read_text() == committed, f"{name} is stale, run scripts/build_dashboards.py"
    names = {p.name for p in (tmp_path / "cards" / language).glob("*.yaml")}
    assert names == {Path(n).name for n in all_files(language) if n.startswith("cards/")}, "no leftover cards"


# ------------------------------------------------------------------------------------- design rules


@pytest.mark.parametrize("language", LANGUAGES)
def test_only_built_in_cards_and_theme_colours(language) -> None:
    for name, text in design_subjects(language).items():
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", text), f"{name}: theme colours only, no hex values"
        cards = list(iter_cards(yaml.safe_load(text)))
        assert cards, name
        for card in cards:
            assert card["type"] in BUILT_IN_CARDS, f"{name}: {card['type']} is not a built-in card"
            if "color" in card:
                assert card["color"] in THEME_COLOURS, f"{name}: {card['color']}"


@pytest.mark.parametrize("language", LANGUAGES)
def test_status_is_never_shown_by_colour_alone(language) -> None:
    """Every tile for a yes/no sensor also prints the state as a word."""
    for name, text in design_subjects(language).items():
        for card in walk(yaml.safe_load(text)):
            if card.get("type") == "tile" and str(card.get("entity", "")).startswith("binary_sensor."):
                assert "state" in card.get("state_content", []), f"{name}: {card['entity']}"
            if card.get("type") == "tile":
                assert card.get("name") and card.get("icon"), f"{name}: tile without name or icon"


# --------------------------------------------------------------------------- the real entities exist


def known_ids(hass: HomeAssistant) -> set[str]:
    return {entry.entity_id for entry in er.async_get(hass).entities.values()}


@pytest.mark.parametrize("language", LANGUAGES)
async def test_every_entity_the_dashboards_use_exists(hass: HomeAssistant, stack, language) -> None:
    hass.config.language = language
    await setup_integration(hass, stack, make_entry({"menu_from_pdf": True}))  # the dishes need the option
    existing = known_ids(hass)
    assert f"sensor.kitaplus_{gen.SLUGS[language]['messages']}" in existing, "the language was applied"

    files = dict(all_files(language))
    files["generated for the fixture child"] = gen.dump(gen.build(language, [CHILD]))
    for name, text in files.items():
        used = set(ENTITY_ID.findall(text.replace(".kind_", ".vorname_1_")))
        assert used, name
        assert used <= existing, f"{name} uses entities that do not exist: {sorted(used - existing)}"


def test_names_are_turned_into_entity_ids_exactly_like_home_assistant() -> None:
    for name in ("Anna", "Jörg", "Mäx", "Strauß", "Zoë", "Anna-Lena", "Luis Paul", "Çağla", "O'Neil", CHILD):
        assert gen.slugify(name) == ha_slugify(name), name


# --------------------------------------------------------------------- the templates render properly

NOW = "2026-10-29T08:00:00+00:00"  # a Thursday, 08:00 UTC


def card_content(card_type: str, name: str, language: str = "de", *, wall: bool = False) -> str:
    """The markdown of one card, found by what it shows."""
    marker = {
        "hero": "ha-alert",
        "kid": "mdi:silverware-fork-knife",
        "board": "mdi:bulletin-board",
        "mail": "mdi:email-outline",
        "next": 'mdi:calendar"',
    }
    view = gen.build(language, [name])["views"][1 if wall else 0]
    for card in walk(view):
        if (
            card.get("type") == "markdown"
            and marker[card_type] in card["content"]
            and "{%" in card["content"]
        ):
            if card_type != "hero" or "namespace(missed" in card["content"]:
                return card["content"]
    raise AssertionError(card_type)


def set_states(hass: HomeAssistant, language: str = "de", **values) -> None:
    """Each value is `state` or `(state, attributes)`; keys name the entity."""
    ids = gen.Ids(language, "kind")
    names = {
        "today": ids.of_child("sensor", "status_today"),
        "tomorrow": ids.of_child("sensor", "status_tomorrow"),
        "deadline": ids.of_child("sensor", "next_deadline"),
        "pending": ids.account("sensor", "pending"),
        "closed": ids.account("binary_sensor", "closed_today"),
        "closed_tomorrow": ids.account("binary_sensor", "closed_tomorrow"),
        "board": ids.account("sensor", "board"),
        "mailbox": ids.account("sensor", "messages"),
        "upcoming": ids.account("sensor", "upcoming"),
    }
    for key, value in values.items():
        state, attributes = value if isinstance(value, tuple) else (value, {})
        hass.states.async_set(names[key], state, attributes)


def calm(**extra):
    base = {
        "today": "ordered",
        "tomorrow": "ordered",
        "pending": ("0", {"messages": []}),
        "closed": "off",
        "closed_tomorrow": "off",
        "deadline": "unknown",
    }
    base.update(extra)
    return base


def hero(hass: HomeAssistant, language: str = "de", name: str = "Mia", **values) -> str:
    set_states(hass, language, **values)
    content = card_content("hero", gen.PLACEHOLDER_NAME, language).replace("KIND", name)
    return " ".join(Template(content, hass).async_render(parse_result=False).split())


@pytest.fixture(autouse=True)
def fixed_time(freezer):
    freezer.move_to(NOW)


@pytest.mark.parametrize("language", LANGUAGES)
async def test_hero_a_missed_deadline_beats_everything(hass: HomeAssistant, language) -> None:
    t = gen.TEXT[language]
    out = hero(
        hass,
        language,
        **calm(
            today="missed",
            tomorrow="open",
            closed="on",
            pending=("1", {"messages": [{"titel": "X", "frist": None}]}),
        ),
    )
    assert 'alert-type="warning"' in out and t["missed_title"] in out and t["ask_kita"] in out
    assert 'alert-type="error"' not in out, "a meal that was left out on purpose is no alarm"
    assert "Mia" in out


async def test_hero_b_one_open_thing_names_it_and_counts_down_to_the_deadline(hass: HomeAssistant) -> None:
    out = hero(hass, **calm(tomorrow="open", deadline="2026-10-29T10:00:00+00:00"))
    assert 'alert-type="warning"' in out and "Eine Sache ist offen" in out
    assert "Essen für Mia morgen bestellen." in out
    assert "Frist heute" in out and "noch 2 Std." in out


async def test_hero_b_counts_several_things_and_mentions_the_rest(hass: HomeAssistant) -> None:
    reply = {"messages": [{"id": 1, "titel": "Einwilligung Ausflug", "frist": "2026-11-06"}]}
    out = hero(hass, **calm(tomorrow="open", pending=("1", reply), deadline="2026-10-29T08:20:00+00:00"))
    assert "2 Sachen sind offen" in out and "Dazu 1 weitere." in out and "noch 20 Min." in out


async def test_hero_b_a_reply_alone_shows_its_deadline(hass: HomeAssistant) -> None:
    reply = {"messages": [{"id": 1, "titel": "Einwilligung Ausflug", "frist": "2026-11-06"}]}
    out = hero(hass, **calm(pending=("1", reply)))
    assert (
        "Eine Sache ist offen" in out
        and "Rückmeldung: Einwilligung Ausflug" in out
        and "Antwort bis Fr 06.11." in out
    )


async def test_hero_b_two_children_only_one_open(hass: HomeAssistant) -> None:
    content = card_content("hero", gen.PLACEHOLDER_NAME)
    two = gen.dump(gen.build("de", ["Anna", "Ben"]))
    assert "sensor.anna_bestellstatus_heute" in two and "sensor.ben_bestellstatus_heute" in two
    for kid in ("anna", "ben"):
        hass.states.async_set(f"sensor.{kid}_bestellstatus_heute", "ordered")
        hass.states.async_set(f"sensor.{kid}_bestellstatus_morgen", "open" if kid == "ben" else "ordered")
        hass.states.async_set(f"sensor.{kid}_nachste_bestellfrist", "2026-10-29T10:00:00+00:00")
    set_states(hass, **calm())
    view = gen.build("de", ["Anna", "Ben"])["views"][0]
    hero_content = next(c["content"] for c in walk(view) if "namespace(missed" in c.get("content", ""))
    out = " ".join(Template(hero_content, hass).async_render(parse_result=False).split())
    assert "Eine Sache ist offen" in out and "Essen für Ben morgen bestellen." in out and "Anna" not in out
    assert content  # placeholder variant stays buildable


@pytest.mark.parametrize("language", LANGUAGES)
async def test_hero_c_a_closed_kita_says_why_and_whether_tomorrow_is_open(
    hass: HomeAssistant, language
) -> None:
    t = gen.TEXT[language]
    out = hero(hass, language, closed=("on", {"reason": "Brückentag"}))
    assert t["closed_title"] in out and "Brückentag" in out and t["tomorrow_open"] in out
    out = hero(hass, language, closed_tomorrow="on")
    assert t["tomorrow_closed"] in out


@pytest.mark.parametrize("language", LANGUAGES)
async def test_hero_d_nothing_to_do(hass: HomeAssistant, language) -> None:
    t = gen.TEXT[language]
    out = hero(hass, language, **calm())
    assert 'alert-type="info"' in out and t["calm_title"] in out and t["calm_ordered"] in out
    out = hero(hass, language, **calm(today="not_offered", tomorrow="not_offered"))
    assert t["calm_nothing"] in out


async def test_hero_says_so_when_there_is_no_data(hass: HomeAssistant) -> None:
    out = hero(hass, **calm(today="unavailable"))
    assert "Keine aktuellen Daten" in out


async def test_hero_open_without_a_known_deadline_still_works(hass: HomeAssistant) -> None:
    out = hero(hass, **calm(tomorrow="open", deadline="unknown"))
    assert "Essen für Mia morgen bestellen." in out and "Frist" not in out and "Error" not in out


async def test_hero_a_past_deadline_shows_no_countdown(hass: HomeAssistant) -> None:
    out = hero(hass, **calm(tomorrow="open", deadline="2026-10-29T07:00:00+00:00"))
    assert "noch" not in out


async def test_hero_long_names_and_titles_are_cut(hass: HomeAssistant) -> None:
    long_title = "Sehr langer Titel " * 20 + "https://example.com/" + "a" * 200
    reply = {"messages": [{"id": 1, "titel": long_title, "frist": "2026-11-06"}]}
    out = hero(hass, name="Maximilian-Alexander Friedrich-Wilhelm", **calm(pending=("1", reply)))
    assert len(out) < 400 and "a" * 40 not in out and "…" in out


@pytest.mark.parametrize("language", LANGUAGES)
async def test_kid_card_shows_state_words_icons_meals_and_deadline(hass: HomeAssistant, language) -> None:
    t = gen.TEXT[language]
    set_states(
        hass,
        language,
        today=("ordered", {"meal": "Nudeln"}),
        tomorrow=("not_offered", {"meal": "ignored"}),
        deadline="2026-10-29T10:00:00+00:00",
    )
    out = Template(
        card_content("kid", gen.PLACEHOLDER_NAME, language).replace("KIND", "Mia"), hass
    ).async_render(parse_result=False)
    assert t["state_words"]["ordered"] in out and t["state_words"]["not_offered"] in out
    assert "✓" in out and "–" in out
    assert "Nudeln" in out and "ignored" not in out
    assert t["next_deadline"] in out and t["today"] in out
    set_states(hass, language, today=("open", {"meal": ""}), tomorrow="missed", deadline="unavailable")
    out = Template(
        card_content("kid", gen.PLACEHOLDER_NAME, language).replace("KIND", "Mia"), hass
    ).async_render(parse_result=False)
    assert (
        t["state_words"]["open"] in out
        and t["state_words"]["missed"] in out
        and t["next_deadline"] not in out
    )


async def test_board_card_shows_only_the_newest_post_cleaned_up(hass: HomeAssistant) -> None:
    post = {
        "titel": "**Sommerfest** <b>2026</b> [Link](https://example.com)",
        "datum": "2026-10-28",
        "text": "Liebe Eltern,\n\n\tbitte  beachten: " + "wort " * 60,
    }
    set_states(
        hass, board=("Sommerfest", {"posts": [post, {"titel": "Alt", "datum": "2026-10-01", "text": "x"}]})
    )
    out = Template(card_content("board", "Mia"), hass).async_render(parse_result=False)
    assert "<b>" not in out and out.count("**") == 2 and "Alt" not in out
    assert "[" not in out and "](" not in out, "no links can be built from a title"
    assert "Mi 28.10." in out and "Liebe Eltern, bitte beachten:" in out and "…" in out


async def test_board_card_links_attached_files_only_through_this_integration(hass: HomeAssistant) -> None:
    files = [
        {"name": "Menüplan 02.11. -06.11", "url": "/api/kitaplus/attachment/abc/7?authSig=x"},
        {"name": "Fremd", "url": "https://evil.example/x"},
        {"name": "Ohne Adresse", "url": None},
    ]
    post = {"titel": "Mittagessen", "datum": "2026-10-28", "text": "", "attachments": files}
    set_states(hass, board=("Mittagessen", {"posts": [post]}))
    out = Template(card_content("board", "Mia"), hass).async_render(parse_result=False)
    assert 'href="/api/kitaplus/attachment/abc/7?authSig=x"' in out and 'target="_blank"' in out
    assert "Menüplan 02.11. -06.11</a>" in out and "evil.example" not in out
    wall = Template(card_content("board", "Mia", wall=True), hass).async_render(parse_result=False)
    assert "Anhang" in wall
    set_states(hass, board=("x", {"posts": [{"titel": "x", "datum": "2026-10-28", "text": ""}]}))
    out = Template(card_content("board", "Mia"), hass).async_render(parse_result=False)
    assert "Anhang" not in out


async def test_board_card_edge_cases(hass: HomeAssistant) -> None:
    set_states(hass, board=("unknown", {"posts": []}))
    out = Template(card_content("board", "Mia"), hass).async_render(parse_result=False)
    assert gen.TEXT["de"]["no_post"] in out
    set_states(hass, board=("", {"posts": [{"titel": "", "datum": "2026-10-28", "text": ""}]}))
    out = Template(card_content("board", "Mia"), hass).async_render(parse_result=False)
    assert gen.TEXT["de"]["untitled"] in out
    url = "https://example.com/" + "a" * 300
    set_states(hass, board=("x", {"posts": [{"titel": url, "datum": "2026-10-28", "text": url}]}))
    out = Template(card_content("board", "Mia"), hass).async_render(parse_result=False)
    assert "a" * 40 not in out
    wall = Template(card_content("board", "Mia", wall=True), hass).async_render(parse_result=False)
    assert "a" * 40 not in wall


async def test_mail_card_lists_two_messages_and_marks_the_one_that_needs_a_reply(hass: HomeAssistant) -> None:
    items = [
        {"id": 7, "titel": "Elternabend", "datum": "2026-10-28T09:00:00+01:00"},
        {"id": 8, "titel": "Ausflug", "datum": "2026-10-27"},
        {"id": 9, "titel": "Dritte", "datum": "2026-10-26"},
    ]
    set_states(
        hass,
        mailbox=("3", {"messages": items}),
        pending=("1", {"messages": [{"id": 8, "titel": "Ausflug", "frist": "2026-11-06"}]}),
    )
    out = Template(card_content("mail", "Mia"), hass).async_render(parse_result=False)
    assert "3 Nachrichten" in out and "Elternabend" in out and "Ausflug" in out and "Dritte" not in out
    assert out.count("Rückmeldung bis") == 1 and "Fr 06.11." in out
    wall = Template(card_content("mail", "Mia", wall=True), hass).async_render(parse_result=False)
    assert "Elternabend" in wall and "Ausflug" not in wall
    set_states(
        hass,
        mailbox=("1", {"messages": [{"id": 1, "titel": None, "datum": None}]}),
        pending=("0", {"messages": []}),
    )
    out = Template(card_content("mail", "Mia"), hass).async_render(parse_result=False)
    assert gen.TEXT["de"]["untitled"] in out and "None" not in out
    assert "1 Nachricht\n" in out or "1 Nachricht " in out and "1 Nachrichten" not in out


@pytest.mark.parametrize("language", LANGUAGES)
async def test_next_card_lists_entries_and_marks_closures(hass: HomeAssistant, language) -> None:
    t = gen.TEXT[language]
    entries = [
        {"datum": "2026-10-30", "zeit": None, "titel": "Brückentag", "schliesstag": True},
        {"datum": "2026-11-02", "zeit": "17:00", "titel": "Elternabend", "schliesstag": False},
        {"datum": "2026-11-05", "zeit": None, "titel": "", "schliesstag": False},
        {"datum": "2026-11-06", "zeit": None, "titel": "Vierter", "schliesstag": False},
    ]
    set_states(hass, language, upcoming=("Brückentag", {"entries": entries}))
    out = Template(card_content("next", "Mia", language), hass).async_render(parse_result=False)
    assert "Brückentag" in out and t["closure"] in out and "17:00" in out and t["untitled"] in out
    assert "Vierter" not in out
    wall = Template(card_content("next", "Mia", language, wall=True), hass).async_render(parse_result=False)
    assert "Elternabend" in wall and t["untitled"] not in wall
    set_states(hass, language, upcoming=("unknown", {"entries": []}))
    out = Template(card_content("next", "Mia", language), hass).async_render(parse_result=False)
    assert t["no_dates"] in out


@pytest.mark.parametrize("language", LANGUAGES)
async def test_the_header_shows_the_date(hass: HomeAssistant, language) -> None:
    view = gen.build(language, ["Mia"])["views"][0]
    header = next(c["content"] for c in walk(view) if c.get("text_only"))
    out = Template(header, hass).async_render(parse_result=False)
    assert gen.TEXT[language]["app"] in out and (
        "Donnerstag" in out or "Thursday" in out or "Mittwoch" in out or "Wednesday" in out
    )
    wall_header = next(
        c["content"] for c in walk(gen.build(language, ["Mia"])["views"][1]) if c.get("text_only")
    )
    assert "{{ now().day }}" in wall_header


# --------------------------------------------------------------------------------- layout of the design


def test_phone_is_one_column_and_the_wall_has_three(hass=None) -> None:
    for language in LANGUAGES:
        views = {v["path"]: v for v in gen.build(language)["views"]}
        assert views["heute"]["max_columns"] == 1 and len(views["heute"]["sections"]) == 3
        assert views["wand"]["max_columns"] == 3 and len(views["wand"]["sections"]) == 3
        assert "kalender" in views


def test_the_phone_order_is_status_kids_then_lists() -> None:
    first = gen.build("de")["views"][0]["sections"]
    assert "ha-alert" in first[0]["cards"][1]["content"]
    assert [c["type"] for c in first[0]["cards"]] == ["markdown", "markdown", "tile", "tile"]
    assert first[2]["cards"][-1]["type"] == "tile", "the balance comes last"


def test_several_children_each_get_a_card_and_a_calendar() -> None:
    dash = gen.build("de", ["Anna", "Ben"])
    kids = dash["views"][0]["sections"][1]["cards"]
    assert len(kids) == 2 and "Anna" in kids[0]["content"] and "Ben" in kids[1]["content"]
    calendar = next(c for c in walk(dash["views"][2]) if c.get("type") == "calendar")
    assert (
        "calendar.anna_bestelltes_essen" in calendar["entities"]
        and "calendar.ben_bestelltes_essen" in calendar["entities"]
    )


@pytest.mark.parametrize("language", LANGUAGES)
def test_templates_only_use_the_two_placeholders_the_readme_explains(language) -> None:
    """`KIND` (shown name) and `kind` (part of entity ids) are the only things a user has to replace."""
    for name, text in all_files(language).items():
        body = "\n".join(line for line in text.splitlines() if not line.startswith("#"))
        cleaned = body.replace(".kind_", ".x_").replace("KIND", "X")
        assert not re.search(r"\bkind\b", cleaned, re.IGNORECASE), f"{name}: stray placeholder"


# ------------------------------------------------------------------------------------- the layout


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_dashboard_file_starts_with_its_version_and_the_integration_it_needs(language) -> None:
    import json

    version = json.loads((ROOT / "custom_components" / "kitaplus" / "manifest.json").read_text())["version"]
    for name, text in all_files(language).items():
        first = text.splitlines()[0]
        assert version in first and gen.MIN_INTEGRATION in first, (
            f"{name}: stale, run scripts/bump_version.py"
        )


@pytest.mark.parametrize("language", LANGUAGES)
async def test_a_template_with_the_placeholders_still_in_it_says_what_to_do(
    hass: HomeAssistant, language
) -> None:
    """Replacing KIND and kind is the one thing to do; forgetting it must not look like an outage."""
    t = gen.TEXT[language]
    out = hero(hass, language, name=gen.PLACEHOLDER_NAME, **calm(today="unknown", tomorrow="unknown"))
    assert t["todo_title"] in out and "KIND" in out and t["nodata_title"] not in out
    out = hero(hass, language, name="Mia", **calm(today="unknown", tomorrow="unknown"))
    assert t["nodata_title"] in out and t["todo_title"] not in out


@pytest.mark.parametrize("language", LANGUAGES)
async def test_the_child_card_of_an_unfinished_template_explains_instead_of_showing_unknown(
    hass: HomeAssistant, language
) -> None:
    t = gen.TEXT[language]
    set_states(hass, language, today="unknown", tomorrow="unknown")
    out = Template(card_content("kid", gen.PLACEHOLDER_NAME, language), hass).async_render(parse_result=False)
    assert t["todo_kid"] in out and t["state_words"]["unknown"] not in out
    named = card_content("kid", "Mia", language)
    out = Template(named, hass).async_render(parse_result=False)
    assert t["todo_kid"] not in out and t["state_words"]["unknown"] in out, (
        "a real child is not told to set up"
    )


@pytest.mark.parametrize("language", LANGUAGES)
async def test_the_child_card_shows_the_dish_from_the_menu_plan_with_a_note(
    hass: HomeAssistant, language
) -> None:
    t = gen.TEXT[language]
    ids = gen.Ids(language, "kind")
    set_states(
        hass, language, today=("ordered", {"meal": "Mittagessen"}), tomorrow=("open", {"meal": "Mittagessen"})
    )
    hass.states.async_set(
        ids.account("sensor", "menu_today"), "Nudeln", {"vegetarian": True, "uncertain": False}
    )
    hass.states.async_set(
        ids.account("sensor", "menu_tomorrow"), "Ge?ügel", {"vegetarian": False, "uncertain": True}
    )
    content = card_content("kid", gen.PLACEHOLDER_NAME, language).replace("KIND", "Mia")
    out = Template(content, hass).async_render(parse_result=False)
    assert "Nudeln" in out and t["vegetarian"] in out and "Mittagessen" not in out
    assert "Ge" in out and t["check_plan"] in out, "an uncertain dish asks to check the plan"
    assert t["from_plan"] in out
    hass.states.async_set(ids.account("sensor", "menu_today"), "unknown")
    hass.states.async_set(ids.account("sensor", "menu_tomorrow"), "unknown")
    out = Template(content, hass).async_render(parse_result=False)
    assert "Mittagessen" in out and t["from_plan"] not in out, "without a plan the card is as before"
