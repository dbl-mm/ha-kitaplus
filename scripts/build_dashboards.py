"""Write the KitaPlus dashboard templates (German and English) into dashboards/.

Usage:
    python3 scripts/build_dashboards.py                        # rewrite dashboards/ for all languages
    python3 scripts/build_dashboards.py --language de --children Anna,Ben
        prints a dashboard for your children (names as they appear in Home Assistant), guessing entity ids

The generator itself lives in custom_components/kitaplus/dashboard.py, because the integration uses it too (the
action `kitaplus.dashboard_yaml`). That action is the better way for users: it reads the real entity ids.
Needs PyYAML (the project environment has it).
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "kitaplus_dashboard", ROOT / "custom_components" / "kitaplus" / "dashboard.py"
)
assert _spec and _spec.loader
gen = importlib.util.module_from_spec(_spec)
sys.modules["kitaplus_dashboard"] = gen  # dataclasses and typing look the module up by name
_spec.loader.exec_module(gen)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--language", choices=sorted(gen.TEXT))
    parser.add_argument("--children", help="comma separated first names, e.g. Anna,Ben")
    args = parser.parse_args()
    if args.children:
        if not args.language:
            parser.error("--children needs --language")
        names = [n.strip() for n in args.children.split(",") if n.strip()]
        text = gen.dump(gen.build(args.language, names), gen.header(args.language, first_line_only=True))
        sys.stdout.write(text)
        return 0
    for path in gen.write_all(ROOT / "dashboards"):
        print("wrote", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
