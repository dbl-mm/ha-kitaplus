"""hassfest does not enforce the quality scale for HACS integrations, so these tests do.

They compare quality_scale.yaml with the official rule list and with the code, so a claim such as
"done" cannot silently go stale.
"""

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent / "custom_components" / "kitaplus"

# The 54 rules up to Platinum, from https://contributors.home-assistant.io/core/quality-scale/rules/
BRONZE = """action-setup appropriate-polling brands common-modules config-flow config-flow-test-coverage
dependency-transparency docs-actions docs-conditions docs-high-level-description
docs-installation-instructions docs-removal-instructions docs-triggers entity-event-setup
entity-unique-id has-entity-name runtime-data test-before-configure test-before-setup
unique-config-entry""".split()
SILVER = """action-exceptions config-entry-unloading docs-configuration-parameters
docs-installation-parameters entity-unavailable integration-owner log-when-unavailable
parallel-updates reauthentication-flow test-coverage""".split()
GOLD = """devices diagnostics discovery discovery-update-info docs-data-update docs-examples
docs-known-limitations docs-supported-devices docs-supported-functions docs-troubleshooting
docs-use-cases dynamic-devices entity-category entity-device-class entity-disabled-by-default
entity-translations exception-translations icon-translations reconfiguration-flow repair-issues
stale-devices""".split()
PLATINUM = ["async-dependency", "inject-websession", "strict-typing"]


def _rules() -> dict:
    return yaml.safe_load((ROOT / "quality_scale.yaml").read_text())["rules"]


def _json(name: str) -> dict:
    return json.loads((ROOT / name).read_text())


def test_all_54_rules_are_listed_exactly_once() -> None:
    expected = set(BRONZE + SILVER + GOLD + PLATINUM)
    assert len(expected) == 54
    assert set(_rules()) == expected


def test_nothing_is_open_and_every_status_is_explained() -> None:
    for slug, rule in _rules().items():
        assert rule["status"] in ("done", "exempt"), f"{slug} is {rule['status']}"
        assert len(rule.get("comment", "")) >= 20, f"{slug} needs a real explanation"


def test_the_manifest_claims_exactly_what_the_file_supports() -> None:
    manifest = _json("manifest.json")
    assert manifest["quality_scale"] == "platinum"
    assert list(manifest)[:2] == ["domain", "name"]  # hassfest wants these first, the rest sorted
    assert list(manifest)[2:] == sorted(list(manifest)[2:])
    # dependency-transparency: one external library, pinned exactly, used only by the optional menu reader
    assert manifest["requirements"] == ["pypdf==6.21.4"]


def test_every_platform_sets_parallel_updates() -> None:
    for name in ("sensor.py", "binary_sensor.py", "calendar.py"):
        assert re.search(r"^PARALLEL_UPDATES = 0", (ROOT / name).read_text(), re.M), name


def test_icons_come_from_icons_json_not_from_code() -> None:
    for path in ROOT.glob("*.py"):
        assert "_attr_icon" not in path.read_text(), path.name
    entities = _json("strings.json")["entity"]
    for platform, keys in _json("icons.json")["entity"].items():
        assert set(keys) <= set(entities[platform]), (
            f"icons.json knows keys that strings.json lacks: {platform}"
        )


def test_brand_images_exist() -> None:
    for name in ("icon.png", "icon@2x.png", "dark_icon.png", "logo.png", "logo@2x.png", "dark_logo.png"):
        assert (ROOT / "brand" / name).stat().st_size > 1000, name


def test_translations_have_the_same_keys_as_strings_json() -> None:
    def keys(node, prefix=""):
        if isinstance(node, dict):
            return {k for key, value in node.items() for k in keys(value, f"{prefix}{key}.")}
        return {prefix}

    reference = keys(_json("strings.json"))
    for name in ("translations/en.json", "translations/de.json"):
        assert keys(_json(name)) == reference, name


def test_every_form_field_has_a_description() -> None:
    strings = _json("strings.json")
    for step, content in strings["config"]["step"].items():
        assert set(content["data"]) <= set(content["data_description"]), step
    options = strings["options"]["step"]["init"]
    assert set(options["data"]) <= set(options["data_description"])


def test_translation_keys_used_in_the_code_exist_in_strings() -> None:
    strings = _json("strings.json")
    defined = set(strings["exceptions"]) | set(strings["issues"])
    in_code: set[str] = set()
    aborts: set[str] = set()
    errors: set[str] = set()
    for path in ROOT.glob("*.py"):
        text = path.read_text()
        for line in text.splitlines():
            if "translation_key" in line and "_attr_translation_key" not in line:
                in_code |= set(re.findall(r'"([a-z_]+)"', line))
        aborts |= set(re.findall(r'reason="([a-z_]+)"', text))
        errors |= set(re.findall(r'return None, "([a-z_]+)"', text))
    in_code -= {"translation_key", "translation_domain"}
    assert in_code, "the code no longer uses translated errors?"
    assert in_code <= defined, f"missing in strings.json: {in_code - defined}"
    assert aborts - {"reauth_successful", "reconfigure_successful"} <= set(strings["config"]["abort"])
    assert errors - {"two_factor"} <= set(strings["config"]["error"])


def test_the_session_sensor_is_the_only_diagnostic_and_disabled_entity() -> None:
    source = (ROOT / "sensor.py").read_text()
    assert source.count("EntityCategory.DIAGNOSTIC") == 1
    assert source.count("_attr_entity_registry_enabled_default = False") == 1
