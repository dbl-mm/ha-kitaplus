"""Read the weekly menu plan (a PDF attached to a bulletin board post) into dishes per day. Experimental.

Many Kitas publish what is cooked only as a PDF. The ordering data of KitaPlus names just the meal type
("Mittagessen"), so this optional feature reads the dishes from such a PDF.

It is built to say nothing rather than guess:

* only a clearly recognised layout is used: a date range in the heading, then one block per weekday
  that starts with "Mo.", "Di." and so on, followed by the dish;
* a character the PDF cannot give as text (a ligature such as "fl" without a Unicode mapping) is repaired
  only when a spelling makes a known dish word; otherwise the dish is marked as uncertain;
* anything unrecognised gives an empty plan, never a partial or invented one.

The parser works on text, so it is tested without a PDF. Reading the PDF itself needs `pypdf`.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date, timedelta

_MONTHS = {
    "januar": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4, "mai": 5, "juni": 6,
    "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11, "dezember": 12,
}  # fmt: skip
_WEEKDAYS = {"mo": 0, "di": 1, "mi": 2, "do": 3, "fr": 4, "sa": 5, "so": 6}
_RANGE = re.compile(
    r"(\d{1,2})\.\s*(?:(\d{1,2})\.\s*)?-\s*(\d{1,2})\.\s*(?:([A-Za-zÄÖÜäöü]{3,})|(\d{1,2})\.?)"
)
_DAY = re.compile(r"^(Mo|Di|Mi|Do|Fr|Sa|So)\.?\s*(.*)$")
_ALLERGENS = re.compile(r"^\s*enth[aä]l?t\b", re.IGNORECASE)
_VEGETARIAN = re.compile(r"\(\s*veg(?:etarisch)?\.?\s*\)", re.IGNORECASE)
_LIGATURE_GAP = "\x00"
# A ligature the PDF cannot name is one of these. It is accepted only if the result contains a known stem.
_LIGATURES = ("fl", "fi", "ff", "ffl", "ffi")
_STEMS = (
    "flügel", "fleisch", "flammkuchen", "flocken", "fladen", "fisch", "filet", "finger", "fischstäbchen",
    "pfifferling", "waffel", "muffin", "kaiserschmarrn", "auflauf", "pfifferlinge", "schnitzel", "kartoffel",
)  # fmt: skip
MAX_DISH = 120
MAX_DAYS = 14


@dataclass(frozen=True)
class MenuDay:
    """The dish of one day as written in the plan."""

    day: date
    dish: str
    vegetarian: bool = False
    uncertain: bool = False  # a character could not be read with certainty


def extract_text(pdf: bytes) -> str:
    """The text of the first page. Raises ValueError when the file is not a readable PDF."""
    try:
        from pypdf import PdfReader  # noqa: PLC0415 - only needed when the option is on

        reader = PdfReader(io.BytesIO(pdf))
        return "\n".join(page.extract_text() or "" for page in reader.pages[:2])
    except Exception as err:  # noqa: BLE001 - pypdf raises many kinds of errors for broken files
        raise ValueError("not a readable PDF") from err


def _repair(text: str) -> tuple[str, bool]:
    """Fill gaps left by unnamed ligatures. Returns (text, uncertain)."""
    if _LIGATURE_GAP not in text:
        return text, False
    uncertain = False
    words = []
    for word in text.split(" "):
        if _LIGATURE_GAP in word:
            fixed = next(
                (
                    candidate
                    for lig in _LIGATURES  # the likeliest spelling first: "fl" before "ffl"
                    if any(
                        stem in (candidate := word.replace(_LIGATURE_GAP, lig, 1)).lower() for stem in _STEMS
                    )
                ),
                None,
            )
            if fixed is not None and _LIGATURE_GAP not in fixed:
                word = fixed
            else:
                word, uncertain = word.replace(_LIGATURE_GAP, "?"), True
        words.append(word)
    return " ".join(words), uncertain


def _clean(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split())[:MAX_DISH]


def _start_of_week(text: str, year: int) -> date | None:
    """The first day of the plan from a heading such as "02.-06. November" or "30.10.-03.11."."""
    found = _RANGE.search(text)
    if found is None:
        return None
    first_day, first_month, last_day, month_name, last_month = found.groups()
    month = (
        int(first_month)
        if first_month
        else _MONTHS.get(month_name.lower(), 0)
        if month_name
        else int(last_month)
    )
    if not month:
        return None
    if not first_month and int(first_day) > int(
        last_day
    ):  # "30.-03. November": the plan starts a month earlier
        month, year = (month - 1, year) if month > 1 else (12, year - 1)
    try:
        return date(year, month, int(first_day))
    except ValueError:
        return None


def parse_menu(text: str, year: int) -> list[MenuDay]:
    """Dishes per day, or an empty list when the text does not look like a weekly menu plan."""
    lines = [line.strip() for line in text.replace("\r", "\n").split("\n")]
    start = _start_of_week(text, year)
    if start is None:
        return []
    blocks: list[tuple[int, list[str]]] = []
    for line in lines:
        if not line:
            continue
        if _ALLERGENS.match(line):
            break  # what follows are the allergen lines and the footer of the supplier
        day = _DAY.match(line)
        if day and (len(line) <= 4 or line[2:3] in ". "):
            blocks.append((_WEEKDAYS[day.group(1).lower()], [day.group(2)] if day.group(2) else []))
        elif blocks:
            blocks[-1][1].append(line)
    days: list[MenuDay] = []
    seen: set[int] = set()
    for weekday, parts in blocks:
        dish_text, uncertain = _repair(" ".join(parts))
        vegetarian = bool(_VEGETARIAN.search(dish_text))
        dish = _clean(_VEGETARIAN.sub("", dish_text))
        offset = (weekday - start.weekday()) % 7
        if not dish or weekday in seen or offset >= MAX_DAYS:
            continue
        seen.add(weekday)
        days.append(MenuDay(start + timedelta(days=offset), dish, vegetarian, uncertain or "?" in dish))
    return sorted(days, key=lambda item: item.day) if len(days) >= 3 else []
