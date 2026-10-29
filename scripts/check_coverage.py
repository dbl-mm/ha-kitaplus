"""Fail unless every module of the integration has at least MIN percent test coverage.

Usage:
    pytest --cov=custom_components.kitaplus --cov-report=json
    python3 scripts/check_coverage.py [MIN]      (default 95, the Silver rule `test-coverage`)
"""

import json
import sys
from pathlib import Path


def main() -> int:
    minimum = float(sys.argv[1]) if len(sys.argv) > 1 else 95.0
    report = json.loads(Path("coverage.json").read_text())
    failures = []
    for name, data in sorted(report["files"].items()):
        percent = data["summary"]["percent_covered"]
        if percent < minimum:
            failures.append(f"{name}: {percent:.1f}% < {minimum:.0f}%")
    print(f"{len(report['files'])} modules checked, minimum {minimum:.0f}%")
    for line in failures:
        print("TOO LOW", line)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
