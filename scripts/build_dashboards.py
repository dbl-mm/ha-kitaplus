"""Build the KitaPlus dashboard templates (German and English) from one source.

Usage:
    python3 scripts/build_dashboards.py                        # rewrite dashboards/ for all languages
    python3 scripts/build_dashboards.py --language de --children Anna,Ben
        prints a ready-to-paste dashboard for your children (names as they appear in Home Assistant)

Why a generator: Home Assistant builds entity ids from the device name and the entity name in the language that
was active when the integration was set up, so the German and English ids differ
(`sensor.kitaplus_postfach` and `sensor.kitaplus_mailbox`). One source keeps both languages and both layouts
(phone and wall tablet) in step, and tests/test_dashboards.py checks every referenced entity id against the
running integration and renders every template with test states.

Design (see docs/dashboards.md): one glance, one statement. A status card says the single most important thing,
the rest follows in a fixed order. Colours and fonts come from the user's theme. The state is always written
in words next to an icon. Built-in cards only.
"""

from __future__ import annotations

import argparse
import json
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
        "upcoming": "nachste_termine",
        "menu_today": "speiseplan_heute",
        "menu_tomorrow": "speiseplan_morgen",
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
        "upcoming": "upcoming_dates",
        "menu_today": "menu_today",
        "menu_tomorrow": "menu_tomorrow",
    },
}

