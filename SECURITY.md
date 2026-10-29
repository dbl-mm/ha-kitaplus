# Sicherheit

## Schwachstelle melden
Bitte nutze **GitHub → Security → „Report a vulnerability“** (privat). Eröffne dafür kein öffentliches Issue.

## Bitte niemals posten
In Issues, Logs oder Diagnostics-Dateien dürfen **nie** stehen: Passwörter, Tokens (`Authorization`, `refresh_token`),
Namen von Kindern oder Eltern, E-Mail-Adressen, IBAN, Telefonnummern oder echte Antworten der KitaPlus-API.
Die Diagnostics-Datei der Integration schwärzt diese Daten, prüfe sie trotzdem vor dem Hochladen.

## Was die Integration speichert
- E-Mail-Adresse und das Refresh-Token von KitaPlus in den Home-Assistant-Konfigurationsdaten (`.storage`).
- Das **Passwort wird nie gespeichert**. Es wird nur während der Anmeldung im Arbeitsspeicher gehalten.
- Es werden keine Daten an Dritte gesendet. Die einzige Gegenstelle ist `eappbroker.kitaplus.de` über HTTPS.
