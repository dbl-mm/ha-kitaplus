"""Create anonymised test fixtures from the raw API answers.

Usage: python3 -I scripts/anonymize_fixtures.py
Reads docs/_raw/*.json (never committed), writes tests/fixtures/*.json.

What is kept: structure, booleans, plan dates and meal prices (needed by the tests).
What is replaced: every id (consistently, so relations still match), every amount,
every timestamp of record creation, and every other string.
What is dropped: contact data, documents, bank details, login data.
Review the output before committing.
"""

import json
import re
from datetime import date, timedelta
from pathlib import Path

RAW = Path("docs/_raw")
OUT = Path("tests/fixtures")
FILES = [
    "termine",
    "schwarzesbrett",
    "getNachrichten",
    "bestelldaten",
    "get_einrichtungen_kinder",
    "buchungen",
    "abwesenheiten",
    "jahresansicht",
]
KEEP_STRINGS = {
    "datum",
    "startdatum",
    "enddatum",
    "abrufDatum",
    "bestellDatum",
    "buchungsdatum",
    "leistungsdatum",
    "wertstellungsdatum",
    "ende",
    "rueckmeldefrist",
    "preis",
    "monat",
    "mimeType",
    "endung",
    "minDate",
    "maxDate",
}
DROP_KEYS = {
    "kindKontakte",
    "kindDokumente",
    "systemExtern",
    "ueberweisungEmpfaengerQrCode",
    "vppTechInfos",
    "vppTechInfosSign",
    "ueberweisungEmpfaengerIban",
    "ueberweisungEmpfaengerBic",
    "email",
    "benutzername",
    "letzterLogin",
    "ip",
}
AMOUNT_KEYS = {"kontostand", "betrag", "summe"}
TIMESTAMP_KEYS = {"createdAt", "updatedAt"}
FIXED_TIMESTAMP = "2026-01-01T00:00:00"
# Real calendar days reveal behaviour (which days a child eats, when messages arrived).
# Every date is moved by the same offset, so the plan keeps its shape.
DATE_SHIFT = timedelta(days=-137)
ISO_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
# Default-deny: every whole number >= 1000 is treated as an identifier or a fingerprint
# (ids, external ids, file sizes) and replaced. Only these keys keep their value.
KEEP_NUMBERS = {"total", "limit", "start", "page"}
BIG_NUMBER = 1000

counter: dict[str, int] = {}
id_map: dict[int, int] = {}


def label(key: str) -> str:
    counter[key] = counter.get(key, 0) + 1
    return f"{key}-{counter[key]}"


def fake_id(value: int) -> int:
    """Same real id -> same fake id in every file, so relations still match."""
    return id_map.setdefault(value, 9000 + len(id_map))


def fake_amount(value: str) -> str:
    return "-3.50" if str(value).startswith("-") else "25.00"


def shift_dates(text: str) -> str:
    def move(m: re.Match) -> str:
        return (date(int(m[1]), int(m[2]), int(m[3])) + DATE_SHIFT).isoformat()

    return ISO_DATE.sub(move, text)


def clean(value, key=""):
    if isinstance(value, dict):
        return {k: clean(v, k) for k, v in value.items() if k not in DROP_KEYS}
    if isinstance(value, list):
        return [clean(v, key) for v in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and key not in KEEP_NUMBERS and abs(value) >= BIG_NUMBER:
        return fake_id(value)
    if isinstance(value, str):
        if key in TIMESTAMP_KEYS:
            return FIXED_TIMESTAMP
        if key in AMOUNT_KEYS:
            return fake_amount(value)
        if key in KEEP_STRINGS and ISO_DATE.search(value):
            return shift_dates(value)
        if key not in KEEP_STRINGS and value:
            return label(key or "text")
    return value


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        src = RAW / f"{name}.json"
        if src.exists():
            data = clean(json.loads(src.read_text()))
            (OUT / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
            print("ok", name)


if __name__ == "__main__":
    main()