# Everything a person reads. Jinja fragments (marked expr) may use the variables named in the templates below.
TEXT: dict[str, dict[str, Any]] = {
    "de": {
        "title": "Kita",
        "view_today": "Heute",
        "view_wall": "Wand",
        "view_calendar": "Kalender",
        "app": "KitaPlus",
        "kita_today": "Kita heute",
        "kita_tomorrow": "Kita morgen",
        "weekdays": ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
        "weekdays_short": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"],
        "months": [
            "Januar",
            "Februar",
            "März",
            "April",
            "Mai",
            "Juni",
            "Juli",
            "August",
            "September",
            "Oktober",
            "November",
            "Dezember",
        ],
        "today": "heute",
        "tomorrow": "morgen",
        "state_words": {
            "ordered": "Bestellt",
            "open": "Offen",
            "missed": "Frist verpasst",
            "not_offered": "Kein Essen",
            "unavailable": "Nicht verfügbar",
            "unknown": "Unbekannt",
        },
        "missed_title": "Nicht bestellt",
        "missed_one": "'Essen für ' ~ ns.missed[0] ~ ' ist nicht bestellt.'",
        "missed_many": "'Nicht bestellt: ' ~ ns.missed | join(', ') ~ '.'",
        "ask_kita": "Die Frist ist vorbei.",
        "open_one": "Eine Sache ist offen",
        "open_many": "' Sachen sind offen'",
        "order_item": "'Essen für ' ~ first.n ~ ' ' ~ first.label ~ ' bestellen.'",
        "reply_item": "'Rückmeldung: ' ~ title",
        "more": "' Dazu ' ~ (total - 1) ~ ' weitere.'",
        "deadline_pill": "'Frist ' ~ dayl ~ ', ' ~ dl.strftime('%H:%M')",
        "left": "' · noch ' ~ left",
        "hours": "Std.",
        "minutes": "Min.",
        "reply_pill": "'Antwort bis ' ~ dlabel(msgs[0].frist)",
        "closed_title": "Kita heute geschlossen",
        "tomorrow_open": "Morgen ist wieder geöffnet.",
        "tomorrow_closed": "Morgen ist ebenfalls geschlossen.",
        "calm_title": "Heute ist nichts zu tun",
        "calm_ordered": "Essen für heute und morgen ist bestellt. Keine Rückmeldung offen.",
        "calm_nothing": "Es gibt nichts zu bestellen. Keine Rückmeldung offen.",
        "todo_title": "Noch nicht eingerichtet",
        "todo_sub": (
            "Das ist erst die Vorlage, deshalb siehst du hier noch keine echten Daten. So richtest du sie ein:"
            "<br>1. Dashboard bearbeiten (Stift), dann ⋮ → Raw-Konfigurationseditor."
            "<br>2. Mit Suchen und Ersetzen <b>{{ 'KI' ~ 'ND' }}</b> durch den Vornamen deines Kindes ersetzen, "
            "zum Beispiel Finn."
            "<br>3. <b>{{ 'ki' ~ 'nd' }}</b> durch denselben Namen in Kleinbuchstaben ersetzen, zum Beispiel finn."
            "<br>4. Speichern. Fertig."
        ),
        "vegetarian": "vegetarisch",
        "check_plan": "bitte im Menüplan prüfen",
        "from_plan": "Gericht laut Menüplan-PDF, ohne Gewähr.",
        "todo_kid": "Noch keine Daten. Richte zuerst die Vorlage ein, die Anleitung steht oben.",
        "nodata_title": "Keine aktuellen Daten",
        "nodata_sub": "KitaPlus ist gerade nicht erreichbar, oder die Entitäten des Kindes fehlen (Namen prüfen unter Einstellungen → Entitäten).",
        "meal_for": "Essen für",
        "row_today": "Heute",
        "row_tomorrow": "Morgen",
        "next_deadline": "Nächste Bestellfrist",
        "board": "Schwarzes Brett",
        "no_post": "Kein Beitrag am Schwarzen Brett.",
        "attached": "Anhang",
        "untitled": "Ohne Titel",
        "mailbox": "Postfach",
        "messages": "Nachrichten",
        "message_one": "Nachricht",
        "no_reply_open": "keine Rückmeldung offen",
        "reply_until": "Rückmeldung bis",
        "next": "Als Nächstes",
        "no_dates": "Keine anstehenden Termine.",
        "closure": "Schließtag",
        "clock": "Uhr",
        "balance": "Guthaben Verpflegung",
        "date_expr": "wd[now().weekday()] ~ ', ' ~ now().day ~ '. ' ~ mo[now().month - 1]",
        "date_numeric": "'%02d' | format(d.day) ~ '.' ~ '%02d' | format(d.month) ~ '.'",
    },
    "en": {
        "title": "Kita",
        "view_today": "Today",
        "view_wall": "Wall",
        "view_calendar": "Calendar",
        "app": "KitaPlus",
        "kita_today": "Kita today",
        "kita_tomorrow": "Kita tomorrow",
        "weekdays": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "weekdays_short": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "months": [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ],
        "today": "today",
        "tomorrow": "tomorrow",
        "state_words": {
            "ordered": "Ordered",
            "open": "Open",
            "missed": "Deadline missed",
            "not_offered": "No meal",
            "unavailable": "Unavailable",
            "unknown": "Unknown",
        },
        "missed_title": "Not ordered",
        "missed_one": "'The meal for ' ~ ns.missed[0] ~ ' is not ordered.'",
        "missed_many": "'Not ordered: ' ~ ns.missed | join(', ') ~ '.'",
        "ask_kita": "The deadline has passed.",
        "open_one": "One thing is open",
        "open_many": "' things are open'",
        "order_item": "'Order the meal for ' ~ first.n ~ ' ' ~ first.label ~ '.'",
        "reply_item": "'Reply needed: ' ~ title",
        "more": "' Plus ' ~ (total - 1) ~ ' more.'",
        "deadline_pill": "'Deadline ' ~ dayl ~ ', ' ~ dl.strftime('%H:%M')",
        "left": "' · ' ~ left ~ ' left'",
        "hours": "h",
        "minutes": "min",
        "reply_pill": "'Reply by ' ~ dlabel(msgs[0].frist)",
        "closed_title": "Kita closed today",
        "tomorrow_open": "Tomorrow it is open again.",
        "tomorrow_closed": "Tomorrow it is closed as well.",
        "calm_title": "Nothing to do today",
        "calm_ordered": "Meals for today and tomorrow are ordered. No reply needed.",
        "calm_nothing": "There is nothing to order. No reply needed.",
        "todo_title": "Not set up yet",
        "todo_sub": (
            "This is only the template, so there is no real data here yet. To set it up:"
            "<br>1. Edit the dashboard (pencil), then ⋮ → Raw configuration editor."
            "<br>2. With find and replace, change <b>{{ 'KI' ~ 'ND' }}</b> to your child's first name, "
            "for example Finn."
            "<br>3. Change <b>{{ 'ki' ~ 'nd' }}</b> to the same name in lower case, for example finn."
            "<br>4. Save. Done."
        ),
        "vegetarian": "vegetarian",
        "check_plan": "please check the menu plan",
        "from_plan": "Dish from the menu plan PDF, without guarantee.",
        "todo_kid": "No data yet. Set up the template first, the instructions are at the top.",
        "nodata_title": "No current data",
        "nodata_sub": "KitaPlus cannot be reached right now, or the child's entities are missing (check the names under Settings → Entities).",
        "meal_for": "Meals for",
        "row_today": "Today",
        "row_tomorrow": "Tomorrow",
        "next_deadline": "Next order deadline",
        "board": "Bulletin board",
        "no_post": "No post on the bulletin board.",
        "attached": "Attachment",
        "untitled": "Untitled",
        "mailbox": "Mailbox",
        "messages": "messages",
        "message_one": "message",
        "no_reply_open": "no reply needed",
        "reply_until": "Reply by",
        "next": "Coming up",
        "no_dates": "No upcoming dates.",
        "closure": "Closure day",
        "clock": "",
        "balance": "Meal account balance",
        "date_expr": "wd[now().weekday()] ~ ', ' ~ now().day ~ ' ' ~ mo[now().month - 1]",
        "date_numeric": "d.day ~ ' ' ~ mon[d.month - 1]",
    },
}

