"""Build the KitaPlus dashboard templates (German and English) from one source.

Usage:
    python3 scripts/build_dashboards.py                        # rewrite dashboards/ for all languages
    python3 scripts/build_dashboards.py --language de --children Anna,Ben
        prints a ready-to-paste dashboard for your children (names as they appear in Home Assistant)

Why a generator: Home Assistant builds entity ids from the device name and the entity name in the language that
was active when the integration was set up, so the German and English ids differ
(`sensor.kitaplus_postfach` and `sensor.kitaplus_mailbox`). One source keeps both languages in step, and
tests/test_dashboards.py checks every referenced entity id against the running integration.

Design rules (see docs/dashboards.md): show as little as possible and make it obvious. Anything that needs action
appears only when there is something to do, status is always written in words (never colour alone), every fact
is shown once, theme colours only, built-in cards only.
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path
from typing import Any

import yaml

PLACEHOLDER_ID = "kind"  # lower case: part of entity ids, replace with the child's first name in lower case
PLACEHOLDER_NAME = "KIND"  # shown text, replace with the child's first name

# Entity id slugs per language. Account entities are `<domain>.kitaplus_<slug>`, child entities
# `<domain>.<child>_<slug>`. tests/test_dashboards.py proves these against the real integration.
SLUGS: dict[str, dict[str, str]] = {
    "de": {
        "board": "schwarzes_brett",
        "messages": "postfach",
        "pending": "offene_ruckmeldungen",
        "balance": "kontostand_verpflegung",
        "meal_today": "essen_heute",
        "meal_tomorrow": "essen_morgen",
        "session": "sitzung_gultig_bis",
        "appointments": "termine",
        "closures": "schliesstage",
        "meals": "bestelltes_essen",
        "closed_today": "heute_geschlossen",
        "closed_tomorrow": "morgen_geschlossen",
        "no_order": "morgen_nicht_bestellt",
        "status_today": "bestellstatus_heute",
        "status_tomorrow": "bestellstatus_morgen",
        "next_deadline": "nachste_bestellfrist",
    },
    "en": {
        "board": "bulletin_board",
        "messages": "mailbox",
        "pending": "pending_replies",
        "balance": "meal_account_balance",
        "meal_today": "meal_today",
        "meal_tomorrow": "meal_tomorrow",
        "session": "session_valid_until",
        "appointments": "appointments",
        "closures": "closures",
        "meals": "ordered_meals",
        "closed_today": "closed_today",
        "closed_tomorrow": "closed_tomorrow",
        "no_order": "nothing_ordered_tomorrow",
        "status_today": "order_status_today",
        "status_tomorrow": "order_status_tomorrow",
        "next_deadline": "next_order_deadline",
    },
}

TEXT: dict[str, dict[str, str]] = {
    "de": {
        "title": "Kita",
        "view_today": "Heute",
        "view_messages": "Mitteilungen",
        "view_calendar": "Kalender",
        "kita": "Kita",
        "kita_today": "Kita heute",
        "kita_tomorrow": "Kita morgen",
        "today": "Heute",
        "tomorrow": "Morgen",
        "order_today": "Essen für heute noch bestellen",
        "order_tomorrow": "Essen für morgen bestellen",
        "deadline": "Bestellfrist",
        "open_replies": "Rückmeldungen offen",
        "account": "Konto",
        "balance": "Guthaben",
        "board": "Schwarzes Brett",
        "mailbox": "Postfach",
        "no_posts": "Keine Beiträge.",
        "no_messages": "Keine Nachrichten.",
        "due": "bis",
        "date_format": "dmy",
    },
    "en": {
        "title": "Kita",
        "view_today": "Today",
        "view_messages": "Messages",
        "view_calendar": "Calendar",
        "kita": "Kita",
        "kita_today": "Kita today",
        "kita_tomorrow": "Kita tomorrow",
        "today": "Today",
        "tomorrow": "Tomorrow",
        "order_today": "Order today's meal while you can",
        "order_tomorrow": "Order tomorrow's meal",
        "deadline": "Order deadline",
        "open_replies": "Replies needed",
        "account": "Account",
        "balance": "Balance",
        "board": "Bulletin board",
        "mailbox": "Mailbox",
        "no_posts": "No posts.",
        "no_messages": "No messages.",
        "due": "due",
        "date_format": "iso",
    },
}

BOARD_ITEMS = 4  # the sensor keeps the last 5; four are plenty on a dashboard
MAILBOX_ITEMS = 3
EXCERPT = 110  # characters of text per item


class Ids:
    """Entity ids for one language and one child (or the placeholder)."""

    def __init__(self, language: str, child: str = PLACEHOLDER_ID) -> None:
        self.slug = SLUGS[language]
        self.child = child

    def account(self, domain: str, key: str) -> str:
        return f"{domain}.kitaplus_{self.slug[key]}"

    def of_child(self, domain: str, key: str) -> str:
        return f"{domain}.{self.child}_{self.slug[key]}"


def slugify(name: str) -> str:
    """Like Home Assistant's slugify: sharp s becomes "ss", other accents are dropped (ü becomes u)."""
    ascii_name = unicodedata.normalize("NFKD", name.replace("ß", "ss")).encode("ascii", "ignore").decode()
    return "_".join("".join(c if c.isalnum() else " " for c in ascii_name.lower()).split())


