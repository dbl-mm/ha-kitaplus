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

from .common import setup_integration

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
    "history-graph",
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
    await setup_integration(hass, stack)
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


def markdown_cards(language: str):
    for card in walk(gen.build(language, [CHILD])):
        if card.get("type") == "markdown" and "{%" in card["content"]:
            yield card["content"]


@pytest.mark.parametrize("language", LANGUAGES)
async def test_markdown_cards_render_with_real_states(hass: HomeAssistant, stack, language) -> None:
    from .test_blueprints import needs_reply

    hass.config.language = language
    await setup_integration(hass, stack, async_get_messages=[needs_reply()])
    rendered = [
        Template(content, hass).async_render(parse_result=False) for content in markdown_cards(language)
    ]
    text = "\n".join(rendered)
    assert len(rendered) == 3, "open replies, bulletin board and mailbox"
    assert "titel-" in text, "the bulletin board shows post titles from the attribute"
    assert "Einwilligung Ausflug" in text, "the open reply is listed with its title"
    if language == "de":
        assert "bis 20.06." in text and re.search(r"\b\d{2}\.\d{2}\.\d{4}\b", text)
    else:
        assert "due 06-20" in text and re.search(r"\b\d{4}-\d{2}-\d{2}\b", text)
    for forbidden in ("None", "Undefined", "Error"):
        assert forbidden not in text, forbidden


@pytest.mark.parametrize("language", LANGUAGES)
async def test_empty_lists_say_so_instead_of_showing_nothing(hass: HomeAssistant, stack, language) -> None:
    hass.config.language = language
    await setup_integration(hass, stack, async_get_board=[], async_get_messages=[])
    t = gen.TEXT[language]
    text = "\n".join(Template(c, hass).async_render(parse_result=False) for c in markdown_cards(language))
    assert t["no_posts"] in text and t["no_messages"] in text


@pytest.mark.parametrize("language", LANGUAGES)
def test_templates_only_use_the_two_placeholders_the_readme_explains(language) -> None:
    """`KIND` (shown name) and `kind` (part of entity ids) are the only things a user has to replace."""
    for name, text in all_files(language).items():
        body = "\n".join(line for line in text.splitlines() if not line.startswith("#"))
        cleaned = body.replace(".kind_", ".x_").replace("KIND", "X")
        assert not re.search(r"\bkind\b", cleaned, re.IGNORECASE), f"{name}: stray placeholder"


# ------------------------------------------------------------------------------------- the layout


def first_view(language: str) -> dict:
    return yaml.safe_load(gen.dump(gen.build(language)))["views"][0]


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_dashboard_is_small_and_has_no_diagnostics_or_charts(language) -> None:
    """Less is more: three views, one calendar, no chart with a single dot, no technical view."""
    t = gen.TEXT[language]
    views = yaml.safe_load(gen.dump(gen.build(language)))["views"]
    assert [v["title"] for v in views] == [t["view_today"], t["view_messages"], t["view_calendar"]]
    text = gen.dump(gen.build(language))
    assert "history-graph" not in text and "type: entities" not in text
    assert text.count("type: calendar") == 1, "the calendar card brings its own list/week/month switch"
    assert text.count(t["balance"] + "\n") <= 2, (
        "the balance is mentioned once as a tile (plus the section title)"
    )


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_action_area_has_no_heading_so_it_disappears_when_there_is_nothing_to_do(language) -> None:
    sections = first_view(language)["sections"]
    todo = sections[0]["cards"]
    assert all(card["type"] == "conditional" for card in todo), (
        "only conditional cards, nothing always visible"
    )
    assert len(todo) == 3, "today open, tomorrow open, replies needed"
    t = gen.TEXT[language]
    headings = [c["heading"] for s in sections[1:] for c in s["cards"] if c.get("type") == "heading"]
    assert headings == [t["kita"], gen.PLACEHOLDER_NAME, t["account"]], (
        "Kita, then each child, then the account"
    )


@pytest.mark.parametrize("language", LANGUAGES)
def test_each_fact_is_shown_once_and_each_child_needs_just_two_tiles(language) -> None:
    sections = first_view(language)["sections"]
    child = next(s for s in sections if any(c.get("heading") == gen.PLACEHOLDER_NAME for c in s["cards"]))
    tiles = [c for c in child["cards"] if c["type"] == "tile"]
    slugs = gen.SLUGS[language]
    assert [c["entity"] for c in tiles] == [
        f"sensor.kind_{slugs['status_today']}",
        f"sensor.kind_{slugs['status_tomorrow']}",
    ]
    assert all(c["state_content"] == ["state", "meal"] for c in tiles), "e.g. 'Bestellt · Mittagessen'"
    entities = [c["entity"] for s in sections for c in iter_cards(s) if c.get("type") == "tile"]
    visible = [e for e in entities if e.endswith(slugs["balance"])]
    assert len(visible) == 1


