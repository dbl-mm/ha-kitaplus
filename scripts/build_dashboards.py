"""Build the KitaPlus dashboard templates (German and English) from one source.

Usage:
    python3 scripts/build_dashboards.py                        # rewrite dashboards/ for all languages
    python3 scripts/build_dashboards.py --language de --children Anna,Ben
        prints a ready-to-paste dashboard for your children (names as they appear in Home Assistant)

Why a generator: Home Assistant builds entity ids from the device name and the entity name in the language that
was active when the integration was set up, so the German and English ids differ
(`sensor.kitaplus_postfach` and `sensor.kitaplus_mailbox`). One source keeps both languages in step, and
tests/test_dashboards.py checks every referenced entity id against the running integration.

Design rules (see docs/dashboards.md): answer "do I have to do something today?" first, show only what needs
attention, never rely on colour alone (every tile also says the state in words), use theme colours only,
and use built-in cards only so nothing but Home Assistant itself is needed.
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
    },
}

TEXT: dict[str, dict[str, str]] = {
    "de": {
        "title": "Kita",
        "view_today": "Heute",
        "view_calendar": "Kalender",
        "view_messages": "Mitteilungen",
        "view_diagnostics": "Diagnose",
        "kita": "Kita",
        "today": "Heute",
        "tomorrow": "Morgen",
        "todo": "Zu erledigen",
        "order_meal_tomorrow": "Essen für morgen bestellen",
        "order_meal_today": "Essen für heute noch bestellen",
        "order_status": "Bestellung morgen",
        "deadline_hint": "Die Bestellfrist legt deine Kita fest. Du findest sie in der KitaPlus-App unter *Verpflegung → Hilfe → Bestellfristen*.",
        "open_replies": "Rückmeldungen offen",
        "all_done": "Nichts zu tun",
        "all_done_text": "✓ Alles bestellt, keine Rückmeldung offen.",
        "meal_today": "Essen heute",
        "meal_tomorrow": "Essen morgen",
        "balance": "Guthaben",
        "balance_history": "Guthaben, letzte 10 Tage",
        "week": "Die nächsten 7 Tage",
        "month": "Monat",
        "board": "Schwarzes Brett",
        "mailbox": "Postfach",
        "no_posts": "Keine Beiträge.",
        "no_messages": "Keine Nachrichten.",
        "due": "bis",
        "connection": "Verbindung",
        "session": "Sitzung gültig bis",
        "session_hint": (
            "Der Sensor **Sitzung gültig bis** ist standardmäßig ausgeschaltet. Einschalten unter "
            "*Einstellungen → Geräte & Dienste → KitaPlus → Entitäten*. Er zeigt, wann du dich neu anmelden musst."
        ),
        "all_values": "Alle Werte",
        "date_format": "dmy",
    },
    "en": {
        "title": "Kita",
        "view_today": "Today",
        "view_calendar": "Calendar",
        "view_messages": "Messages",
        "view_diagnostics": "Diagnostics",
        "kita": "Kita",
        "today": "Today",
        "tomorrow": "Tomorrow",
        "todo": "To do",
        "order_meal_tomorrow": "Order tomorrow's meal",
        "order_meal_today": "Order today's meal while you still can",
        "order_status": "Order for tomorrow",
        "deadline_hint": "Your Kita sets the order deadline. You can find it in the KitaPlus app under *Verpflegung → Hilfe → Bestellfristen*.",
        "open_replies": "Replies needed",
        "all_done": "Nothing to do",
        "all_done_text": "✓ Everything is ordered, no reply is needed.",
        "meal_today": "Meal today",
        "meal_tomorrow": "Meal tomorrow",
        "balance": "Balance",
        "balance_history": "Balance, last 10 days",
        "week": "Next 7 days",
        "month": "Month",
        "board": "Bulletin board",
        "mailbox": "Mailbox",
        "no_posts": "No posts.",
        "no_messages": "No messages.",
        "due": "due",
        "connection": "Connection",
        "session": "Session valid until",
        "session_hint": (
            "The **Session valid until** sensor is off by default. Turn it on under "
            "*Settings → Devices & services → KitaPlus → Entities*. It shows when you have to sign in again."
        ),
        "all_values": "All values",
        "date_format": "iso",
    },
}


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


def date_expr(var: str, style: str) -> str:
    """A date from KitaPlus' `YYYY-MM-DDTHH:MM:SS`, cut from the text so no time zone can shift the day."""
    if style == "dmy":
        return f"{{{{ {var}[8:10] }}}}.{{{{ {var}[5:7] }}}}.{{{{ {var}[0:4] }}}}"
    return f"{{{{ {var}[0:10] }}}}"