# Plain signs: an inline <ha-icon> grows to the size of the heading in Home Assistant, a sign stays text-sized.
ICON = {"ordered": "✓", "open": "○", "missed": "✕", "not_offered": "–"}
BOARD_EXCERPT = 100  # characters: about two lines on a phone
TITLE_LENGTH = 80  # about two lines
WORD_LENGTH = 24  # longer words (web addresses) are cut so they cannot break the layout


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


def q(text: str) -> str:
    """A Jinja string literal (single quotes) for fixed text or a name."""
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def jlist(items: list[str]) -> str:
    return "[" + ", ".join(q(i) for i in items) + "]"


def fill(template: str, **values: str) -> str:
    """Replace @@NAME@@ markers. A marker may stand for text or for a Jinja expression."""
    for key, value in values.items():
        template = template.replace(f"@@{key}@@", value)
    assert "@@" not in template, "unfilled marker"
    return template.strip() + "\n"


# --------------------------------------------------------------------------------------------- templates

# Shared Jinja helpers. `clean` removes markup signs a Kita may type into titles and texts, collapses line breaks and
# cuts very long words (web addresses). Home Assistant has no bound on text lengths, so everything is shortened.
HELPERS = """
{%- set wd = @@WD@@ -%}
{%- set mon = @@MON@@ -%}
{%- macro clean(t) -%}
{%- set s = (t or '') | regex_replace('[<>&"`*_#\\\\[\\\\]]', '') | regex_replace('[\\n\\r\\t ]+', ' ') | trim -%}
{%- for w in s.split(' ') -%}{{ w | truncate(@@WORD@@, True, '…') }}{{ ' ' if not loop.last }}{%- endfor -%}
{%- endmacro -%}
{%- macro dlabel(iso) -%}
{%- set d = as_datetime(iso) -%}
{%- if d -%}{{ wd[d.weekday()] }} {{ @@DATE_NUMERIC@@ }}{%- endif -%}
{%- endmacro -%}
"""


def helpers(t: dict[str, Any]) -> str:
    return (
        fill(
            HELPERS,
            WD=jlist(t["weekdays_short"]),
            MON=jlist(t["months"][i][:3] for i in range(12))
            if False
            else jlist([m[:3] for m in t["months"]]),
            WORD=str(WORD_LENGTH),
            DATE_NUMERIC=t["date_numeric"],
        ).rstrip("\n")
        + "\n"
    )


HEADER = """
{%- set wd = @@WEEKDAYS@@ -%}
{%- set mo = @@MONTHS@@ -%}
<small>{{ @@DATE@@ }}</small>

# @@APP@@
"""

HEADER_WALL = """
{%- set wd = @@WEEKDAYS@@ -%}
{%- set mo = @@MONTHS@@ -%}
## {{ wd[now().weekday()] }}

# {{ now().day }}. {{ mo[now().month - 1] }}
"""

