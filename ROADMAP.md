# Roadmap

Was als Nächstes denkbar ist. Die Liste ist eine Absicht, kein Versprechen: Die Schnittstelle von KitaPlus ist
nicht öffentlich, und alles, was schreibt, wird nur mit großer Vorsicht gebaut. Jeder Punkt hat ein
[Issue](https://github.com/dbl-mm/ha-kitaplus/issues?q=label%3Aroadmap), dort kannst du mitreden.

## Als Nächstes

- **Dashboard-Assistent.** Die Integration erzeugt das Dashboard-YAML mit den echten Kindern und Entity-IDs,
  sodass `KIND` und `kind` nicht mehr ersetzt werden müssen (Aktion `kitaplus.dashboard_yaml`). Danach ein Hinweis
  nach der Einrichtung. Ein automatisches Anlegen des Dashboards nur auf ausdrücklichen Wunsch.
- **Echte Screenshots** statt der Entwurfsbilder im README und im Wiki.
- **Bestellfrist automatisch lesen.** Die Frist der Kita steht bei KitaPlus nur als Text. Mit einem Beispiel der
  Antwort von `/vpp/einrichtungen/index` ließe sie sich einlesen, ohne dass man sie einträgt.

## Später

- **Schreibende Funktionen (Version 2):** Essen bestellen und abbestellen, Krankmeldung und Abwesenheit. Jede
  Aktion meldet Erfolg oder Fehler **eindeutig** zurück, und es wird nur gehandelt, solange KitaPlus die Mahlzeit
  als bestellbar meldet.
- **Fristen genauer:** Feiertage bei der Frist berücksichtigen, die Werktage-Regel für das Montagsessen mit
  Erfahrungen aus der Praxis prüfen.
- **Speiseplan:** Die Gerichte stehen bei vielen Kitas nur in einer PDF. Aktuell zeigt das Dashboard den Namen des
  Anhangs und öffnet ihn. Ob sich die Gerichte zuverlässig auslesen lassen, ist offen.
- **Mehrere Einrichtungen, Gastkinder und weitere Kitas testen.** Bisher getestet: ein Konto, eine Einrichtung,
  ein Kind.
- **Englische Dokumentation** (README und Wiki).

## Von außen abhängig

- **Aufnahme in die HACS-Standardliste:** Der
  [Pull Request](https://github.com/hacs/default/pull/12968) wartet auf die Prüfung durch das HACS-Team.
- **Icon in der HACS-Liste:** HACS zeigt für eigene Integrationen noch einen Platzhalter, obwohl der
  `brand/`-Ordner stimmt. Laut HACS-Team behebt der „Marketplace“ ab Home Assistant 2026.11 das
  ([hacs/integration#5402](https://github.com/hacs/integration/issues/5402)). Danach prüfen wir es erneut.

## Bewusst nicht geplant

- **Zusatzkarten** (HACS-Frontend) für die Dashboards. Die Vorlagen nutzen nur eingebaute Karten, damit nichts
  nachinstalliert werden muss.
- **Passwort speichern.** Die Anmeldung bleibt ohne gespeichertes Passwort, und die Integration meldet sich nie
  selbstständig erneut an.
- **Aufnahme in den Home-Assistant-Core.** Das Projekt bleibt eine HACS-Integration.
