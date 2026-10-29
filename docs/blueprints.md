# Blueprints

Acht fertige Automationen für den Alltag. Sie liegen im Ordner [`blueprints/automation/kitaplus/`](../blueprints/automation/kitaplus)
und werden **nicht** automatisch installiert, Home Assistant legt sie erst an, wenn du sie importierst.

**Importieren:** Auf den Knopf im [README](../README.md#blueprints) klicken (öffnet deine Home-Assistant-Instanz), oder
*Einstellungen → Automatisierungen & Szenen → Blueprints → Blueprint importieren* und die Adresse der Datei einfügen.
Über „Neu importieren“ holst du später eine neuere Fassung. Danach wie üblich: *Automatisierung erstellen → Blueprint wählen*.

Alle Blueprints folgen denselben Regeln:
- Entities wählst du aus einer Liste, die nur KitaPlus-Entities zeigt. Entity-IDs musst du nicht kennen.
- Was passieren soll, wählst du selbst (**Aktion**). Voreingestellt ist eine Mitteilung über `notify.notify`. Du kannst jede
  andere Aktion nehmen (Push an ein Handy, Sprachausgabe, Licht …). In der Aktion stehen **Variablen** zur Verfügung (siehe unten).
- Selten Gebrauchtes steht im eingeklappten Abschnitt „Erweitert“.
- Erinnerungen laufen im Modus `single` und melden sich nicht doppelt.

| Blueprint | Wann | Variablen für deine Aktion |
|---|---|---|
| [Erinnerung vor der Bestellfrist](../blueprints/automation/kitaplus/bestellfrist_erinnerung.yaml) | **kurz vor der Frist deiner Kita** (zum Beispiel 2 Stunden vorher), wenn noch nichts bestellt ist; die Frist trägst du einmal bei der Integration ein | `message`, `child`, `day`, `day_label`, `time_left`, `deadline_time`, `minutes_left`, `fresh` |
| [Essen-Erinnerung](../blueprints/automation/kitaplus/essen_erinnerung.yaml) | abends für morgen und auf Wunsch morgens als „letzte Chance“ für heute, **solange KitaPlus noch Bestellungen annimmt**; holt vorher frische Daten, meldet die verpasste Frist nur auf Wunsch | `message`, `child`, `day`, `status`, `entity_id` |
| [Schließtag](../blueprints/automation/kitaplus/schliesstag.yaml) | am Vorabend ein Hinweis, am Morgen des Schließtags optional eine Aktion (zum Beispiel Wecker aus) | `message`, `reason`, `when` |
| [Neue Mitteilung](../blueprints/automation/kitaplus/neue_mitteilung.yaml) | bei jedem neuen Beitrag am Schwarzen Brett oder neuer Nachricht, optional nur mit Stichwörtern | `title`, `source`, `source_label`, `message` |
| [Rückmeldung](../blueprints/automation/kitaplus/rueckmeldung_erinnerung.yaml) | sofort, wenn eine Rückmeldung nötig wird, und auf Wunsch täglich; mit Titel und Frist | `count`, `titles`, `message` |
| [Guthaben](../blueprints/automation/kitaplus/guthaben_niedrig.yaml) | wenn das Verpflegungs-Guthaben unter einen Betrag fällt, auf Wunsch täglich bis zum Aufladen | `balance`, `threshold`, `message` |
| [Sitzung läuft ab](../blueprints/automation/kitaplus/sitzung_laeuft_ab.yaml) | 1, 3 oder 7 Tage, bevor die gespeicherte Anmeldung abläuft | `days`, `message` |
| [Tagesbriefing](../blueprints/automation/kitaplus/tagesbriefing.yaml) | eine Zusammenfassung zur Uhrzeit: Schließtage, Essen, Rückmeldungen, Guthaben | `message`, `lines` |

## Bestellfristen berücksichtigen
**Am genauesten:** Trage die Frist deiner Kita bei der Integration ein (README, Abschnitt „Bestellfristen“) und nimm den Blueprint „Erinnerung vor der Bestellfrist“. Er braucht keine Uhrzeit, der Zeitpunkt ergibt sich aus der Frist. Mit festen Uhrzeiten (Blueprint „Essen-Erinnerung“) gilt:

Jede Kita setzt ihre eigene Frist (zum Beispiel „bis 9:00 Uhr am selben Tag“). Die Blueprints kennen die Uhrzeit nicht, sondern
verlassen sich auf den **Bestellstatus**, den KitaPlus liefert (*Offen* = noch bestellbar, *Frist verpasst* = zu spät, siehe
[README](../README.md#bestellfristen)). Deshalb:
- Stelle die Uhrzeit der Erinnerung **deutlich vor** deiner Frist ein (Frist: KitaPlus-App → *Verpflegung → Hilfe → Bestellfristen*).
- Bei Kitas mit Frist am selben Tag wähle unter „Letzte Chance“ die Sensoren *Bestellstatus heute* und eine Uhrzeit vor der Frist.
- Lass „Vor der Erinnerung frische Daten holen“ **eingeschaltet**. Sonst kann der Status bis zu ein Abfrageintervall alt sein.
- Ist die Frist verpasst, wird nicht zum Bestellen aufgefordert (auf Wunsch gibt es stattdessen eine Meldung).

## Eigene Aktion nutzen: Beispiel
Statt der Mitteilung die Küchenlampe blinken lassen und zusätzlich eine Sprachausgabe:
```yaml
- action: tts.speak
  target:
    entity_id: tts.home_assistant_cloud
  data:
    media_player_entity_id: media_player.kueche
    message: "{{ message }}"
- action: light.turn_on
  target:
    entity_id: light.kuechenlampe
  data:
    flash: long
```

## Hinweise
- **Sitzung läuft ab:** Der Sensor „Sitzung gültig bis“ ist standardmäßig ausgeschaltet. Erst unter *Einstellungen → Geräte & Dienste →
  KitaPlus → Entitäten* einschalten.
- **Neue Mitteilung** meldet erst, wenn die Integration das nächste Mal abfragt (Standard 30 Minuten) und nie beim allerersten
  Abruf nach einem Neustart.
- **Sprache:** Die Blueprints sind deutsch beschriftet, jede Beschreibung beginnt mit einem englischen Hinweis.
- **Getestet:** Jeder Blueprint hat automatische Tests mit Uhrzeit und Zuständen (`tests/test_blueprints.py`): Auslöser,
  Bedingungen, Variablen und „bleibt still, wenn nichts zu melden ist“.