HERO = """
{%- set kids = @@KIDS@@ -%}
{%- set ns = namespace(missed=[], opens=[], ordered=0, nodata=0) -%}
{%- for k in kids -%}
{%- for key, label in [('t', @@TODAY@@), ('m', @@TOMORROW@@)] -%}
{%- set st = states(k[key]) -%}
{%- if st == 'missed' -%}{%- set ns.missed = ns.missed + [k.n ~ ' ' ~ label] -%}{%- endif -%}
{%- if st == 'open' -%}{%- set ns.opens = ns.opens + [{'n': k.n, 'label': label, 'dl': k.d}] -%}{%- endif -%}
{%- if st == 'ordered' -%}{%- set ns.ordered = ns.ordered + 1 -%}{%- endif -%}
{%- if st in ['unavailable', 'unknown'] -%}{%- set ns.nodata = ns.nodata + 1 -%}{%- endif -%}
{%- endfor -%}
{%- endfor -%}
{%- set pending = '@@PENDING@@' -%}
{%- set pend = states(pending) | int(0) -%}
{%- set msgs = state_attr(pending, 'messages') or [] -%}
{%- set title = clean(msgs[0].titel if msgs else '') | trim -%}
{%- set total = ns.opens | count + pend -%}
{%- if kids | selectattr('n', 'eq', 'KI' ~ 'ND') | list | count > 0 -%}
<ha-alert alert-type="info" title="@@TODO_TITLE@@">@@TODO_SUB@@</ha-alert>
{%- elif ns.missed | count > 0 -%}
<ha-alert alert-type="warning" title="@@MISSED_TITLE@@">{{ (@@MISSED_ONE@@ if ns.missed | count == 1 else @@MISSED_MANY@@) | truncate(@@TITLE@@, True, '…') }} @@ASK_KITA@@</ha-alert>
{%- elif total > 0 -%}
{%- set first = ns.opens[0] if ns.opens else none -%}
{%- set dlstate = states(first.dl) if first else 'unknown' -%}
{%- set dl = (as_datetime(dlstate) | as_local) if dlstate not in ['unknown', 'unavailable', 'none', ''] else none -%}
{%- set text = (@@ORDER_ITEM_O@@ if first else @@REPLY_ITEM@@) -%}
{%- set pill = '' -%}
{%- if dl and dl > now() -%}
{%- set mins = ((dl - now()).total_seconds() // 60) | int -%}
{%- set left = ((mins // 60) ~ ' @@HOURS@@' ~ (' ' ~ (mins % 60) ~ ' @@MINUTES@@' if mins % 60 else '')) if mins >= 60 else (mins ~ ' @@MINUTES@@') -%}
{%- set dayl = @@TODAY@@ if dl.date() == now().date() else (@@TOMORROW@@ if (dl.date() - now().date()).days == 1 else wd[dl.weekday()]) -%}
{%- set pill = @@DEADLINE_PILL@@ ~ @@LEFT@@ -%}
{%- elif not first and msgs and msgs[0].frist -%}
{%- set pill = @@REPLY_PILL@@ -%}
{%- endif -%}
<ha-alert alert-type="warning" title="{{ @@OPEN_ONE@@ if total == 1 else total ~ @@OPEN_MANY@@ }}">{{ text | truncate(@@TITLE@@, True, '…') }}{{ @@MORE@@ if total > 1 else '' }}{% if pill %}<br><b>{{ pill }}</b>{% endif %}</ha-alert>
{%- elif is_state('@@CLOSED_TODAY@@', 'on') -%}
{%- set reason = clean(state_attr('@@CLOSED_TODAY@@', 'reason')) | trim -%}
### <ha-icon icon="mdi:calendar-remove"></ha-icon> @@CLOSED_TITLE@@

{{ reason ~ '. ' if reason else '' }}{{ '@@TOMORROW_CLOSED@@' if is_state('@@CLOSED_TOMORROW@@', 'on') else '@@TOMORROW_OPEN@@' }}
{%- elif ns.nodata > 0 or states(pending) in ['unavailable', 'unknown'] -%}
<ha-alert alert-type="warning" title="@@NODATA_TITLE@@">@@NODATA_SUB@@</ha-alert>
{%- else -%}
<ha-alert alert-type="info" title="@@CALM_TITLE@@">{{ '@@CALM_ORDERED@@' if ns.ordered > 0 else '@@CALM_NOTHING@@' }}</ha-alert>
{%- endif -%}
"""

KID = """
@@HELPERS@@
{%- set words = @@WORDS@@ -%}
{%- set icons = @@ICONS@@ -%}
### <ha-icon icon="mdi:silverware-fork-knife"></ha-icon> @@MEAL_FOR@@ @@NAME@@
{% if '@@NAME@@' == 'KI' ~ 'ND' -%}
@@TODO_KID@@
{%- else -%}
{%- set ns = namespace(from_plan=false) -%}
{% for ent, label, dish_ent in [('@@TODAY_ENTITY@@', '@@ROW_TODAY@@', '@@MENU_TODAY@@'), ('@@TOMORROW_ENTITY@@', '@@ROW_TOMORROW@@', '@@MENU_TOMORROW@@')] %}
{%- set st = states(ent) -%}
{%- set dish = clean(states(dish_ent)) | trim if states(dish_ent) not in ['unknown', 'unavailable', 'none', ''] else '' -%}
{%- set meal = dish or (clean(state_attr(ent, 'meal')) | trim) -%}
{%- set ns.from_plan = ns.from_plan or (dish != '' and st != 'not_offered') -%}

**{{ label }}** · {{ icons[st] if st in icons else '?' }} **{{ words[st] if st in words else st }}**
{% if st != 'not_offered' and meal -%}
{{ meal | truncate(@@TITLE@@, True, '…') }}{{ ' · @@VEGETARIAN@@' if dish and is_state_attr(dish_ent, 'vegetarian', true) else '' }}{{ ' · @@CHECK@@' if dish and is_state_attr(dish_ent, 'uncertain', true) else '' }}
{% endif %}
{% endfor %}
{%- if ns.from_plan %}
<small>@@FROM_PLAN@@</small>
{% endif %}
{%- set dlstate = states('@@DEADLINE_ENTITY@@') -%}
{%- if dlstate not in ['unknown', 'unavailable', 'none', ''] -%}
{%- set dl = as_datetime(dlstate) | as_local -%}
{%- set dayl = @@TODAY@@ if dl.date() == now().date() else (@@TOMORROW@@ if (dl.date() - now().date()).days == 1 else wd[dl.weekday()] ~ ' ' ~ ('%02d' | format(dl.day)) ~ '.' ~ ('%02d' | format(dl.month)) ~ '.') %}

<small>@@NEXT_DEADLINE@@: <b>{{ dayl }}, {{ dl.strftime('%H:%M') }}</b></small>
{%- endif -%}
{%- endif -%}
"""