def short_date(var: str, style: str) -> str:
    """A date from KitaPlus' `YYYY-MM-DDTHH:MM:SS`, cut from the text so no time zone can shift the day."""
    if style == "dmy":
        return f"{{{{ {var}[8:10] }}}}.{{{{ {var}[5:7] }}}}."
    return f"{{{{ {var}[5:10] }}}}"


def full_date(var: str, style: str) -> str:
    if style == "dmy":
        return f"{{{{ {var}[8:10] }}}}.{{{{ {var}[5:7] }}}}.{{{{ {var}[0:4] }}}}"
    return f"{{{{ {var}[0:10] }}}}"


# ----------------------------------------------------------------------------------------------- cards


def tile(
    entity: str, name: str, icon: str, *, color: str | None = None, content: list[str] | None = None
) -> dict:
    card: dict[str, Any] = {"type": "tile", "entity": entity, "name": name, "icon": icon}
    if color:
        card["color"] = color
    if content:
        card["state_content"] = content
    return card


def heading(text: str, icon: str) -> dict:
    return {"type": "heading", "heading": text, "heading_style": "title", "icon": icon}


def kita_cards(t: dict[str, str], account: Ids) -> list[dict]:
    """Is the Kita open today and tomorrow? The state is written out; the reason (e.g. a bridge day) follows."""
    closed_today = account.account("binary_sensor", "closed_today")
    closed_tomorrow = account.account("binary_sensor", "closed_tomorrow")
    return [
        tile(
            closed_today, t["kita_today"], "mdi:school-outline", color="orange", content=["state", "reason"]
        ),
        tile(
            closed_tomorrow,
            t["kita_tomorrow"],
            "mdi:school-outline",
            color="orange",
            content=["state", "reason"],
        ),
    ]


def child_cards(t: dict[str, str], ids: Ids, display: str) -> list[dict]:
    """Two tiles per child: "Ordered · Lunch" for today and tomorrow. The icon follows the state."""
    return [
        heading(display, "mdi:account-child-outline"),
        tile(
            ids.of_child("sensor", "status_today"), t["today"], "mdi:cart-outline", content=["state", "meal"]
        ),
        tile(
            ids.of_child("sensor", "status_tomorrow"),
            t["tomorrow"],
            "mdi:cart-outline",
            content=["state", "meal"],
        ),
    ]


def balance_cards(t: dict[str, str], account: Ids) -> list[dict]:
    return [
        heading(t["account"], "mdi:wallet-outline"),
        tile(account.account("sensor", "balance"), t["balance"], "mdi:cash", content=["state"]),
    ]


def replies_cards(t: dict[str, str], account: Ids) -> list[dict]:
    """Only while a message needs an answer: a tile and the titles with their deadline."""
    pending = account.account("sensor", "pending")
    titles = (
        "{% for m in state_attr('" + pending + "', 'messages') or [] %}\n"
        "- **{{ (m.titel or '–') | regex_replace('[*_`#>]', '') | trim }}**"
        "{% if m.frist %} · " + t["due"] + " " + short_date("m.frist", t["date_format"]) + "{% endif %}\n"
        "{% endfor %}"
    )
    return [
        {
            "type": "conditional",
            "conditions": [{"condition": "numeric_state", "entity": pending, "above": 0}],
            "card": {
                "type": "vertical-stack",
                "cards": [
                    tile(pending, t["open_replies"], "mdi:email-alert-outline", color="orange"),
                    {"type": "markdown", "content": titles},
                ],
            },
        }
    ]


