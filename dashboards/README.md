# Dashboard-Vorlagen für KitaPlus

Fertige Dashboards im neuen **Sections-Layout**, gebaut nur mit **eingebauten Karten** (nichts zusätzlich installieren,
passt zu jedem Theme, hell und dunkel).

| Datei | Inhalt |
|---|---|
| [`kitaplus_de.yaml`](kitaplus_de.yaml) | komplettes Dashboard, deutsche Installation |
| [`kitaplus_en.yaml`](kitaplus_en.yaml) | komplettes Dashboard, englische Installation |
| [`cards/de/`](cards/de), [`cards/en/`](cards/en) | einzelne Karten zum Einfügen in ein vorhandenes Dashboard |

> **Deutsch oder Englisch?** Home Assistant vergibt Entity-IDs in der Sprache, die **bei der Einrichtung der Integration**
> eingestellt war (`sensor.kitaplus_postfach` auf Deutsch, `sensor.kitaplus_mailbox` auf Englisch). Nimm die Datei, deren
> IDs bei dir stimmen. Schau unter *Einstellungen → Entitäten* nach „kitaplus“.

## Einbau (ca. 2 Minuten)
1. **Einstellungen → Dashboards → Dashboard hinzufügen**, ein leeres Dashboard (von Grund auf) anlegen, Namen „Kita“ vergeben und öffnen.
2. **⋮ (oben rechts) → Bearbeiten → ⋮ → Raw-Konfigurationseditor**, alles löschen und den Inhalt von `kitaplus_de.yaml` einfügen.
3. Zwei Platzhalter ersetzen (Suchen und Ersetzen im Editor, **Groß-/Kleinschreibung beachten**):
   - `KIND` → der Vorname deines Kindes, so wie er angezeigt werden soll (zum Beispiel `Finn`)
   - `kind` → derselbe Name in Kleinbuchstaben, so heißen die Entities (zum Beispiel `finn`; ein Name mit Umlaut wird
     einfach ohne Punkte geschrieben, `Jörg` wird `jorg`, `Strauß` wird `strauss`)
4. Speichern. Fehlt eine Karte oder zeigt sie „Entität nicht gefunden“, stimmt der Name nicht: in *Einstellungen → Entitäten*
   nachsehen, wie die Entity heißt.

## Mehrere Kinder
Entweder die Abschnitte „KIND“ im Editor kopieren und die Platzhalter ersetzen, oder fertig erzeugen lassen:

```bash
python3 scripts/build_dashboards.py --language de --children Anna,Ben > kita.yaml
```
Das Skript verwendet die Namen, wie sie in Home Assistant stehen, und erzeugt die Entity-IDs genau wie Home Assistant
(`Jörg` → `jorg`). Benötigt Python und `pip install pyyaml`.

## Was du siehst
1. **Heute** beantwortet zuerst: *Muss ich etwas tun?* Oben der Status (Kita heute und morgen geöffnet oder geschlossen,
   mit Grund). Darunter **Zu erledigen**: erscheint nur, wenn das Essen für morgen nicht bestellt ist oder eine Rückmeldung
   offen ist; sonst steht dort ruhig „Nichts zu tun“. Danach je Kind das Essen heute und morgen, dann das Guthaben mit
   Verlauf.
2. **Kalender** mit den nächsten 7 Tagen und dem Monat: Termine, Schließtage und bestelltes Essen.
3. **Mitteilungen**: Schwarzes Brett und Postfach mit Titel, Datum und Textanfang.
4. **Diagnose**: bis wann die Anmeldung gilt (Sensor erst einschalten) und alle Werte auf einen Blick.

Farben tragen nie allein die Aussage: Jede Kachel schreibt den Zustand in Worten („Geschlossen“, „Nicht bestellt“) und
hat ein Symbol. Es gibt keine festen Farbwerte, nur Theme-Farben.

## Hinweise
- Der **Guthaben-Verlauf** zeigt höchstens die letzten 10 Tage, so lange hält Home Assistant den Verlauf standardmäßig vor.
- Die **Vorlagen werden erzeugt** (`scripts/build_dashboards.py`) und von Tests geprüft: gültiges YAML, nur eingebaute Karten,
  jede Entity-ID existiert in der deutschen und der englischen Installation, jede Markdown-Karte rendert mit echten
  Zuständen. Bitte ändere deshalb die Datei in deinem eigenen Dashboard, nicht hier im Repository.
- Gefällt dir etwas nicht oder sieht etwas auf deinem Gerät falsch aus? Ein [Issue](https://github.com/dbl-mm/ha-kitaplus/issues)
  mit Screenshot (ohne Namen und Kontostand) hilft.