BOARD = """
@@HELPERS@@
### <ha-icon icon="mdi:bulletin-board"></ha-icon> @@BOARD@@
{% set posts = state_attr('@@ENTITY@@', 'posts') or [] -%}
{% if posts | count == 0 -%}
@@NO_POST@@
{%- else -%}
{%- set p = posts[0] -%}
{%- set head = clean(p.titel) | trim -%}

**{{ (head if head else '@@UNTITLED@@') | truncate(@@TITLE@@, True, '…') }}**
{% if p.datum %}
{{ dlabel(p.datum) }}
{% endif -%}
@@EXCERPT@@
{%- endif -%}
"""

EXCERPT = """
{%- set body = clean(p.text) | trim -%}
{% if body %}
{{ body | truncate(@@LENGTH@@, True, '…') }}
{% endif -%}
"""

# Attached files (a meal plan is often a PDF) open in a new tab through a signed, expiring Home Assistant address.
# Only addresses of this integration are linked; anything else is shown as plain text.
ATTACHMENTS = """
{%- set files = (p.attachments or [])[:2] -%}
{% if files %}
@@ATTACHED@@: {% for f in files %}{% set label = clean(f.name) | trim | truncate(@@TITLE@@, True, '…') %}{% if f.url and f.url.startswith('/api/kitaplus/') %}<a href="{{ f.url }}" target="_blank" rel="noopener">{{ label }}</a>{% else %}{{ label }}{% endif %}{{ ', ' if not loop.last }}{% endfor %}
{% endif -%}
"""


MAIL = """
@@HELPERS@@
{%- set count = states('@@ENTITY@@') | int(0) -%}
{%- set items = state_attr('@@ENTITY@@', 'messages') or [] -%}
{%- set replies = state_attr('@@PENDING@@', 'messages') or [] -%}
### <ha-icon icon="mdi:email-outline"></ha-icon> @@MAILBOX@@ · {{ count }} {{ '@@MESSAGE_ONE@@' if count == 1 else '@@MESSAGES@@' }}
{% for m in items[:@@LIMIT@@] %}
{%- set head = clean(m.titel) | trim -%}
{%- set due = namespace(value='') -%}
{%- for r in replies if r.id == m.id and r.frist -%}{%- set due.value = r.frist -%}{%- endfor %}

**{{ (head if head else '@@UNTITLED@@') | truncate(@@TITLE@@, True, '…') }}**
{{ dlabel(m.datum) if m.datum else '' }}{% if due.value %} · **@@REPLY_UNTIL@@ {{ dlabel(due.value) }}**{% elif @@WALL@@ %} · @@NO_REPLY_OPEN@@{% endif %}
{% endfor -%}
"""

NEXT = """
@@HELPERS@@
### <ha-icon icon="mdi:calendar"></ha-icon> @@NEXT@@
{% set entries = state_attr('@@ENTITY@@', 'entries') or [] -%}
{% if entries | count == 0 -%}
@@NO_DATES@@
{%- endif %}
{% for e in entries[:@@LIMIT@@] %}
{%- set head = clean(e.titel) | trim %}
**{{ dlabel(e.datum) }}** · {{ (head if head else '@@UNTITLED@@') | truncate(@@TITLE@@, True, '…') }}{% if e.zeit %} · {{ e.zeit }}@@CLOCK@@{% endif %}{% if e.schliesstag %} · **@@CLOSURE@@**{% endif %}

{% endfor -%}
"""


# ----------------------------------------------------------------------------------------------- cards


def markdown(content: str, *, text_only: bool = False) -> dict:
    card: dict[str, Any] = {"type": "markdown", "content": content}
    if text_only:
        card["text_only"] = True
    return card


def tile(entity: str, name: str, icon: str, *, content: list[str] | None = None) -> dict:
    card: dict[str, Any] = {"type": "tile", "entity": entity, "name": name, "icon": icon}
    if content:
        card["state_content"] = content
    return card