def todo_cards(t: dict[str, str], ids_for: list[tuple[Ids, str]], account: Ids) -> list[dict]:
    """Only what needs attention. When there is nothing to do, nothing is shown at all (and the section hides).

    A reminder to order only appears while ordering is still possible (status "open"). A missed deadline is not
    shown here, because there is nothing left to do about it.
    """
    cards: list[dict] = []
    for ids, display in ids_for:
        for key, name_key in (("status_today", "order_today"), ("status_tomorrow", "order_tomorrow")):
            sensor = ids.of_child("sensor", key)
            name = t[name_key] if len(ids_for) == 1 else f"{display}: {t[name_key]}"
            deadline = ids.of_child("sensor", "next_deadline")
            cards.append(
                {
                    "type": "conditional",
                    "conditions": [{"condition": "state", "entity": sensor, "state": "open"}],
                    "card": {
                        "type": "vertical-stack",
                        "cards": [
                            tile(sensor, name, "mdi:cart-arrow-down", color="red", content=["meal"]),
                            tile(deadline, t["deadline"], "mdi:timer-sand", content=["state"]),
                        ],
                    },
                }
            )
    return [*cards, *replies_cards(t, account)]


def list_markdown(entity: str, attribute: str, empty: str, limit: int, t: dict[str, str]) -> dict:
    """Latest items from a sensor attribute: bold title, date, a short excerpt. Markdown signs that Kitas put
    into their titles (for example `**Gartenfest**`) are removed, so they never show up as stray asterisks."""
    when = full_date("p.datum", t["date_format"])
    content = (
        "{% set items = state_attr('" + entity + "', '" + attribute + "') or [] %}\n"
        "{% if items | length == 0 %}\n"
        "_" + empty + "_\n"
        "{% else %}\n"
        "{% for p in items[:" + str(limit) + "] %}\n"
        "**{{ (p.titel or '–') | regex_replace('[*_`#>]', '') | trim }}**{% if p.datum %} · "
        + when
        + "{% endif %}\n"
        "\n"
        "{% set text = (p.text or '') | regex_replace('[*_`#>]', '') | regex_replace('[\\n\\r\\t ]+', ' ') | trim %}\n"
        "{% if text %}\n"
        "{{ text | truncate(" + str(EXCERPT) + ") }}\n"
        "\n"
        "{% endif %}\n"
        "{% endfor %}\n"
        "{% endif %}"
    )
    return {"type": "markdown", "content": content}


def board_cards(t: dict[str, str], account: Ids) -> list[dict]:
    board = account.account("sensor", "board")
    return [
        heading(t["board"], "mdi:bulletin-board"),
        list_markdown(board, "posts", t["no_posts"], BOARD_ITEMS, t),
    ]


def mailbox_cards(t: dict[str, str], account: Ids) -> list[dict]:
    messages = account.account("sensor", "messages")
    return [
        heading(t["mailbox"], "mdi:email-outline"),
        list_markdown(messages, "messages", t["no_messages"], MAILBOX_ITEMS, t),
    ]


def calendar_cards(account: Ids, ids_for: list[Ids]) -> list[dict]:
    """One calendar card: it brings its own switch between list, week and month."""
    entities = [account.account("calendar", "appointments"), account.account("calendar", "closures")]
    entities += [ids.of_child("calendar", "meals") for ids in ids_for]
    return [{"type": "calendar", "entities": entities, "initial_view": "listWeek"}]


# --------------------------------------------------------------------------------------------- dashboard


def build(language: str, children: list[str] | None = None) -> dict:
    """The complete dashboard. `children` are names as shown in Home Assistant; None keeps the placeholder."""
    t = TEXT[language]
    account = Ids(language)
    if children:
        kids = [(Ids(language, slugify(name)), name) for name in children]
    else:
        kids = [(Ids(language), PLACEHOLDER_NAME)]
    ids_for = [ids for ids, _ in kids]

    today_sections: list[dict] = [
        # no heading: while nothing needs action every card is hidden and the whole section disappears
        {"type": "grid", "cards": todo_cards(t, kids, account)},
        {"type": "grid", "cards": [heading(t["kita"], "mdi:school-outline"), *kita_cards(t, account)]},
    ]
    today_sections += [{"type": "grid", "cards": child_cards(t, ids, display)} for ids, display in kids]
    today_sections.append({"type": "grid", "cards": balance_cards(t, account)})

    messages_sections = [
        {"type": "grid", "cards": board_cards(t, account)},
        {"type": "grid", "cards": mailbox_cards(t, account)},
    ]
    calendar_sections = [{"type": "grid", "cards": calendar_cards(account, ids_for)}]
    return {
        "title": t["title"],
        "views": [
            _view(t["view_today"], "heute", "mdi:home-heart", today_sections),
            _view(t["view_messages"], "mitteilungen", "mdi:message-text-outline", messages_sections),
            _view(t["view_calendar"], "kalender", "mdi:calendar", calendar_sections),
        ],
    }


