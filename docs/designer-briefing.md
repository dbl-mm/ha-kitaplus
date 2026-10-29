# Briefing für Designer: KitaPlus in Home Assistant

Wer das Dashboard gestalten möchte, findet hier, **was an Daten da ist, wie aktuell es ist und was es nicht gibt**. Der heutige
Entwurf (`dashboards/`) ist eine Ausgangsbasis, kein Muss. Alles Folgende gilt für das Lesen. Die Integration bestellt nichts.

## 1. Für wen und wofür
Eltern mit Kindern in einer Kita, die **kitaplus** nutzt. Typische Fragen, die ein Dashboard beantworten soll:
1. Muss ich heute etwas tun? (Essen bestellen, auf eine Nachricht antworten)
2. Ist die Kita heute und morgen geöffnet?
3. Was isst mein Kind heute und morgen, und ist es bestellt?
4. Was gibt es Neues (Schwarzes Brett, Postfach), was steht an (Termine, Schließtage)?
5. Wie viel Guthaben ist auf dem Verpflegungskonto?

Nutzung vor allem **mobil und kurz** (Blick aufs Handy), dazu ein Wand-Tablet. Hell und dunkel müssen beide stimmen.

## 2. Was es gibt

### Pro Konto (Gerät „KitaPlus“)
| Inhalt | Art | Werte / Zustand | Zusatzangaben (Attribute) |
|---|---|---|---|
| Kita heute, Kita morgen | Ja/Nein | **Geschlossen** / **Geöffnet** (Schließtage und Feiertage) | `reason`: Name des Schließtags, zum Beispiel „Brückentag“ (kann leer sein) |
| Schwarzes Brett | Text | Titel des neuesten Beitrags | `posts`: bis zu 5 Beiträge mit `titel`, `datum`, `text` (bis 500 Zeichen), `id` |
| Postfach | Zahl | Anzahl der Nachrichten (nicht nur ungelesene) | `messages`: bis zu 5 Nachrichten (`titel`, `datum`, `text`, `id`) |
| Offene Rückmeldungen | Zahl | Nachrichten, die bestätigt werden müssen | `messages`: `titel`, `frist` (Datum), `id` |
| Guthaben Verpflegung | Betrag in EUR | zum Beispiel 87,55 | – |
| Sitzung gültig bis | Zeitpunkt | bis wann die gespeicherte Anmeldung gilt (technisch, standardmäßig aus) | – |
| Termine | Kalender | Termine der Kita (ganztägig oder mit Uhrzeit) | – |
| Schließtage | Kalender | Schließtage und Feiertage | – |

### Pro Kind (eigenes Gerät, benannt nach dem Vornamen)
| Inhalt | Art | Werte / Zustand | Zusatzangaben |
|---|---|---|---|
| **Bestellstatus heute / morgen** | Auswahl | **Bestellt**, **Offen** (bestellbar, noch nichts bestellt), **Frist verpasst**, **Kein Essen** | `meal`: Name des bestellten bzw. angebotenen Gerichts. Das Symbol wechselt je nach Zustand. |
| **Nächste Bestellfrist** | Zeitpunkt | wann die Bestellung für den nächsten offenen Tag schließt (nur, wenn die Frist eingetragen ist) | `day`: für welchen Tag |
| Essen heute / morgen | Text | Gericht(e), oder „Nichts bestellt“ | `offered`: alle Gerichte des Tages mit `art`, `variante`, `preis`, `bestellt`, `bestellbar`, `abbestellbar` |
| Morgen nicht bestellt | Ja/Nein (Problem) | Nicht bestellt / In Ordnung | `can_still_order` |
| Bestelltes Essen | Kalender | ein ganztägiger Eintrag pro bestelltem Tag | Beschreibung: Mahlzeit-Art |

### Ereignisse (für Benachrichtigungen)
`kitaplus_new_board_post` und `kitaplus_new_message` (`id`, `title`) bei Neuem; `kitaplus_order_deadline` kurz vor der Bestellfrist
(`child`, `day`, `days_ahead`, `weekday`, `deadline`, `minutes_left`). Dazu gibt es [fertige Blueprints](blueprints.md).