def header_card(t: dict[str, Any], *, wall: bool = False) -> dict:
    if wall:
        return markdown(
            fill(HEADER_WALL, WEEKDAYS=jlist(t["weekdays"]), MONTHS=jlist(t["months"])), text_only=True
        )
    content = fill(
        HEADER, WEEKDAYS=jlist(t["weekdays"]), MONTHS=jlist(t["months"]), DATE=t["date_expr"], APP=t["app"]
    )
    return markdown(content, text_only=True)


def hero_card(t: dict[str, Any], account: Ids, kids: list[tuple[Ids, str]]) -> dict:
    entries = ", ".join(
        "{{'n': {}, 't': {}, 'm': {}, 'd': {}}}".format(
            q(name),
            q(ids.of_child("sensor", "status_today")),
            q(ids.of_child("sensor", "status_tomorrow")),
            q(ids.of_child("sensor", "next_deadline")),
        )
        for ids, name in kids
    )
    weekdays_helpers = fill(
        "{%- set wd = @@WD@@ -%}\n{%- macro clean(t) -%}\n{%- set s = (t or '') | regex_replace('[<>&\"`*_#\\\\[\\\\]]', '') | regex_replace('[\\n\\r\\t ]+', ' ') | trim -%}\n"
        "{%- for w in s.split(' ') -%}{{ w | truncate(@@WORD@@, True, '…') }}{{ ' ' if not loop.last }}{%- endfor -%}\n{%- endmacro -%}\n"
        "{%- macro dlabel(iso) -%}\n{%- set d = as_datetime(iso) -%}\n{%- set mon = @@MON@@ -%}\n"
        "{%- if d -%}{{ wd[d.weekday()] }} {{ @@DATE_NUMERIC@@ }}{%- endif -%}\n{%- endmacro -%}\n",
        WD=jlist(t["weekdays_short"]),
        MON=jlist([m[:3] for m in t["months"]]),
        WORD=str(WORD_LENGTH),
        DATE_NUMERIC=t["date_numeric"],
    )
    body = fill(
        HERO,
        KIDS="[" + entries + "]",
        TODAY=q(t["today"]),
        TOMORROW=q(t["tomorrow"]),
        PENDING=account.account("sensor", "pending"),
        MISSED_TITLE=t["missed_title"],
        MISSED_ONE=t["missed_one"],
        MISSED_MANY=t["missed_many"],
        TITLE="110",
        ASK_KITA=t["ask_kita"],
        ORDER_ITEM_O=t["order_item"],
        REPLY_ITEM=t["reply_item"],
        HOURS=t["hours"],
        MINUTES=t["minutes"],
        DEADLINE_PILL=t["deadline_pill"],
        LEFT=t["left"],
        REPLY_PILL=t["reply_pill"],
        OPEN_ONE=q(t["open_one"]),
        OPEN_MANY=t["open_many"],
        MORE=t["more"],
        CLOSED_TODAY=account.account("binary_sensor", "closed_today"),
        CLOSED_TOMORROW=account.account("binary_sensor", "closed_tomorrow"),
        CLOSED_TITLE=t["closed_title"],
        TOMORROW_OPEN=t["tomorrow_open"],
        TOMORROW_CLOSED=t["tomorrow_closed"],
        TODO_TITLE=t["todo_title"],
        TODO_SUB=t["todo_sub"],
        NODATA_TITLE=t["nodata_title"],
        NODATA_SUB=t["nodata_sub"],
        CALM_TITLE=t["calm_title"],
        CALM_ORDERED=t["calm_ordered"],
        CALM_NOTHING=t["calm_nothing"],
    )
    return markdown(weekdays_helpers + body, text_only=True)  # the alert is the frame, no second card border


def kita_cards(t: dict[str, Any], account: Ids) -> list[dict]:
    """Is the Kita open today and tomorrow? The state in words; the reason (for example a bridge day) follows."""
    return [
        tile(
            account.account("binary_sensor", "closed_today"),
            t["kita_today"],
            "mdi:school-outline",
            content=["state", "reason"],
        ),
        tile(
            account.account("binary_sensor", "closed_tomorrow"),
            t["kita_tomorrow"],
            "mdi:school-outline",
            content=["state", "reason"],
        ),
    ]


