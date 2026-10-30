# Blueprints

Acht fertige Automationen für den Alltag. In Home Assistant heißen sie „KitaPlus: …“. Sie liegen im Ordner [`blueprints/automation/kitaplus/`](../blueprints/automation/kitaplus)
und werden **nicht** automatisch installiert, Home Assistant legt sie erst an, wenn du sie importierst.

**Version:** Am Ende der Beschreibung jedes Blueprints steht „Version X · benötigt KitaPlus ab Y · Home Assistant ab Z“. So siehst du, ob eine neuere Fassung existiert (dann „Neu importieren“) und welche Version der Integration du mindestens brauchst.

**Importieren:** Auf den Knopf im [README](../README.md#blueprints) klicken (öffnet deine Home-Assistant-Instanz), oder
*Einstellungen → Automatisierungen & Szenen → Blueprints → Blueprint importieren* und die Adresse der Datei einfügen.
Über „Neu importieren“ holst du später eine neuere Fassung. Danach wie üblich: *Automatisierung erstellen → Blueprint wählen*.

Alle Blueprints folgen denselben Regeln:
- Entities wählst du aus einer Liste, die nur KitaPlus-Entities zeigt. Entity-IDs musst du nicht kennen.
- Was passieren soll, wählst du selbst (**Aktion**). Voreingestellt ist eine Mitteilung über `notify.notify`. Du kannst jede
  andere Aktion nehmen (Push an ein Handy, Sprachausgabe, Licht …). In der Aktion stehen **Variablen** zur Verfügung (siehe unten).
- Selten Gebrauchtes steht im eingeklappten Abschnitt „Erweitert“.
- Erinnerungen laufen im Modus `single` und melden sich nicht doppelt.

## Welcher Blueprint wofür?

Die Kurzfassung mit Importknöpfen steht im [README](../README.md#blueprints). Hier die Dateien und was du in deiner eigenen Aktion verwenden kannst.

| Blueprint | Datei | Variablen in deiner Aktion |
|---|---|---|
| **Erinnerung kurz vor der Bestellfrist** | [`bestellfrist_erinnerung.yaml`](../blueprints/automation/kitaplus/bestellfrist_erinnerung.yaml) | `message`, `child`, `day`, `day_label`, `time_left`, `deadline_time`, `minutes_left`, `fresh` |
| **Erinnerung zu festen Uhrzeiten** | [`essen_erinnerung.yaml`](../blueprints/automation/kitaplus/essen_erinnerung.yaml) | `message`, `child`, `day`, `status`, `entity_id` |
| **Neue Mitteilung** | [`neue_mitteilung.yaml`](../blueprints/automation/kitaplus/neue_mitteilung.yaml) | `title`, `source`, `source_label`, `message` |
| **Offene Rückmeldungen** | [`rueckmeldung_erinnerung.yaml`](../blueprints/automation/kitaplus/rueckmeldung_erinnerung.yaml) | `count`, `titles`, `message` |
| **Schließtag** | [`schliesstag.yaml`](../blueprints/automation/kitaplus/schliesstag.yaml) | `message`, `reason`, `when` |
| **Niedriges Guthaben** | [`guthaben_niedrig.yaml`](../blueprints/automation/kitaplus/guthaben_niedrig.yaml) | `balance`, `threshold`, `message` |
| **Tagesbriefing** | [`tagesbriefing.yaml`](../blueprints/automation/kitaplus/tagesbriefing.yaml) | `message`, `lines` |
| **Anmeldung läuft ab** | [`sitzung_laeuft_ab.yaml`](../blueprints/automation/kitaplus/sitzung_laeuft_ab.yaml) | `days`, `message` |

**Was bedeutet „Variablen“?** Der Blueprint kennt zum Beispiel den fertigen Text der Nachricht. Wenn du als Aktion etwas anderes wählst,
kannst du ihn mit `{{ message }}` verwenden (siehe Beispiel unten).

## Bestellfristen berücksichtigen
**Am genauesten:** Trage die Frist deiner Kita bei der Integration ein (README, Abschnitt „Bestellfristen“) und nimm den Blueprint „Erinnerung kurz vor der Bestellfrist“. Er braucht keine Uhrzeit, der Zeitpunkt ergibt sich aus der Frist. Mit festen Uhrzeiten (Blueprint „Erinnerung zu festen Uhrzeiten“) gilt:

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
