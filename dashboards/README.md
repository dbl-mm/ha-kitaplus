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

## Vorschau

> Entwurf des Designs (Mockups mit erfundenen Daten). In deinem Home Assistant wirkt es etwas schlichter, weil Farben, Schriften und Rundungen von deinem Theme kommen. Echte Bildschirmfotos folgen.

<p>
<img src="../docs/img/heute-nichts-zu-tun.png" alt="Heute: nichts zu tun" width="230">
<img src="../docs/img/heute-essen-offen.png" alt="Heute: Essen für ein Kind noch offen" width="230">
<img src="../docs/img/heute-frist-verpasst-dunkel.png" alt="Heute: Frist verpasst, dunkles Theme" width="230">
<img src="../docs/img/heute-kita-geschlossen.png" alt="Heute: Kita geschlossen" width="230">
</p>

## Was du siehst
**Heute** (Handy, eine Spalte), von oben nach unten:
1. **Datum und Status:** eine Karte sagt das Wichtigste. Rangfolge: *Nicht bestellt* (Frist vorbei, gelb, bewusst ohne Alarm: Essen wird oft absichtlich abbestellt) vor *N Sachen sind offen* (mit Frist und
   Restzeit oder „Antwort bis …“) vor *Kita heute geschlossen* (mit Grund und Hinweis zu morgen) vor *Heute ist nichts zu tun*.
   Sind keine Daten da, steht das auch dort.
2. **Kita heute / morgen:** geöffnet oder geschlossen, mit Grund.
3. **Essen für <Kind>:** Heute und Morgen mit Zustand in Worten („Bestellt“, „Offen“, „Frist verpasst“, „Kein Essen“), Symbol und Gericht, darunter die nächste Bestellfrist.
4. **Schwarzes Brett:** nur der neueste Beitrag (Titel, Datum, Textanfang).
5. **Postfach:** Anzahl und die letzten zwei Nachrichten; wartet eine auf Antwort, steht „Rückmeldung bis …“ dabei.
6. **Als Nächstes:** die nächsten drei Termine, Schließtage sind markiert.
7. **Guthaben.**

**Wand** (Tablet im Querformat, drei Spalten): links Datum, Status und Kita; Mitte die Kinder; rechts Brett, Postfach, Termine, Guthaben,
jeweils kürzer. **Kalender:** eine Karte mit Terminen, Schließtagen und bestelltem Essen.

Schriften und Farben kommen von deinem Theme. Dafür braucht die Vorlage den Sensor **Nächste Termine** (ab Integration 0.3.0).

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