def _view(title: str, path: str, icon: str, sections: list[dict]) -> dict:
    return {"title": title, "path": path, "icon": icon, "type": "sections", "sections": sections}


def single_cards(language: str) -> dict[str, dict]:
    """Stand-alone cards for people who already have a dashboard (one child, placeholders)."""
    t = TEXT[language]
    account = Ids(language)
    ids = Ids(language)
    kids = [(ids, PLACEHOLDER_NAME)]
    de = language == "de"
    kita = {
        "type": "vertical-stack",
        "cards": [
            heading(t["kita"], "mdi:school-outline"),
            {"type": "grid", "columns": 2, "square": False, "cards": kita_cards(t, account)},
        ],
    }

    def stack(cards: list[dict]) -> dict:
        return {"type": "vertical-stack", "cards": cards}

    return {
        "kita": kita,
        "zu_erledigen" if de else "todo": stack(todo_cards(t, kids, account)),
        "essen" if de else "meals": stack(child_cards(t, ids, PLACEHOLDER_NAME)),
        "guthaben" if de else "balance": stack(balance_cards(t, account)),
        "schwarzes_brett" if de else "bulletin_board": stack(board_cards(t, account)),
        "postfach" if de else "mailbox": stack(mailbox_cards(t, account)),
        "kalender" if de else "calendar": calendar_cards(account, [ids])[0],
    }


# ------------------------------------------------------------------------------------------------ output


class _Dumper(yaml.SafeDumper):
    """Multi-line strings (the markdown templates) are written as readable blocks."""


def _str(dumper: yaml.SafeDumper, value: str) -> yaml.ScalarNode:
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _str)

HEADER = {
    "de": (
        "# KitaPlus-Dashboard (Vorlage)\n"
        "# Einbau: Einstellungen → Dashboards → Dashboard hinzufügen → öffnen → ⋮ → Raw-Konfigurationseditor.\n"
        "# Ersetze KIND durch den Vornamen deines Kindes (Anzeige) und kind durch denselben Namen in Kleinbuchstaben\n"
        "# (so heißen die Entities, siehe Einstellungen → Entitäten). Mehrere Kinder: README in diesem Ordner.\n"
        "# Diese Datei wird erzeugt (scripts/build_dashboards.py), bitte nicht in der Vorlage selbst ändern.\n"
    ),
    "en": (
        "# KitaPlus dashboard (template)\n"
        "# Install: Settings → Dashboards → Add dashboard → open it → ⋮ → Raw configuration editor.\n"
        "# Replace KIND with your child's first name (display) and kind with the same name in lower case\n"
        "# (that is how the entities are named, see Settings → Entities). Several children: see the README here.\n"
        "# This file is generated (scripts/build_dashboards.py), please do not edit the template itself.\n"
    ),
}


def dump(data: Any, header: str = "") -> str:
    body = yaml.dump(
        data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=110, default_flow_style=False
    )
    return header + body


def write_all(root: Path) -> list[Path]:
    written: list[Path] = []
    root.mkdir(parents=True, exist_ok=True)
    for language in TEXT:
        target = root / f"kitaplus_{language}.yaml"
        target.write_text(dump(build(language), HEADER[language]))
        written.append(target)
        cards_dir = root / "cards" / language
        cards_dir.mkdir(parents=True, exist_ok=True)
        for stale in cards_dir.glob("*.yaml"):
            stale.unlink()  # a card that no longer exists must not linger
        for name, card in single_cards(language).items():
            path = cards_dir / f"{name}.yaml"
            path.write_text(dump(card, HEADER[language].split("\n")[0] + "\n"))
            written.append(path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--language", choices=sorted(TEXT))
    parser.add_argument("--children", help="comma separated first names, e.g. Anna,Ben")
    args = parser.parse_args()
    if args.children:
        if not args.language:
            parser.error("--children needs --language")
        names = [n.strip() for n in args.children.split(",") if n.strip()]
        sys.stdout.write(dump(build(args.language, names), HEADER[args.language].split("\n")[0] + "\n"))
        return 0
    for path in write_all(Path("dashboards")):
        print("wrote", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