def kid_card(t: dict[str, Any], ids: Ids, name: str) -> dict:
    content = fill(
        KID,
        HELPERS=helpers(t),
        WORDS="{" + ", ".join(f"{q(k)}: {q(v)}" for k, v in t["state_words"].items()) + "}",
        ICONS="{" + ", ".join(f"{q(k)}: {q(v)}" for k, v in ICON.items()) + "}",
        MEAL_FOR=t["meal_for"],
        NAME=name.replace("{", "").replace("%", ""),
        TODAY_ENTITY=ids.of_child("sensor", "status_today"),
        TOMORROW_ENTITY=ids.of_child("sensor", "status_tomorrow"),
        ROW_TODAY=t["row_today"],
        ROW_TOMORROW=t["row_tomorrow"],
        TITLE=str(TITLE_LENGTH),
        DEADLINE_ENTITY=ids.of_child("sensor", "next_deadline"),
        TODAY=q(t["today"]),
        TOMORROW=q(t["tomorrow"]),
        NEXT_DEADLINE=t["next_deadline"],
        TODO_KID=t["todo_kid"],
        MENU_TODAY=ids.account("sensor", "menu_today"),
        MENU_TOMORROW=ids.account("sensor", "menu_tomorrow"),
        VEGETARIAN=t["vegetarian"],
        CHECK=t["check_plan"],
        FROM_PLAN=t["from_plan"],
    )
    return markdown(content)


def board_card(t: dict[str, Any], account: Ids, *, wall: bool = False) -> dict:
    excerpt = "" if wall else fill(EXCERPT, LENGTH=str(BOARD_EXCERPT)).strip("\n")
    excerpt += fill(ATTACHMENTS, ATTACHED=t["attached"], TITLE=str(TITLE_LENGTH)).strip("\n")
    content = fill(
        BOARD,
        HELPERS=helpers(t),
        BOARD=t["board"],
        ENTITY=account.account("sensor", "board"),
        NO_POST=t["no_post"],
        UNTITLED=t["untitled"],
        TITLE=str(TITLE_LENGTH),
        EXCERPT=excerpt,
    )
    return markdown(content)


def mail_card(t: dict[str, Any], account: Ids, *, wall: bool = False) -> dict:
    content = fill(
        MAIL,
        HELPERS=helpers(t),
        ENTITY=account.account("sensor", "messages"),
        PENDING=account.account("sensor", "pending"),
        MAILBOX=t["mailbox"],
        MESSAGES=t["messages"],
        MESSAGE_ONE=t["message_one"],
        UNTITLED=t["untitled"],
        TITLE=str(TITLE_LENGTH),
        LIMIT="1" if wall else "2",
        REPLY_UNTIL=t["reply_until"],
        NO_REPLY_OPEN=t["no_reply_open"],
        WALL="true" if wall else "false",
    )
    return markdown(content)


def next_card(t: dict[str, Any], account: Ids, *, wall: bool = False) -> dict:
    content = fill(
        NEXT,
        HELPERS=helpers(t),
        NEXT=t["next"],
        ENTITY=account.account("sensor", "upcoming"),
        NO_DATES=t["no_dates"],
        LIMIT="2" if wall else "3",
        UNTITLED=t["untitled"],
        TITLE=str(TITLE_LENGTH),
        CLOCK=f" {t['clock']}" if t["clock"] else "",
        CLOSURE=t["closure"],
    )
    return markdown(content)


def balance_card(t: dict[str, Any], account: Ids) -> dict:
    return tile(account.account("sensor", "balance"), t["balance"], "mdi:wallet-outline", content=["state"])


def calendar_card(account: Ids, ids_for: list[Ids]) -> dict:
    """One calendar card for the full picture: it brings its own switch between list, week and month."""
    entities = [account.account("calendar", "appointments"), account.account("calendar", "closures")]
    entities += [ids.of_child("calendar", "meals") for ids in ids_for]
    return {"type": "calendar", "entities": entities, "initial_view": "listWeek"}


# --------------------------------------------------------------------------------------------- dashboard


def _grid(cards: list[dict]) -> dict:
    return {"type": "grid", "cards": cards}


def _view(title: str, path: str, icon: str, sections: list[dict], *, columns: int | None = None) -> dict:
    view: dict[str, Any] = {"title": title, "path": path, "icon": icon, "type": "sections"}
    if columns:
        view["max_columns"] = columns
    view["sections"] = sections
    return view


def _kids(language: str, children: list[str] | None) -> list[tuple[Ids, str]]:
    if children:
        return [(Ids(language, slugify(name)), name) for name in children]
    return [(Ids(language), PLACEHOLDER_NAME)]


