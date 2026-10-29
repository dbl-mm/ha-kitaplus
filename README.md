# KitaPlus für Home Assistant

Inoffizielle Home-Assistant-Integration für die **kitaplus Eltern-App** (eltern.kitaplus.de). Sie zeigt Schwarzes Brett, Postfach, Termine und Schließtage, Speiseplan und Bestellungen sowie den Verpflegungs-Kontostand in Home Assistant an.

> **Wichtig, bitte lesen**
> - Dieses Projekt ist **nicht** von kitaplus und steht in keiner Verbindung zu kitaplus oder deiner Kita.
> - Es gibt keine öffentliche API. Die Integration nutzt dieselben Schnittstellen wie die Eltern-App im Browser. Sie kann **jederzeit nach einem Update von kitaplus aufhören zu funktionieren**.
> - Die Nutzung geschieht **auf eigene Verantwortung**. Prüfe, ob die Nutzungsbedingungen deiner Kita bzw. von kitaplus eine solche Nutzung erlauben.
> - Version 0.1 ist **nur lesend**. Es wird nichts bestellt, gebucht, abbestellt oder gemeldet.

## Funktionen

| Bereich | Entities |
|---|---|
| Schwarzes Brett | Sensor mit dem neuesten Titel, die letzten Beiträge als Attribut |
| Postfach | Anzahl Nachrichten, „Offene Rückmeldungen“ (Nachrichten, die bestätigt werden müssen) |
| Kalender | „Termine“, „Schließtage“ (inkl. Feiertage) und pro Kind „Bestelltes Essen“ |
| Verpflegung | pro Kind „Essen heute“, „Essen morgen“, „Morgen nicht bestellt“; Kontostand |
| Kita | „Heute geschlossen“, „Morgen geschlossen“ |
| Events | `kitaplus_new_board_post`, `kitaplus_new_message` (nicht beim ersten Abruf) |

Jedes Kind erscheint als eigenes Gerät.

## Installation

### HACS (empfohlen)
1. HACS → ⋮ → **Benutzerdefinierte Repositories** → `https://github.com/dbl-mm/ha-kitaplus`, Kategorie **Integration**.
2. „KitaPlus“ installieren und Home Assistant neu starten.
3. **Einstellungen → Geräte & Dienste → Integration hinzufügen → KitaPlus**.

### Manuell
Den Ordner `custom_components/kitaplus` nach `<config>/custom_components/kitaplus` kopieren und neu starten.

## Updates

Über HACS bekommst du Updates wie bei jeder anderen Integration: HACS legt eine **Update-Entität** an, Home Assistant zeigt unter **Einstellungen → System → Updates** (und in der Seitenleiste) ein Update an, und du installierst es mit einem Klick. Danach ist ein **Neustart von Home Assistant** nötig. Die gespeicherte Anmeldung bleibt erhalten, es gibt **keine neue Anmeldung** bei KitaPlus.