def short_date(var: str, style: str) -> str:
    return f"{{{{ {var}[8:10] }}}}.{{{{ {var}[5:7] }}}}." if style == "dmy" else f"{{{{ {var}[5:10] }}}}"


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


def status_cards(t: dict[str, str], ids: Ids) -> list[dict]:
    """Is the Kita open today and tomorrow? Two tiles with the state in words."""
    return [
        tile(
            ids.account("binary_sensor", "closed_today"),
            t["today"],
            "mdi:school-outline",
            color="orange",
            content=["state", "reason"],
        ),
        tile(
            ids.account("binary_sensor", "closed_tomorrow"),
            t["tomorrow"],
            "mdi:school-outline",
            color="orange",
            content=["state", "reason"],
        ),
    ]


def todo_cards(t: dict[str, str], ids_for: list[Ids], account: Ids) -> list[dict]:
    """Only what needs attention; a calm 'nothing to do' card when everything is fine.

    A reminder to order only appears while KitaPlus still accepts the order (status "open"). A missed deadline
    is not shown here, because there is nothing left to do about it.
    """
    cards: list[dict] = []
    calm: list[dict] = []
    for ids in ids_for:
        for key, name_key in (
            ("status_today", "order_meal_today"),
            ("status_tomorrow", "order_meal_tomorrow"),
        ):
            sensor = ids.of_child("sensor", key)
            cards.append(
                {
                    "type": "conditional",
                    "conditions": [{"condition": "state", "entity": sensor, "state": "open"}],
                    "card": {
                        "type": "vertical-stack",
                        "cards": [
                            tile(sensor, t[name_key], "mdi:cart-arrow-down", color="red", content=["state"]),
                            {"type": "markdown", "content": t["deadline_hint"]},
                        ],
                    },
                }
            )
            calm.append({"condition": "state", "entity": sensor, "state_not": "open"})
    pending = account.account("sensor", "pending")
    messages_template = (
        "{% for m in state_attr('" + pending + "', 'messages') or [] %}\n"
        "- **{{ m.titel }}**{% if m.frist %} · "
        + t["due"]
        + " "
        + short_date("m.frist", t["date_format"])
        + "{% endif %}\n"
        "{% endfor %}"
    )
    cards.append(
        {
            "type": "conditional",
            "conditions": [{"condition": "numeric_state", "entity": pending, "above": 0}],
            "card": {
                "type": "vertical-stack",
                "cards": [
                    tile(pending, t["open_replies"], "mdi:email-alert-outline", color="orange"),
                    {"type": "markdown", "content": messages_template},
                ],
            },
        }
    )
    calm.append({"condition": "numeric_state", "entity": pending, "below": 1})
    cards.append(
        {
            "type": "conditional",
            "conditions": calm,
            "card": {"type": "markdown", "title": t["all_done"], "content": t["all_done_text"]},
        }
    )
    return cards


def child_cards(t: dict[str, str], ids: Ids, display: str) -> list[dict]:
    return [
        heading(display, "mdi:account-child-outline"),
        tile(
            ids.of_child("sensor", "meal_today"),
            t["meal_today"],
            "mdi:silverware-fork-knife",
            content=["state"],
        ),
        tile(
            ids.of_child("sensor", "meal_tomorrow"),
            t["meal_tomorrow"],
            "mdi:silverware-fork-knife",
            content=["state"],
        ),
    ]


