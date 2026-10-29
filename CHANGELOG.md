# Changelog

Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach [SemVer](https://semver.org/lang/de/).

## [0.2.0]
### Neu
- Konten werden an der stabilen KitaPlus-Konto-ID erkannt statt an der E-Mail; bestehende Einträge werden beim ersten Start einmal umgestellt.
- „Neu konfigurieren“ (E-Mail ändern, neu anmelden); es wird nur dasselbe Konto akzeptiert.
- Neue Kinder erscheinen ohne Neuladen, entfernte Kinder verschwinden als Gerät.
- Diagnose-Sensor „Sitzung gültig bis“ (standardmäßig aus), Geräte mit Modell und Link.
- Übersetzte Fehlermeldungen, Icons über `icons.json`, Beschreibungen zu allen Eingabefeldern.
- Dokumentation: Entfernen, Datenaktualisierung, Anwendungsfälle, Fehlerbehebung.
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