Was jede Version ändert, steht im [Changelog](CHANGELOG.md) und in den [GitHub-Releases](https://github.com/dbl-mm/ha-kitaplus/releases). Versionen folgen [SemVer](https://semver.org/lang/de/): `0.1.x` sind Fehlerbehebungen, `0.x.0` bringen neue Funktionen.

## Einrichtung und Anmeldung

Du brauchst die E-Mail-Adresse und das **Passwort** deines KitaPlus-Eltern-Zugangs. **Passkeys funktionieren nicht**; falls du dich bisher nur per Passkey anmeldest, setze in der KitaPlus-App ein Passwort. Ist bei dir Zwei-Faktor aktiv (Authenticator-App oder E-Mail-Code), fragt die Einrichtung den Code ab.

**Zum Schutz deines Kontos gilt:**
- Jeder Klick auf „Absenden“ ist **genau ein** Anmeldeversuch. Es gibt keine automatischen Wiederholungen.
- Die Einrichtung **bricht nach 2 Fehlversuchen ab**, weil KitaPlus Konten nach zu vielen Fehlversuchen sperren kann. Eine Sperre kann **nur die Kita-Leitung** aufheben.
- Die Meldung von KitaPlus wird dir unverändert angezeigt, dazu der Zählerstand („Fehlversuch 1 von 2“).
- Läuft die Sitzung später ab oder wird sie abgelehnt, **stoppt die Integration die Abfragen** und zeigt unter **Einstellungen → Reparaturen** genau an, was passiert ist und was zu tun ist. Sie meldet sich nicht von selbst neu an.
- Wartungsarbeiten bei KitaPlus werden erkannt und nicht als Passwortfehler gewertet.
- Das Abfrageintervall ist einstellbar (Standard 30 Minuten, **mindestens 15**), um die Server zu schonen.

## Datenschutz und Sicherheit

- Gespeichert werden in Home Assistant nur deine **E-Mail-Adresse** und das **Refresh-Token**. Das **Passwort wird nie gespeichert**.
- Es werden keine Daten an Dritte gesendet. Die Integration spricht ausschließlich mit `eappbroker.kitaplus.de` über HTTPS.
- Daten, die nicht gebraucht werden (Kontakte, Adressen, Geburtsdaten, Dokumente), werden sofort nach dem Abruf verworfen und weder gespeichert noch angezeigt.
- Die **Diagnostics-Datei** schwärzt Namen, Texte, Token und Bankdaten. Prüfe sie trotzdem, bevor du sie in einem Issue teilst.
- Schwachstellen bitte privat melden, siehe [SECURITY.md](SECURITY.md).

## Beispiel: Erinnerung, wenn morgen nichts bestellt ist

```yaml
automation:
  - alias: "Kita: Essen bestellen"
    triggers:
      - trigger: time
        at: "18:00:00"
    conditions:
      - condition: state
        entity_id: binary_sensor.kind_morgen_nicht_bestellt
        state: "on"
    actions:
      - action: notify.notify
        data:
          message: "Für morgen ist kein Essen bestellt."
```

Die Entity-IDs hängen vom Namen deines Kindes ab. Prüfe sie unter Einstellungen → Entitäten.

## Bekannte Einschränkungen
- Nur lesend (v0.1). Geplant für v2: Krankmeldung sowie Essen bestellen und abbestellen, jeweils mit eindeutiger Rückmeldung über Erfolg oder Fehler.
- „Postfach“ zählt alle Nachrichten, nicht nur ungelesene.
- Gastkinder und mehrere Einrichtungen sind nicht getestet.

## Entwicklung

```bash
uv venv --python 3.13
uv pip install pytest-homeassistant-custom-component aioresponses ruff
.venv/bin/python -m pytest
```

Die Tests laufen ausschließlich mit **anonymisierten** Beispieldaten (`tests/fixtures`) und machen **keine Netzwerkzugriffe**. Rohdaten gehören nie ins Repository; `docs/_raw/` ist per `.gitignore` ausgeschlossen. `scripts/anonymize_fixtures.py` erzeugt die Fixtures. API-Notizen stehen in [docs/api.md](docs/api.md).

### Neue Version veröffentlichen
```bash
python3 scripts/bump_version.py 0.2.0        # setzt die Version in manifest.json
# CHANGELOG.md ergänzen, committen und pushen, dann:
git tag v0.2.0 && git push origin v0.2.0     # startet .github/workflows/release.yml
```
Der Workflow prüft, dass Tag und `manifest.json` übereinstimmen, lässt die Tests laufen, baut `kitaplus.zip` und erstellt das GitHub-Release. Erst damit erscheint das Update in HACS.

## Lizenz
[MIT](LICENSE)

---

*English summary:* Unofficial, read-only Home Assistant integration for the kitaplus parent app. It uses the app's own endpoints, which can change at any time. Sign-in is one attempt per submit, stops after two failures, shows KitaPlus' own message, and never stores your password. Use at your own risk.
