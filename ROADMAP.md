# Roadmap

Was als Nächstes denkbar ist. Die Liste ist eine Absicht, kein Versprechen: Die Schnittstelle von KitaPlus ist
nicht öffentlich, und alles, was schreibt, wird nur mit großer Vorsicht gebaut. Mitreden kannst du in den
[Diskussionen](https://github.com/dbl-mm/ha-kitaplus/discussions), zu den Punkten unten gibt es dort je einen Beitrag. Fehler und
konkrete Probleme gehören weiterhin in die [Issues](https://github.com/dbl-mm/ha-kitaplus/issues).

## Als Nächstes

- **Dashboard automatisch anlegen.** Die Aktion „Dashboard erzeugen“ gibt es schon (nur das YAML zum Kopieren). Ein automatisches Anlegen des Dashboards in Home Assistant nur auf ausdrücklichen Wunsch.
- **Echte Screenshots** statt der Entwurfsbilder im README und im Wiki.

## Später

- **Schreibende Funktionen (Version 2):** Essen bestellen und abbestellen, Krankmeldung und Abwesenheit. Jede
  Aktion meldet Erfolg oder Fehler **eindeutig** zurück, und es wird nur gehandelt, solange KitaPlus die Mahlzeit
  als bestellbar meldet.
- **Fristen: Montagsessen mit Praxis prüfen.** KitaPlus verschiebt eine Frist vom Wochenende oder Feiertag auf den Werktag davor, die Integration rechnet das jetzt genauso. Offen ist nur, ob das am Montag, 09.11.2026, in der Praxis so aufgeht.
- **Speiseplan:** Die Gerichte stehen bei vielen Kitas nur in einer PDF. Aktuell zeigt das Dashboard den Namen des
  Anhangs und öffnet ihn. Ob sich die Gerichte zuverlässig auslesen lassen, ist offen.
- **Mehrere Einrichtungen, Gastkinder und weitere Kitas testen.** Bisher getestet: ein Konto, eine Einrichtung,
  ein Kind.
- **Englische Dokumentation:** README und Wiki gibt es jetzt auch auf Englisch ([README.en.md](README.en.md)). Offen: die Dateien in `docs/`.

## Bewusst nicht geplant

- **Zusatzkarten** (HACS-Frontend) für die Dashboards. Die Vorlagen nutzen nur eingebaute Karten, damit nichts
  nachinstalliert werden muss.
- **Passwort speichern.** Die Anmeldung bleibt ohne gespeichertes Passwort, und die Integration meldet sich nie
  selbstständig erneut an.
- **Aufnahme in den Home-Assistant-Core.** Das Projekt bleibt eine HACS-Integration.
