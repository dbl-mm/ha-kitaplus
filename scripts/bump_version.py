"""Set the integration version in manifest.json.

Usage: python3 scripts/bump_version.py 0.2.0
The version must match the git tag (v0.2.0), because HACS compares the installed
version with the latest GitHub release.
"""

import json
import re
import sys
from pathlib import Path

MANIFEST = Path("custom_components/kitaplus/manifest.json")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def main() -> int:
    if len(sys.argv) != 2 or not SEMVER.match(sys.argv[1]):
        print("usage: bump_version.py MAJOR.MINOR.PATCH")
        return 1
    data = json.loads(MANIFEST.read_text())
    old, data["version"] = data["version"], sys.argv[1]
    MANIFEST.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"{old} -> {sys.argv[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
