# Changelog

Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach [SemVer](https://semver.org/lang/de/).

## [0.3.4]
### Geändert
- README neu gegliedert: Schnellstart, Vorschaubilder gleich am Anfang, Funktionen als Liste, Blueprints als Liste mit Import-Knöpfen gleicher Größe; Logo und Bilder mit absoluten Adressen, damit sie auch in HACS erscheinen.
- Korrektur: Ein Beitrag oder eine Nachricht, die nach einer kurz verkürzten KitaPlus-Antwort wiederkam, löste die Ereignisse `kitaplus_new_board_post` und `kitaplus_new_message` ein zweites Mal aus.
- Intern verschlankt: gemeinsamer Anmeldeschritt im Einrichtungsablauf, gemeinsame Basis der Essens-Sensoren, Sensoren „Offene Rückmeldungen“ und „Nächste Bestellfrist“ rechnen nicht mehr doppelt.

## [0.3.3]
### Neu
- **Anhänge öffnen:** Dateien an Beiträgen und Nachrichten (zum Beispiel ein Menüplan als PDF) lassen sich in Home Assistant öffnen. Der Sensor nennt sie im Attribut `attachments` (Name und Adresse, höchstens 3), das Dashboard zeigt beim neuesten Beitrag „Anhang: …“ als Link, der in einem neuen Tab öffnet. Die Adresse wird von Home Assistant **signiert und läuft ab**; abrufbar sind nur Dateien, die gerade an einem Beitrag oder einer Nachricht hängen. PDF und Bilder werden angezeigt, alles andere nur als Download. Dateipfade und Einrichtungs-IDs aus der KitaPlus-Antwort werden nicht gespeichert.

## [0.3.2]
### Geändert
- GitHub Actions sind auf feste Commit-Versionen gesetzt und werden über Dependabot aktuell gehalten.
- Sicherheit: Der Diagnose-Export zeigt nur noch eine feste Liste harmloser Felder (statt unbekannte Felder durchzulassen) und schwärzt die Konto-ID. Meldungen des KitaPlus-Servers werden im Anmeldeformular und in den Reparaturen als reiner, gekürzter Text angezeigt. Dashboard-Texte können keine Links mehr enthalten.
- Dashboard: kleine Zeichen (✓ ○ ✕) statt großer Symbole, Abstand zwischen den Zeilen, „1 Nachricht“.
- Dashboard: Ist die Frist vorbei und nichts bestellt, meldet die Statuskarte neutral „Nicht bestellt. Die Frist ist vorbei.“ (gelb statt rot, ohne „Bitte bei der Kita nachfragen“), denn oft ist das Absicht. Die Statuskarte hat keinen doppelten Rahmen mehr.

## [0.3.1]
### Neu
- **Dashboard-Vorlagen nach Designvorlage neu aufgebaut:** Ansichten Heute (Handy), Wand (Tablet, drei Spalten) und Kalender; eine Statuskarte mit fester Rangfolge, Essen pro Kind, Brett, Postfach, „Als Nächstes“. Neuer Sensor **Nächste Termine** (die nächsten Termine und Schließtage in einer Liste).
- Der Datenschutz-Scan prüft auch neue, noch nicht hinzugefügte Dateien.

## [0.3.0]
### Neu
- **Bestellfrist deiner Kita** in den Optionen (Tage vor dem Essen, Uhrzeit, optional nur Werktage, Vorlaufzeit der Erinnerung). Beispiel: „1 Tag vor Essenausgabe um 11:00 Uhr“.
  - Der **Bestellstatus** springt **genau zur Frist** auf „Frist verpasst“, auch wenn der letzte Abruf älter ist.
  - Neuer Sensor **Nächste Bestellfrist** (Zeitstempel) pro Kind.
  - Das Ereignis `kitaplus_order_deadline` wird zur eingestellten Zeit vor der Frist ausgelöst, nur wenn der Tag noch nicht bestellt ist und nachdem frische Daten geholt wurden.
- Neuer Blueprint **„Erinnerung kurz vor der Bestellfrist“** (braucht keine Uhrzeit, der Zeitpunkt ergibt sich aus der Frist).
- Frühere Fassung: drei Ansichten (Heute, Mitteilungen, Kalender) statt vier. Hinweise erscheinen nur, wenn du etwas tun kannst, und der Bereich verschwindet sonst ganz. Pro Kind genügen zwei Kacheln („Bestellt · Mittagessen“). Entfallen sind Diagramm, Diagnose-Ansicht, doppelter Kalender und alle Wiederholungen. Formatierungszeichen in Titeln der Kita (zum Beispiel `**Gartenfest**`) erscheinen nicht mehr als Sternchen.
- Der Bestellstatus nennt das Gericht im Attribut `meal`.
- [Briefing für Designer](docs/designer-briefing.md): was an Daten verfügbar ist, wie aktuell es ist und was es nicht gibt.

## [0.2.0]
### Neu
- Konten werden an der stabilen KitaPlus-Konto-ID erkannt statt an der E-Mail; bestehende Einträge werden beim ersten Start einmal umgestellt.
- „Neu konfigurieren“ (E-Mail ändern, neu anmelden); es wird nur dasselbe Konto akzeptiert.
- Neue Kinder erscheinen ohne Neuladen, entfernte Kinder verschwinden als Gerät.
- Diagnose-Sensor „Sitzung gültig bis“ (standardmäßig aus), Geräte mit Modell und Link.
- Übersetzte Fehlermeldungen, Icons über `icons.json`, Beschreibungen zu allen Eingabefeldern.
- Dokumentation: Entfernen, Datenaktualisierung, Anwendungsfälle, Fehlerbehebung.
- **Bestellstatus** pro Kind für heute und morgen (Bestellt, Offen, Frist verpasst, Kein Essen). Er übernimmt die Angabe von KitaPlus, ob noch bestellt werden kann. Blueprint und Dashboard fordern nach verpasster Frist nicht mehr zum Bestellen auf.
- **7 Blueprints** (Essen-Erinnerung, Schließtag, Neue Mitteilung, Rückmeldung, Guthaben, Sitzung läuft ab, Tagesbriefing), per Knopf im README importierbar.
- **Dashboard-Vorlagen** (Heute, Kalender, Mitteilungen, Diagnose) auf Deutsch und Englisch, nur eingebaute Karten, plus Einzelkarten.
- Die Sensoren „Heute/Morgen geschlossen“ nennen den Grund im Attribut `reason`; Kacheln zeigen „Geschlossen/Geöffnet“ und „Nicht bestellt“ statt Ein/Aus.
- `quality_scale.yaml` (Selbsteinstufung Platinum), `mypy --strict`, 100 % Testabdeckung.
### Behoben
- Fehlerantworten werden auch bei komprimierten Antworten gelesen, damit Wartungs- und Serverhinweise nicht verloren gehen.
- Eine bestellte Mahlzeit ohne Namen zeigt „Bestellt“ statt eines Fehlers.

## [0.1.1]
### Behoben
- Absturz nach dem Neustart von Home Assistant (gespeicherte Sitzung ohne JWT).
- E-Mail wird exakt wie eingegeben gesendet (kein Kleinschreiben).
- Serverfehler (502/429) beim Login werden nicht mehr als falsches Passwort gewertet.
- Pause von 15 Minuten nach 2 Fehlversuchen, auch wenn der Dialog neu gestartet wird.
- Erneuertes Refresh-Token wird sofort gespeichert.
- Offene oder fehlerhafte Datumswerte lassen Entities nicht mehr abstürzen; Termine über zwei Monate erscheinen nicht doppelt.
- „Heute/Morgen“-Werte werden um Mitternacht neu berechnet.
### Neu
- Optionen: Abfrageintervall (15 bis 240 Minuten).
- Eigene Logos, GitHub-Release-Ablauf für Updates über HACS.

## [0.1.0]
- Erste Version (nur lesend): Schwarzes Brett, Postfach, Termine, Schließtage, Speiseplan, Bestellungen, Kontostand.