def balance_cards(t: dict[str, str], account: Ids) -> list[dict]:
    balance = account.account("sensor", "balance")
    return [
        heading(t["balance"], "mdi:wallet-outline"),
        tile(balance, t["balance"], "mdi:cash", content=["state"]),
        {
            "type": "history-graph",
            "title": t["balance_history"],
            "entities": [balance],
            "hours_to_show": 240,  # the recorder keeps 10 days by default
            "show_names": False,
        },
    ]


def list_markdown(entity: str, attribute: str, empty: str, t: dict[str, str]) -> dict:
    """Latest items from a sensor attribute: bold title, date, shortened text."""
    when = date_expr("p.datum", t["date_format"])
    content = (
        "{% set items = state_attr('" + entity + "', '" + attribute + "') or [] %}\n"
        "{% if items | length == 0 %}\n"
        "_" + empty + "_\n"
        "{% else %}\n"
        "{% for p in items %}\n"
        "**{{ p.titel or '–' }}**{% if p.datum %} · " + when + "{% endif %}\n"
        "{% if p.text %}\n"
        "{{ p.text | truncate(220) }}\n"
        "{% endif %}\n"
        "{% if not loop.last %}\n"
        "---\n"
        "{% endif %}\n"
        "{% endfor %}\n"
        "{% endif %}"
    )
    return {"type": "markdown", "content": content}


def board_cards(t: dict[str, str], account: Ids) -> list[dict]:
    board = account.account("sensor", "board")
    return [heading(t["board"], "mdi:bulletin-board"), list_markdown(board, "posts", t["no_posts"], t)]


def mailbox_cards(t: dict[str, str], account: Ids) -> list[dict]:
    messages = account.account("sensor", "messages")
    return [
        heading(t["mailbox"], "mdi:email-outline"),
        list_markdown(messages, "messages", t["no_messages"], t),
    ]


def calendar_cards(t: dict[str, str], account: Ids, ids_for: list[Ids]) -> list[dict]:
    entities = [account.account("calendar", "appointments"), account.account("calendar", "closures")]
    entities += [ids.of_child("calendar", "meals") for ids in ids_for]
    return [
        heading(t["week"], "mdi:calendar-week"),
        {"type": "calendar", "entities": entities, "initial_view": "listWeek"},
        heading(t["month"], "mdi:calendar-month"),
        {"type": "calendar", "entities": entities, "initial_view": "dayGridMonth"},
    ]


def diagnostics_cards(t: dict[str, str], account: Ids, ids_for: list[Ids]) -> list[dict]:
    values = [
        account.account(domain, key)
        for domain, key in (
            ("binary_sensor", "closed_today"),
            ("binary_sensor", "closed_tomorrow"),
            ("sensor", "board"),
            ("sensor", "messages"),
            ("sensor", "pending"),
            ("sensor", "balance"),
        )
    ]
    for ids in ids_for:
        values += [ids.of_child("sensor", "meal_today"), ids.of_child("sensor", "meal_tomorrow")]
        values += [ids.of_child("sensor", "status_today"), ids.of_child("sensor", "status_tomorrow")]
        values.append(ids.of_child("binary_sensor", "no_order"))
    return [
        heading(t["connection"], "mdi:cloud-check-outline"),
        {"type": "markdown", "content": t["session_hint"]},
        tile(
            account.account("sensor", "session"), t["session"], "mdi:clock-check-outline", content=["state"]
        ),
        {"type": "entities", "title": t["all_values"], "entities": values},
    ]


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
        {"type": "grid", "cards": [heading(t["kita"], "mdi:school-outline"), *status_cards(t, account)]},
        {
            "type": "grid",
            "cards": [
                heading(t["todo"], "mdi:checkbox-marked-circle-outline"),
                *todo_cards(t, ids_for, account),
            ],
        },
    ]
    for ids, display in kids:
        today_sections.append({"type": "grid", "cards": child_cards(t, ids, display)})
    today_sections.append({"type": "grid", "cards": balance_cards(t, account)})

    return {
        "title": t["title"],
        "views": [
            {
                "title": t["view_today"],
                "path": "heute",
                "icon": "mdi:home-heart",
                "type": "sections",
                "sections": today_sections,
            },
            {
                "title": t["view_calendar"],
                "path": "kalender",
                "icon": "mdi:calendar",
                "type": "sections",
                "sections": [{"type": "grid", "cards": calendar_cards(t, account, ids_for)}],
            },
            {
                "title": t["view_messages"],
                "path": "mitteilungen",
                "icon": "mdi:message-text-outline",
                "type": "sections",
                "sections": [
                    {"type": "grid", "cards": board_cards(t, account)},
                    {"type": "grid", "cards": mailbox_cards(t, account)},
                ],
            },
            {
                "title": t["view_diagnostics"],
                "path": "diagnose",
                "icon": "mdi:stethoscope",
                "type": "sections",
                "sections": [{"type": "grid", "cards": diagnostics_cards(t, account, ids_for)}],
            },
        ],
    }