def build(language: str, children: list[str] | None = None) -> dict:
    """The complete dashboard. `children` are names as shown in Home Assistant; None keeps the placeholder."""
    t = TEXT[language]
    account = Ids(language)
    kids = _kids(language, children)
    ids_for = [ids for ids, _ in kids]

    phone = [
        _grid([header_card(t), hero_card(t, account, kids), *kita_cards(t, account)]),
        _grid([kid_card(t, ids, name) for ids, name in kids]),
        _grid(
            [board_card(t, account), mail_card(t, account), next_card(t, account), balance_card(t, account)]
        ),
    ]
    wall = [
        _grid([header_card(t, wall=True), hero_card(t, account, kids), *kita_cards(t, account)]),
        _grid([kid_card(t, ids, name) for ids, name in kids]),
        _grid(
            [
                board_card(t, account, wall=True),
                mail_card(t, account, wall=True),
                next_card(t, account, wall=True),
                balance_card(t, account),
            ]
        ),
    ]
    return {
        "title": t["title"],
        "views": [
            _view(t["view_today"], "heute", "mdi:home-heart", phone, columns=1),
            _view(t["view_wall"], "wand", "mdi:television", wall, columns=3),
            _view(t["view_calendar"], "kalender", "mdi:calendar", [_grid([calendar_card(account, ids_for)])]),
        ],
    }


def single_cards(language: str) -> dict[str, dict]:
    """Stand-alone cards for people who already have a dashboard (one child, placeholders)."""
    t = TEXT[language]
    account = Ids(language)
    kids = _kids(language, None)
    ids = kids[0][0]
    de = language == "de"
    return {
        "status" if not de else "status": hero_card(t, account, kids),
        "kita": {"type": "grid", "columns": 2, "square": False, "cards": kita_cards(t, account)},
        "essen" if de else "meals": kid_card(t, ids, PLACEHOLDER_NAME),
        "schwarzes_brett" if de else "bulletin_board": board_card(t, account),
        "postfach" if de else "mailbox": mail_card(t, account),
        "als_naechstes" if de else "coming_up": next_card(t, account),
        "guthaben" if de else "balance": balance_card(t, account),
        "kalender" if de else "calendar": calendar_card(account, [ids]),
    }


# ------------------------------------------------------------------------------------------------ output


class _Dumper(yaml.SafeDumper):
    """Multi-line strings (the markdown templates) are written as readable blocks."""


def _str(dumper: yaml.SafeDumper, value: str) -> yaml.ScalarNode:
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _str)


def _version() -> str:
    manifest = Path(__file__).resolve().parent.parent / "custom_components" / "kitaplus" / "manifest.json"
    return str(json.loads(manifest.read_text())["version"])


# The oldest integration the template works with: the status card needs the order status and deadline
# sensors, "Als Nächstes" needs the sensor "Nächste Termine" (0.3.1); attached files appear from 0.3.3.
MIN_INTEGRATION = "0.3.1"
HEADERS = {
    "de": (
        "# KitaPlus-Dashboard (Vorlage) · Version {version} · benötigt KitaPlus ab {minimum}\n"
        "# Einbau: Einstellungen → Dashboards → Dashboard hinzufügen → öffnen → ⋮ → Raw-Konfigurationseditor.\n"
        "# Ersetze KIND durch den Vornamen deines Kindes (Anzeige) und kind durch denselben Namen in Kleinbuchstaben\n"
        "# (so heißen die Entities, siehe Einstellungen → Entitäten). Mehrere Kinder: README in diesem Ordner.\n"
        "# Links zu angehängten Dateien (zum Beispiel Menüplan) brauchen KitaPlus ab 0.3.3, Gerichte aus dem Menüplan ab 0.4.0.\n"
        "# Diese Datei wird erzeugt (scripts/build_dashboards.py), bitte nicht in der Vorlage selbst ändern.\n"
    ),
    "en": (
        "# KitaPlus dashboard (template) · version {version} · needs KitaPlus {minimum} or newer\n"
        "# Install: Settings → Dashboards → Add dashboard → open it → ⋮ → Raw configuration editor.\n"
        "# Replace KIND with your child's first name (display) and kind with the same name in lower case\n"
        "# (that is how the entities are named, see Settings → Entities). Several children: see the README here.\n"
        "# Links to attached files (for example the meal plan) need KitaPlus 0.3.3, dishes from the menu plan 0.4.0 or newer.\n"
        "# This file is generated (scripts/build_dashboards.py), please do not edit the template itself.\n"
    ),
}


def header(language: str, *, first_line_only: bool = False) -> str:
    text = HEADERS[language].format(version=_version(), minimum=MIN_INTEGRATION)
    return text.split("\n")[0] + "\n" if first_line_only else text


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
        target.write_text(dump(build(language), header(language)))
        written.append(target)
        cards_dir = root / "cards" / language
        cards_dir.mkdir(parents=True, exist_ok=True)
        for stale in cards_dir.glob("*.yaml"):
            stale.unlink()  # a card that no longer exists must not linger
        for name, card in single_cards(language).items():
            path = cards_dir / f"{name}.yaml"
            path.write_text(dump(card, header(language, first_line_only=True)))
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
        sys.stdout.write(dump(build(args.language, names), header(args.language, first_line_only=True)))
        return 0
    for path in write_all(Path("dashboards")):
        print("wrote", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
