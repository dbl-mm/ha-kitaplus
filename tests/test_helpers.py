from datetime import date

from custom_components.kitaplus.helpers import is_closed_on, meals_on, pending_replies

from .conftest import load


def test_closed_on_covers_range():
    events = [
        {
            "istSchliesstag": True,
            "istFeiertag": False,
            "startdatum": "2026-12-24T00:00:00",
            "enddatum": "2026-12-26T23:59:00",
        }
    ]
    assert is_closed_on(events, date(2026, 12, 25))
    assert not is_closed_on(events, date(2026, 12, 27))


def test_normal_appointment_is_not_a_closure():
    events = [
        {
            "istSchliesstag": False,
            "istFeiertag": False,
            "startdatum": "2026-11-11T16:00:00",
            "enddatum": "2026-11-11T18:00:00",
        }
    ]
    assert not is_closed_on(events, date(2026, 11, 11))


def test_meals_flatten_and_cancelled_order_is_not_ordered():
    days = [
        {
            "datum": "2026-11-02T00:00:00",
            "mahlzeitArten": [
                {
                    "name": "Mittag",
                    "varianten": [
                        {
                            "name": "A",
                            "preis": "3.50",
                            "istBestellbar": True,
                            "istAbbestellbar": True,
                            "bestellung": {"istAbbestellt": True},
                        },
                        {
                            "name": "B",
                            "preis": "3.50",
                            "istBestellbar": True,
                            "istAbbestellbar": True,
                            "bestellung": {"istAbbestellt": False},
                        },
                    ],
                }
            ],
        }
    ]
    meals = meals_on(days, date(2026, 11, 2))
    assert [m["bestellt"] for m in meals] == [False, True]
    assert meals_on(days, date(2026, 11, 3)) == []


def test_pending_replies_ignores_answered():
    msgs = [
        {
            "id": 1,
            "istBeantwortet": False,
            "nachricht": {"istBestaetigungspflichtig": True, "titel": "x", "rueckmeldefrist": None},
        },
        {"id": 2, "istBeantwortet": True, "nachricht": {"istBestaetigungspflichtig": True, "titel": "y"}},
        {"id": 3, "istBeantwortet": False, "nachricht": {"istBestaetigungspflichtig": False, "titel": "z"}},
    ]
    assert [m["id"] for m in pending_replies(msgs)] == [1]


def test_fixtures_have_expected_shape():
    assert "istSchliesstag" in load("termine")["data"][0]
    day = next(d for d in load("bestelldaten")["data"][0]["tage"] if d["mahlzeitArten"])
    assert "varianten" in day["mahlzeitArten"][0]
    assert "nachricht" in load("getNachrichten")["data"][0]


def test_open_ended_or_broken_dates_do_not_crash():
    events = [
        {"istSchliesstag": True, "startdatum": "2026-12-24T00:00:00", "enddatum": None},
        {"istSchliesstag": True, "startdatum": None, "enddatum": None},
        {"istSchliesstag": True, "startdatum": "garbage", "enddatum": "garbage"},
    ]
    assert is_closed_on(events, date(2026, 12, 24))  # an open end counts for the first day
    assert not is_closed_on(events, date(2026, 12, 25))
    assert meals_on([{"datum": None}, {}], date(2026, 12, 24)) == []


def test_upcoming_entries_are_sorted_flattened_and_skip_what_is_over_or_broken() -> None:
    from custom_components.kitaplus.helpers import upcoming_entries

    today = date(2026, 10, 29)
    events = [
        {
            "id": 1,
            "name": "Elternabend",
            "startdatum": "2026-11-02T19:30:00",
            "enddatum": "2026-11-02T21:00:00",
        },
        {
            "id": 2,
            "name": "Teamtag",
            "istSchliesstag": True,
            "startdatum": "2026-11-16T00:00:00",
            "enddatum": "2026-11-16T23:59:00",
        },
        {
            "id": 3,
            "name": "Brückentage",
            "istSchliesstag": True,
            "startdatum": "2026-10-28T00:00:00",
            "enddatum": "2026-10-30T23:59:00",
        },
        {"id": 4, "name": "Gestern", "startdatum": "2026-10-27T10:00:00", "enddatum": "2026-10-27T11:00:00"},
        {"id": 5, "name": "Ohne Start", "startdatum": None},
        {"id": 6, "name": "Kaputt", "startdatum": "garbage"},
        {"id": 7, "name": "Open end", "startdatum": "2026-11-01T00:00:00", "enddatum": None},
        {"id": 8, "name": None, "startdatum": "2026-11-20T08:00:00", "enddatum": "2026-11-20T09:00:00"},
    ]
    entries = upcoming_entries(events, today, limit=5)
    assert [(e["datum"], e["zeit"], e["titel"], e["schliesstag"]) for e in entries] == [
        ("2026-10-29", None, "Brückentage", True),  # running since yesterday: shown today
        ("2026-11-01", None, "Open end", False),
        ("2026-11-02", "19:30", "Elternabend", False),
        ("2026-11-16", None, "Teamtag", True),
        ("2026-11-20", "08:00", "", False),
    ]
    assert len(upcoming_entries(events, today, limit=2)) == 2
    assert upcoming_entries([], today) == []


def test_server_messages_are_shown_as_short_plain_text() -> None:
    from custom_components.kitaplus.helpers import plain_text

    assert plain_text(None) == ""
    assert plain_text("Falsches   Passwort\n") == "Falsches Passwort"
    assert (
        plain_text("Klick [hier](https://example.com) <b>jetzt</b> *fett*")
        == "Klick hierhttps://example.com bjetzt/b fett"
    )
    assert len(plain_text("x" * 500)) == 200
