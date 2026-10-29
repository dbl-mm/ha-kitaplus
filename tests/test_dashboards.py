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


@pytest.mark.parametrize("language", LANGUAGES)
def test_templates_only_use_the_two_placeholders_the_readme_explains(language) -> None:
    """`KIND` (shown name) and `kind` (part of entity ids) are the only things a user has to replace."""
    for name, text in all_files(language).items():
        body = "\n".join(line for line in text.splitlines() if not line.startswith("#"))
        cleaned = body.replace(".kind_", ".x_").replace("KIND", "X")
        assert not re.search(r"\bkind\b", cleaned, re.IGNORECASE), f"{name}: stray placeholder"
        assert (
            ".kind_" in body
            or name.endswith(("status.yaml", "guthaben.yaml", "balance.yaml"))
            or "calendar" in name
            or "bulletin" in name
            or "schwarzes" in name
            or "mailbox" in name
            or "postfach" in name
        ), name


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


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_first_view_answers_what_needs_attention_before_the_details(language) -> None:
    today = yaml.safe_load(all_files(language)[f"kitaplus_{language}.yaml"])["views"][0]
    headings = [c["heading"] for s in today["sections"] for c in s["cards"] if c.get("type") == "heading"]
    t = gen.TEXT[language]
    assert headings[:2] == [t["kita"], t["todo"]], "status first, then what to do, then the children"
    todo = today["sections"][1]["cards"]
    assert all(c["type"] in ("heading", "conditional") for c in todo), (
        "the to-do area only shows what is needed"
    )
    assert any(c.get("card", {}).get("title") == t["all_done"] for c in todo), (
        "and a calm card when it is empty"
    )


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


@pytest.mark.parametrize("language", LANGUAGES)
def test_several_children_each_get_their_own_section_and_calendar(language) -> None:
    data = gen.build(language, ["Anna", "Jörg"])
    text = gen.dump(data)
    for slug, shown in (("anna", "Anna"), ("jorg", "Jörg")):
        assert f"sensor.{slug}_{gen.SLUGS[language]['meal_today']}" in text
        assert f"calendar.{slug}_{gen.SLUGS[language]['meals']}" in text
        assert any(c.get("heading") == shown for s in data["views"][0]["sections"] for c in s["cards"])
    assert "kind_" not in text and "KIND" not in text, "no placeholder is left"


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