@pytest.mark.parametrize("language", LANGUAGES)
def test_several_children_each_get_their_own_section_and_calendar(language) -> None:
    data = gen.build(language, ["Anna", "Jörg"])
    text = gen.dump(data)
    slugs = gen.SLUGS[language]
    for slug, shown in (("anna", "Anna"), ("jorg", "Jörg")):
        assert f"sensor.{slug}_{slugs['status_today']}" in text
        assert f"sensor.{slug}_{slugs['status_tomorrow']}" in text
        assert f"calendar.{slug}_{slugs['meals']}" in text
        assert any(c.get("heading") == shown for s in data["views"][0]["sections"] for c in s["cards"])
    names = [
        c["name"]
        for c in iter_cards(data["views"][0]["sections"][0])
        if c.get("type") == "tile" and "Anna" in c["name"]
    ]
    assert len(names) == 2, "with several children the reminders say whose meal it is"
    assert "kind_" not in text and "KIND" not in text, "no placeholder is left"


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_order_reminder_only_shows_while_ordering_is_still_possible(language) -> None:
    """A missed deadline must never produce a "please order" card: there is nothing left to do about it."""
    slugs = gen.SLUGS[language]
    for name, text in design_subjects(language).items():
        for card in iter_cards(yaml.safe_load(text)):
            for condition in card.get("conditions", []):
                if str(condition.get("entity", "")).endswith(
                    (slugs["status_today"], slugs["status_tomorrow"])
                ):
                    assert condition == {
                        "condition": "state",
                        "entity": condition["entity"],
                        "state": "open",
                    }, f"{name}: only 'open' may show a reminder, never 'missed'"
    reminders = [
        c for c in first_view(language)["sections"][0]["cards"] if c["conditions"][0].get("state") == "open"
    ]
    assert len(reminders) == 2, "one for today and one for tomorrow"
    for reminder in reminders:
        deadline, meal = reminder["card"]["cards"][1], reminder["card"]["cards"][0]
        assert deadline["entity"].endswith(slugs["next_deadline"]), (
            "the deadline sits right under the reminder"
        )
        assert meal["state_content"] == ["meal"], "the reminder names the meal instead of repeating the state"


@pytest.mark.parametrize("language", LANGUAGES)
async def test_markup_a_kita_puts_into_titles_and_texts_never_shows_up_as_stray_signs(
    hass, stack, language
) -> None:
    """A Kita wrote `**Gartenfest **` as a title. The card shows a clean bold title, not raw asterisks."""
    hass.config.language = language
    post = {
        "id": 1,
        "datum": "2026-10-28T09:00:00",
        "titel": "**Gartenfest **",
        "text": "Erste Zeile\n**fett** und _kursiv_ " + "wort " * 80,
    }
    await setup_integration(hass, stack, async_get_board=[post])
    board = next(c for c in markdown_cards(language) if "'posts'" in c)
    rendered = Template(board, hass).async_render(parse_result=False)
    assert "**Gartenfest**" in rendered, "title cleaned and bolded once"
    assert "****" not in rendered and "** " not in rendered.replace("**Gartenfest**", "")
    excerpt = next(line for line in rendered.splitlines() if line.startswith("Erste Zeile"))
    assert "Erste Zeile fett und kursiv" in excerpt, "line breaks and markup signs are gone"
    assert len(excerpt) <= gen.EXCERPT + 3 and excerpt.endswith("..."), "the text is shortened"


@pytest.mark.parametrize("language", LANGUAGES)
async def test_the_message_lists_are_limited_to_what_fits_on_a_dashboard(hass, stack, language) -> None:
    hass.config.language = language
    posts = [
        {"id": n, "datum": "2026-10-28T09:00:00", "titel": f"Beitrag {n}", "text": "x"} for n in range(1, 6)
    ]
    await setup_integration(hass, stack, async_get_board=posts)
    board = next(c for c in markdown_cards(language) if "'posts'" in c)
    rendered = Template(board, hass).async_render(parse_result=False)
    assert rendered.count("Beitrag") == gen.BOARD_ITEMS
