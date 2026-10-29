"""Typed shapes of the KitaPlus answers. Only the fields the integration reads are listed.

These are static types: the client trusts the shape at the edge, and the coordinator turns any
surprise (a missing key, a different type) into a clear, translated error instead of a crash.
"""

from __future__ import annotations

from typing import TypedDict


class ParentAccountRef(TypedDict):
    """The parent account (elternkonto) a child belongs to."""

    id: int | None


class Child(TypedDict):
    """A child, reduced to what the integration needs (no contacts, no birth date)."""

    id: int
    vorname: str | None
    istVppAktiv: bool
    elternkonto: ParentAccountRef


class Event(TypedDict, total=False):
    """An appointment, closure day or public holiday."""

    id: int
    name: str | None
    startdatum: str | None
    enddatum: str | None
    istSchliesstag: bool
    istFeiertag: bool


class Order(TypedDict, total=False):
    istAbbestellt: bool


class Variant(TypedDict, total=False):
    name: str | None
    preis: str | None
    istBestellbar: bool
    istAbbestellbar: bool
    bestellung: Order | None


class MealType(TypedDict, total=False):
    name: str | None
    varianten: list[Variant]


class Day(TypedDict, total=False):
    """One day of the meal plan with its meals and the orders for them."""

    datum: str | None
    mahlzeitArten: list[MealType]


class BoardPost(TypedDict, total=False):
    id: int
    datum: str | None
    titel: str | None
    text: str | None


class Note(TypedDict, total=False):
    datum: str | None
    titel: str | None
    text: str | None
    istBestaetigungspflichtig: bool
    rueckmeldefrist: str | None


class Message(TypedDict, total=False):
    id: int
    abrufDatum: str | None
    istBeantwortet: bool
    nachricht: Note | None


class Account(TypedDict, total=False):
    id: int
    istAktiv: bool
    kontostand: str | None


class UpcomingEntry(TypedDict):
    """One of the next appointments or closure days, flattened for dashboards."""

    datum: str  # YYYY-MM-DD; an ongoing multi-day entry shows today
    zeit: str | None  # HH:MM for timed entries, None for all-day entries
    titel: str
    schliesstag: bool  # closure day or public holiday


class MealEntry(TypedDict):
    """One meal variant of a day, flattened by helpers.meals_on."""

    art: str | None
    variante: str | None
    preis: str | None
    bestellt: bool
    bestellbar: bool
    abbestellbar: bool


class PendingReply(TypedDict):
    id: int | None
    titel: str | None
    frist: str | None