def single_cards(language: str) -> dict[str, dict]:
    """Stand-alone cards for people who already have a dashboard (one child, placeholders)."""
    t = TEXT[language]
    account = Ids(language)
    ids = Ids(language)
    return {
        "status": {
            "type": "vertical-stack",
            "cards": [
                heading(t["kita"], "mdi:school-outline"),
                {"type": "grid", "columns": 2, "square": False, "cards": status_cards(t, account)},
            ],
        },
        "zu_erledigen" if language == "de" else "todo": {
            "type": "vertical-stack",
            "cards": todo_cards(t, [ids], account),
        },
        "essen" if language == "de" else "meals": {
            "type": "vertical-stack",
            "cards": child_cards(t, ids, PLACEHOLDER_NAME),
        },
        "guthaben" if language == "de" else "balance": {
            "type": "vertical-stack",
            "cards": balance_cards(t, account),
        },
        "schwarzes_brett" if language == "de" else "bulletin_board": {
            "type": "vertical-stack",
            "cards": board_cards(t, account),
        },
        "postfach" if language == "de" else "mailbox": {
            "type": "vertical-stack",
            "cards": mailbox_cards(t, account),
        },
        "kalender" if language == "de" else "calendar": {
            "type": "vertical-stack",
            "cards": calendar_cards(t, account, [ids]),
        },
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
        "# Einbau: Einstellungen → Dashboards → Dashboard hinzufügen → öffnen → ⋮ → Raw-Konfigurationseditor → alles ersetzen.\n"
        "# Ersetze KIND durch den Vornamen deines Kindes (Anzeige) und kind durch denselben Namen in Kleinbuchstaben\n"
        "# (so heißen die Entities, siehe Einstellungen → Entitäten). Mehrere Kinder: README in diesem Ordner.\n"
        "# Diese Datei wird erzeugt (scripts/build_dashboards.py), bitte nicht in der Vorlage selbst ändern.\n"
    ),
    "en": (
        "# KitaPlus dashboard (template)\n"
        "# Install: Settings → Dashboards → Add dashboard → open it → ⋮ → Raw configuration editor → replace everything.\n"
        "# Replace KIND with your child's first name (display) and kind with the same name in lower case\n"
        "# (that is how the entities are named, see Settings → Entities). Several children: see the README in this folder.\n"
        "# This file is generated (scripts/build_dashboards.py), please do not edit the template itself.\n"
    ),
}


def dump(data: Any, header: str = "") -> str:
    return header + yaml.dump(
        data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=110, default_flow_style=False
    )


def write_all(root: Path) -> list[Path]:
    written: list[Path] = []
    root.mkdir(parents=True, exist_ok=True)
    for language in TEXT:
        target = root / f"kitaplus_{language}.yaml"
        target.write_text(dump(build(language), HEADER[language]))
        written.append(target)
        cards_dir = root / "cards" / language
        cards_dir.mkdir(parents=True, exist_ok=True)
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
