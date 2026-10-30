"""Set the integration version in manifest.json and stamp it into blueprints and dashboards.

Usage: python3 scripts/bump_version.py 0.2.0
The version must match the git tag (v0.2.0), because HACS compares the installed
version with the latest GitHub release.

Every blueprint ends its description with "Version X · benötigt KitaPlus ab Y · Home Assistant ab Z", and
every dashboard file starts with a version comment. X follows the release, Y is the oldest integration that
offers everything the file uses (kept in MINIMUM below), so users see at a glance what a file needs.
tests/test_blueprints.py and tests/test_dashboards.py fail when a stamp is stale.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "custom_components" / "kitaplus" / "manifest.json"
BLUEPRINTS = ROOT / "blueprints" / "automation" / "kitaplus"
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
STAMP = re.compile(
    r"^    \*Version [\d.]+ · benötigt KitaPlus ab [\d.]+ · Home Assistant ab [\d.]+\*\n", re.M
)

# The oldest integration version each blueprint works with (entities and events it needs).
MINIMUM = {
    "bestellfrist_erinnerung.yaml": "0.3.0",  # event kitaplus_order_deadline and the deadline option
    "essen_erinnerung.yaml": "0.2.0",
    "guthaben_niedrig.yaml": "0.2.0",
    "neue_mitteilung.yaml": "0.2.0",
    "rueckmeldung_erinnerung.yaml": "0.2.0",
    "schliesstag.yaml": "0.2.0",
    "sitzung_laeuft_ab.yaml": "0.2.0",
    "tagesbriefing.yaml": "0.2.0",
}
HOME_ASSISTANT = "2025.8"


def stamp_text(name: str, version: str) -> str:
    needs = f"benötigt KitaPlus ab {MINIMUM[name]} · Home Assistant ab {HOME_ASSISTANT}"
    return f"    *Version {version} · {needs}*\n"


def stamp_blueprints(version: str) -> None:
    for path in sorted(BLUEPRINTS.glob("*.yaml")):
        text = path.read_text()
        stamp = stamp_text(path.name, version)
        if STAMP.search(text):
            text = STAMP.sub(stamp, text, count=1)
        else:  # first time: at the end of the description, before `domain:`
            marker = "\n  domain: automation\n"
            assert marker in text, path.name
            text = text.replace(marker, "\n\n" + stamp + marker.lstrip("\n"), 1)  # blank line, stamp, domain
        path.write_text(text)


def main() -> int:
    if len(sys.argv) != 2 or not SEMVER.match(sys.argv[1]):
        print("usage: bump_version.py MAJOR.MINOR.PATCH")
        return 1
    data = json.loads(MANIFEST.read_text())
    old, data["version"] = data["version"], sys.argv[1]
    MANIFEST.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    stamp_blueprints(sys.argv[1])
    venv = ROOT / ".venv" / "bin" / "python"  # the generator needs PyYAML, which the project environment has
    python = str(venv) if venv.exists() else sys.executable
    subprocess.run([python, str(ROOT / "scripts" / "build_dashboards.py")], cwd=ROOT, check=True)
    print(f"{old} -> {sys.argv[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
