# Dashboard-Vorlagen für KitaPlus

Ein bewusst **ruhiges** Dashboard: Es zeigt nur, was du wissen musst, und nur dann Hinweise, wenn du etwas tun kannst.
Gebaut im Sections-Layout, nur mit **eingebauten Karten** (nichts zusätzlich installieren, passt zu jedem Theme).

| Datei | Inhalt |
|---|---|
| [`kitaplus_de.yaml`](kitaplus_de.yaml) | komplettes Dashboard, deutsche Installation |
| [`kitaplus_en.yaml`](kitaplus_en.yaml) | komplettes Dashboard, englische Installation |
| [`cards/de/`](cards/de), [`cards/en/`](cards/en) | einzelne Karten zum Einfügen in ein vorhandenes Dashboard |

> **Deutsch oder Englisch?** Home Assistant vergibt Entity-IDs in der Sprache, die **bei der Einrichtung der Integration**
> eingestellt war (`sensor.kitaplus_postfach` auf Deutsch, `sensor.kitaplus_mailbox` auf Englisch). Nimm die Datei, deren
> IDs bei dir stimmen. Schau unter *Einstellungen → Entitäten* nach „kitaplus“.

> **Voraussetzung:** die aktuelle Integration (Bestellstatus und Bestellfrist gibt es ab 0.2.0 bzw. 0.3.0). Zeigt eine Karte
> „Entität nicht gefunden“, ist meist die Integration noch alt: in HACS aktualisieren und Home Assistant neu starten.

## Was du siehst
**Heute**
1. **Hinweise** (nur wenn nötig, sonst verschwindet der Bereich): *Essen für morgen bestellen* bzw. *für heute noch bestellen*,
   jeweils mit dem Gericht und der **Bestellfrist** darunter, und *Rückmeldungen offen* mit Titel und Frist. Es erscheint nur
   etwas, solange noch bestellt werden kann; ist die Frist vorbei, wird nicht mehr dazu aufgefordert.
2. **Kita:** *Kita heute* und *Kita morgen* (Geöffnet oder Geschlossen, bei Schließtagen mit Grund).
3. **Dein Kind:** *Heute* und *Morgen* in einer Zeile, zum Beispiel „Bestellt · Mittagessen“ oder „Offen · Mittagessen“.
4. **Konto:** das Guthaben.

**Mitteilungen:** Schwarzes Brett (die letzten 4) und Postfach (die letzten 3) mit Titel, Datum und Textanfang.
**Kalender:** eine Karte mit Termine, Schließtage und bestelltem Essen. Sie hat selbst einen Umschalter zwischen Liste, Woche und Monat.

Farben tragen nie allein die Aussage: Jede Kachel schreibt den Zustand in Worten und hat ein Symbol. Es gibt keine festen
Farbwerte, nur Theme-Farben.

## Einbau (ca. 2 Minuten)
1. **Einstellungen → Dashboards → Dashboard hinzufügen**, ein leeres Dashboard (von Grund auf) anlegen, Namen „Kita“ vergeben, öffnen.
2. **⋮ (oben rechts) → Bearbeiten → ⋮ → Raw-Konfigurationseditor**, alles löschen und den Inhalt von `kitaplus_de.yaml` einfügen.
3. Zwei Platzhalter ersetzen (Suchen und Ersetzen im Editor, **Groß-/Kleinschreibung beachten**):
   - `KIND` → der Vorname deines Kindes, so wie er angezeigt werden soll (zum Beispiel `Finn`)
   - `kind` → derselbe Name in Kleinbuchstaben, so heißen die Entities (zum Beispiel `finn`). Umlaute und Sonderzeichen
     schreibt Home Assistant einfach, `Jörg` wird `jorg`, `Strauß` wird `strauss`.
4. Speichern. Zeigt eine Karte „Entität nicht gefunden“, stimmt der Name nicht oder die Integration ist noch alt (siehe oben).

## Mehrere Kinder
Entweder die Abschnitte „KIND“ im Editor kopieren und die Platzhalter ersetzen, oder fertig erzeugen lassen:

```bash
python3 scripts/build_dashboards.py --language de --children Anna,Ben > kita.yaml
```
Das Skript verwendet die Namen, wie sie in Home Assistant stehen, und erzeugt die Entity-IDs genau wie Home Assistant
(`Jörg` → `jorg`). Benötigt Python und `pip install pyyaml`. Bei mehreren Kindern nennen die Hinweise auch den Namen.

## Hinweise
- Die **Bestellfrist** wird angezeigt, sobald du sie bei der Integration eingetragen hast (README, Abschnitt „Bestellfristen“).
  Ohne sie steht dort „Unbekannt“, und es gilt nur die Angabe von KitaPlus, ob noch bestellt werden kann.
- Die **Vorlagen werden erzeugt** (`scripts/build_dashboards.py`) und von Tests geprüft: gültiges YAML, nur eingebaute Karten,
  jede Entity-ID existiert in der deutschen und der englischen Installation, jede Markdown-Karte rendert mit echten Zuständen.
  Ändere deshalb die Datei in deinem eigenen Dashboard, nicht hier im Repository.
- Willst du das Aussehen von jemandem gestalten lassen? Das [Briefing für Designer](../docs/designer-briefing.md) listet alles auf,
  was verfügbar ist.
- Gefällt dir etwas nicht? Ein [Issue](https://github.com/dbl-mm/ha-kitaplus/issues) mit Screenshot (ohne Namen und Kontostand) hilft.
