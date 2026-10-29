# KitaPlus Eltern-API (reverse engineered, read only)

Frontend: https://eltern.kitaplus.de (PWA). API: https://eappbroker.kitaplus.de

## Auth (aus app.js gelesen, noch nicht live gegen die API getestet)

- Header: `Authorization: Bearer <JWT>` (keine Cookies), dazu `X-Requested-With: XMLHttpRequest`.
- Login: `POST /app/login_check` (JSON): `username`, `password` (Klartext, kein bcrypt im Request), `rememberMe`, `authCode` (TOTP, nur wenn 2FA aktiv), `clientInfo`.
  - Antwort bei Erfolg: `success: true`, `token` (JWT), `refresh_token`, `refresh_token_expiration`, `refresh_token_ttl`, `token_ttl`, `rememberMe`, `user`.
  - Antwort bei 2FA: `twoFaRequired: true`, `twoFaMethod` (TOTP) -> zweiter Aufruf mit `authCode`.
- Refresh: `POST /app/refresh_token` (form params): `refresh_token`, `rememberMe`, `withUser`, `clientInfo` (JSON-String), `appHash`. Die App erneuert das JWT, wenn es in weniger als 20 s abläuft. 401 = Sitzung abgelaufen -> neu einloggen.
- Logout: `POST /benutzer/logout`.
- `clientInfo`: userAgent, geraetTyp, geraet, browser, browserVersion, os, osVersion, cpu, browserFingerprint, features, appVersion, bildschirmBreite/-Hoehe. Das Gerät erscheint danach in `/benutzer/get_geraete`.
- Passkeys laufen getrennt über `/webauthn/auth/options` und `/webauthn/auth`. Nicht für HA nutzbar.

## Weitere bekannte Endpunkte
`/benutzer/get_own`, `/benutzer/get_einrichtungen_kinder`, `/benutzer/get_benutzereinrichtungen`, `/kind/istfreischaltungnotwendig`, `/kind/istvppfreischaltungdatumnotwendig`.
Responses: `{"success": bool, "data": [...], "total": n}`.

| Bereich | Endpoint | Params |
|---|---|---|
| Schwarzes Brett | GET /orga_nachrichten/index | page, start, limit |
| Postfach | GET /nachrichten/getNachrichten | page, start, limit |
| Kalender | GET /termin/getTermine | month, year, openEnd, page, start, limit |
| Abwesenheiten | GET /abwesenheitsmeldung/getAbwesenheitsmeldungen | page, start, limit |
| Verpflegung | TODO | |

Speiseplan scheint als PDF-Anhang im Schwarzen Brett zu kommen.

## Verpflegung (VPP) – aus app.js gelesen, nicht live getestet
| Zweck | Endpoint | Parameter / Felder |
|---|---|---|
| Konten + Kontostand | GET /vpp/verpflegungskonten | `data[]`: id, bezeichnung, **kontostand**, istGast, einrichtungId, bankkontoIban, ... |
| Speiseplan + Bestellungen | GET /vpp/bestelldaten | `kindId` (Gast: `vppKontoId`), `elternkontoId`, `startdatum`/`enddatum` (YYYY-MM-DD), `ignoriereSchliesstage` |
| Buchungen (Kontobewegungen) | GET /vpp/buchungen | Felder: id, betrag, datum, bestellDatum, kindId, bezeichnung, buchungsdatum |
| Essensplan als Datei | GET /vpp/einrichtungen/essensplan | `elternkontoId`, `woche`, `jahr` |
| Standardwochen | GET /vpp/standardwochen | |
| Bestellen (v2, nicht nutzen) | POST /vpp/bestellungen | `kindId`, `elternkontoId`, `bestellungen` (JSON), `pin` |

Bestellung-Felder: id, datum, istAbbestellt, bestellDatum, abbestellDatum, bezeichnung, preis, kindId, varianteId.
Der Speiseplan ist strukturiert (Gericht, Variante, MahlzeitArt) abrufbar, das PDF im Schwarzen Brett muss nicht geparst werden.

## Sperrschutz
Das Benutzermodell hat `loginVersuche` und `loginSperrdatum`. Der Client darf bei 401/403 oder falschen Zugangsdaten NIE automatisch erneut einloggen, sondern muss den Reauth-Flow auslösen.