## 3. Wie aktuell ist es?
- Abfrage bei KitaPlus **alle 30 Minuten** (einstellbar 15 bis 240). Neue Beiträge können also bis dahin warten.
- „Heute“ und „Morgen“ rechnen **um Mitternacht** neu, ohne neue Abfrage.
- Mit eingetragener Bestellfrist springt der Bestellstatus **genau zur Frist** auf „Frist verpasst“.
- Der Speiseplan reicht **14 Tage** voraus, der Status gibt es nur für **heute und morgen**.
- Kein Live-Verlauf: Der Verlauf des Guthabens hat meist nur wenige Punkte, ein Diagramm lohnt nicht.

## 4. Was es nicht gibt (bitte nicht einplanen)
- **Keine Bilder, Fotos, Anhänge oder PDFs.** Der Speiseplan der Kita liegt als PDF am Schwarzen Brett und ist ohne Anmeldung nicht abrufbar. Es gibt nur den Titel.
- **Kein Wochenspeiseplan als Daten**, nur Gericht und Preis für heute und morgen (`offered`) sowie bestellte Tage im Kalender.
- **Keine Absender, Gruppen oder Lesestatus** bei Nachrichten, **keine Kontakte** und keine Telefonnummern (werden bewusst nicht gelesen).
- **Kein Bestellen, Abbestellen, Krankmelden** aus dem Dashboard (geplant für später, mit eindeutiger Rückmeldung).
- Kein Kontoauszug, nur der aktuelle Stand.
- Texte von Kitas sind **frei formuliert** und können Formatierungszeichen, Umbrüche und sehr lange Zeilen enthalten (Auszüge verwenden).
- Titel können leer sein.

## 5. Was Home Assistant fürs Gestalten bietet
- **Layout:** Ansicht „Sections“ (Spalten aus Abschnitten, wird auf dem Handy zu einer Spalte). Jeder Abschnitt hat eine Überschrift mit Symbol und optionalen kleinen Anzeigen („Badges“).
- **Karten:** Kachel (Symbol, Name, Zustand plus Attribute, Farbe), Überschrift, Markdown (mit Vorlagen für freien Text), bedingte Karte (ein-/ausblenden nach Zustand), Kalender (Liste, Woche, Monat), Verlaufs- und Statistikdiagramm, Entitäten-Liste, Schaltfläche, Raster, Stapel. Darüber hinaus beliebige Zusatzkarten aus HACS, falls ihr welche nutzen wollt (die Vorlage verzichtet bewusst darauf).
- **Farben:** Theme-Farben statt fester Werte (so bleiben hell und dunkel stimmig). Symbole aus dem Material-Design-Satz (mdi).
- **Zustände mit Worten:** Die Integration liefert alle Zustände schon als lesbaren Text („Geschlossen“, „Frist verpasst“). Farbe allein sollte nie die Aussage tragen.
- **Sprache:** Texte sind deutsch und englisch übersetzt. Die **Entity-IDs unterscheiden sich** je nach Sprache bei der Einrichtung und enthalten den Namen des Kindes.

## 6. Was ein Designer liefert und wie es sich prüfen lässt
- Ein Entwurf (Skizze, Figma o. Ä.) mit **allen Zuständen**: nichts zu tun, Essen offen, Frist verpasst, Kita geschlossen, mehrere Kinder, kein Beitrag, sehr langer Titel, Hell/Dunkel, Handy/Tablet.
- Die Umsetzung übernehmen wir als Vorlage. Der Generator `scripts/build_dashboards.py` und die Tests in `tests/test_dashboards.py` sichern ab, dass jede Entity existiert, nur eingebaute Karten genutzt werden und die Texte sauber rendern.
- Entscheidungen, die uns helfen: Was ist die **eine** wichtigste Information? Was darf wegfallen? Wie wird „Handlungsbedarf“ sichtbar, ohne zu erschrecken?

## Nachtrag: Sensor „Nächste Termine“
`sensor.kitaplus_nachste_termine` (englisch `upcoming_dates`): Zustand = Titel des nächsten Eintrags, Attribut `entries` = Liste mit `datum`, `zeit`, `titel`, `schliesstag` (Termine und Schließtage gemischt, nach Datum sortiert).
