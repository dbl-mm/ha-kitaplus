"""Check that no real data from docs/_raw ended up in a file Git tracks.

Usage: python3 -I scripts/privacy_scan.py     (run before every commit)
Compares every tracked text file with the values in docs/_raw (never committed):
numbers >= 1000, names, addresses, bank data, e-mail addresses and tokens.
Exit code 1 if anything is found. Prints counts and file names, never the values.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

RAW = Path("docs/_raw")
TEXT_KEYS = {
    "email", "vorname", "nachname", "benutzername", "telefon", "mobil", "strasse", "plz", "ort",
    "ueberweisungEmpfaengerIban", "bankkontoIban", "geburtsdatum", "name", "titel", "bezeichnung",
    "verwendungszweck", "text",
}  # fmt: skip
# Made-up addresses used by the tests, the GitHub noreply address, and file names like icon@2x.png.
ALLOWED_EMAIL_DOMAINS = ("b.de", "example.de", "example.com", "users.noreply.github.com")
# Everyday words that also occur in the real data and are not personal ("Mittagessen" means lunch).
GENERIC_WORDS = {"mittagessen"}
# Fixed strings from public specifications that can look like data (the year inside the YAML tag namespace).
BENIGN = ("tag:yaml.org,2002:",)
IMAGE_SUFFIX = re.compile(r"@\dx\.(png|jpg|webp)$")


def collect() -> tuple[set[int], set[str]]:
    numbers: set[int] = set()
    texts: set[str] = set()

    def walk(value, key=""):
        if isinstance(value, dict):
            for k, v in value.items():
                walk(v, k)
        elif isinstance(value, list):
            for v in value:
                walk(v, key)
        elif isinstance(value, int) and not isinstance(value, bool) and abs(value) >= 1000:
            numbers.add(value)
        elif isinstance(value, str) and key in TEXT_KEYS and len(value.strip()) >= 5:
            texts.add(value.strip().lower())

    for path in RAW.glob("*.json"):
        walk(json.loads(path.read_text()))
    return numbers, texts


def main() -> int:
    if not RAW.exists():
        print("docs/_raw not found: nothing to compare against (skipped)")
        return 0
    numbers, texts = collect()
    tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.split()
    findings: list[str] = []
    for name in tracked:
        if name.endswith((".png", ".zip")):
            continue
        content = Path(name).read_text(encoding="utf-8", errors="ignore")
        for benign in BENIGN:
            content = content.replace(benign, "")
        lowered = content.lower()
        hits = sum(1 for n in numbers if re.search(rf"(?<![\d.]){n}(?![\d.])", content))
        hits_text = sum(1 for t in texts - GENERIC_WORDS if t in lowered)
        found = {
            m.group(0).lower() for m in re.finditer(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}", content)
        }
        emails = {e for e in found if not IMAGE_SUFFIX.search(e) and not e.endswith(ALLOWED_EMAIL_DOMAINS)}
        token = bool(re.search(r"eyJ[A-Za-z0-9_-]{10,}\.|Bearer\s+[A-Za-z0-9._-]{30,}", content))
        if hits or hits_text or emails or token:
            findings.append(f"{name}: numbers={hits} texts={hits_text} emails={len(emails)} token={token}")
    print(f"{len(tracked)} tracked files checked against {len(numbers)} numbers and {len(texts)} texts")
    for line in findings:
        print("FOUND", line)
    print("OK, nothing found" if not findings else f"{len(findings)} file(s) need attention")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
