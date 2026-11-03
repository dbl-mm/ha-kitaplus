![KitaPlus logo](https://raw.githubusercontent.com/dbl-mm/ha-kitaplus/main/docs/img/logo-112.png)

# KitaPlus for Home Assistant

[Deutsche Version](README.md)

Unofficial Home Assistant integration for the **kitaplus parent app** (eltern.kitaplus.de), used by many German day-care centres (Kitas). It shows the bulletin board, the mailbox, appointments and closure days, the meal plan and orders, and the meal account balance in Home Assistant. The names of the entities and the Kita-specific terms follow the app, which is in German.

> **Important, please read**
> - This project is **not** made by kitaplus and has no connection to kitaplus or your Kita.
> - There is no public API. The integration uses the same endpoints as the parent app in the browser. It can **stop working at any time after a kitaplus update**.
> - You use it **at your own risk**. Check whether the terms of your Kita or of kitaplus allow this kind of use.
> - The integration is **read-only**. It never orders, books, cancels or reports anything.

**Jump to:** [Installation](#installation) · [Setup](#setup-and-sign-in) · [Order deadlines](#order-deadlines) · [Blueprints](#blueprints) · [Dashboard](#dashboard-templates) · [Help](#troubleshooting) · [Wiki (German)](https://github.com/dbl-mm/ha-kitaplus/wiki)

## Features

- **Bulletin board:** the newest title, the last 5 posts as attribute `posts`
- **Mailbox:** number of messages, the last 5 as attribute `messages`; **Pending replies**: messages that need a confirmation, with their deadline
- **Calendars:** **Appointments**, **Closures** (including public holidays) and, per child, **Ordered meals**; **Upcoming dates**: the next appointments and closures as a list (attribute `entries`)
- **Kita:** **Closed today**, **Closed tomorrow** (attribute `reason` names the cause, for example a bridge day; attribute `weekend` is true on Saturdays and Sundays, which KitaPlus does not list as closure days, so the state stays off then)
- **Meals:** per child **Meal today**, **Meal tomorrow**, **Order status today**, **Order status tomorrow** (ordered, open, deadline missed, no meal), **Next order deadline**, **Nothing ordered tomorrow**; per account **Meal account balance** (EUR)
- **Group:** per child the main group of the Kita as **Group**; project groups you pick in the options appear as attribute `project_groups`
- **Diagnostics:** **Session valid until** (disabled by default): how long the stored sign-in is valid
- **Events:** `kitaplus_new_board_post`, `kitaplus_new_message` (with `id` and `title`; not on the first poll), `kitaplus_order_deadline` (before the order deadline, see below)

Every child is its own device, plus one "KitaPlus" device for the account. New children appear without a restart (within 24 hours at the latest); children KitaPlus no longer lists are removed as devices.

**Supported:** parent accounts of the kitaplus parent app with e-mail and password, including two-factor (authenticator app or e-mail code). It was tested with one account, one facility and one child. **Not supported:** accounts that sign in with a passkey only, and any write function.

## Quick start

1. In HACS search for **KitaPlus**, download it and restart Home Assistant. (If it does not show up in the search yet: [Installation](#installation).)
2. **Settings → Devices & services → Add integration → KitaPlus** and sign in with your KitaPlus account (e-mail and password, plus the two-factor code if needed).
3. Under **Configure** enter **your Kita's order deadline** so that "deadline missed" and the reminders are right. [How](#order-deadlines).
4. Import a [blueprint](#blueprints) and add the [dashboard](#dashboard-templates).

## Installation

### HACS (recommended)
1. In HACS search for **KitaPlus** and download it.
2. Restart Home Assistant.
3. **Settings → Devices & services → Add integration → KitaPlus**.

If you cannot find KitaPlus in the search yet (new entries appear with a delay), add it as a **custom repository**: HACS → ⋮ → **Custom repositories** → `https://github.com/dbl-mm/ha-kitaplus`, category **Integration**.

### Manual
Copy the folder `custom_components/kitaplus` to `<config>/custom_components/kitaplus` and restart.

## Updates

HACS provides updates like for any other integration: it creates an **update entity**, Home Assistant shows the update under **Settings → System → Updates**, and you install it with one click. A **restart of Home Assistant** is needed afterwards. The stored sign-in stays, there is **no new sign-in** at KitaPlus.

> **Important: restart after every update.** Only after the restart the new code runs, and new entities (for example **Upcoming dates**) only appear then. If you do not see the update: in HACS choose **⋮ → Reload data** or **Redownload** on KitaPlus, select the version and restart Home Assistant. Which version runs is shown under *Settings → Devices & services → KitaPlus*.

What each version changes is listed in the [changelog](CHANGELOG.md) (German) and in the [GitHub releases](https://github.com/dbl-mm/ha-kitaplus/releases). Versions follow [SemVer](https://semver.org/).

## Setup and sign-in

Fields of the setup:

- **E-mail address**: the e-mail of your KitaPlus parent account. It is sent exactly as you type it.
- **Password**: your KitaPlus password. It is only used to sign in and **never stored**.
- **Code**: only if your account uses two-factor: the code from the authenticator app or the e-mail.

**Passkeys do not work.** If you only sign in with a passkey so far, set a password in the KitaPlus app as well.

**To protect your account:**
- Every click on "Submit" is **exactly one** sign-in attempt. There are no automatic retries.
- After **2 failed attempts** the setup stops and **pauses for 15 minutes**, even if you reopen the dialog. KitaPlus can lock accounts after too many failures, and **only the Kita management** can unlock them.
- The message from KitaPlus is shown unchanged, together with the counter ("failed attempt 1 of 2").
- Server errors or maintenance at KitaPlus are recognised and **not** counted as wrong passwords.
- If the session later expires or is rejected, **the integration stops polling** and shows exactly what happened under **Settings → Repairs**. It does not sign in again by itself.

### Options
**Settings → Devices & services → KitaPlus → Configure:**

- **Polling interval** (default: 30 minutes): how often Home Assistant asks KitaPlus (15 to 240 minutes). Less than 15 is not allowed, to be gentle on the servers.
- **Order deadline** (days before, time, weekdays only, reminder): see [Order deadlines](#order-deadlines).
- **Project groups to show:** pick which project groups (for example an age group) appear next to the main group. The list comes from your child's groups in KitaPlus. Project groups often include things like phone lists, so nothing is shown unless you choose it.
- **Experimental: read the dishes from the menu plan PDF** (default: off) and **Menu plan: word in the attachment name** (default: Menü): see [Dishes from the menu plan](#dishes-from-the-menu-plan-experimental).

### Reconfigure
**⋮ → Reconfigure** lets you sign in again or change the e-mail address. Only **the same KitaPlus account** is accepted; another account is rejected and nothing changes. The same protection rules as in the setup apply.

## Data updates

The integration polls KitaPlus at the set interval (default every 30 minutes). One run consists of a few read requests: appointments for this and next month, the meal plan of the next 14 days per child, bulletin board, mailbox and accounts. The list of children is reloaded only once a day. Before the first poll after a restart the access token is renewed with the stored refresh token, which needs **no password**.

"Today" and "tomorrow" values are recalculated at midnight without a new request.

## Order deadlines

Every Kita decides **until when** meals can be ordered or cancelled. Some say "1 day before the meal at 11:00", others "until 9:00 on the same day". KitaPlus only tells the time in the help text of the app, not as a number. The integration therefore works with **two pieces of information**:

1. **What KitaPlus reports:** for every meal the server says whether it can **still be ordered**.
2. **What you enter (recommended):** your Kita's deadline, once. Then everything is accurate to the minute.

The four states of the order status:

- **Ordered**: something is ordered.
- **Open**: there is a meal, nothing is ordered, and it can **still** be ordered.
- **Deadline missed**: there is a meal, nothing is ordered, and the deadline is **over**. This can no longer be changed.
- **No meal**: no meal is offered that day.

### Enter your Kita's deadline
The deadline is in the KitaPlus app under *Verpflegung → Hilfe → Bestellfristen*, for example:

> Order deadline (single orders): **1 day before the meal at 11:00**. Single orders for today (Thursday) must be placed by Wednesday 28.10.2026, 11:00 at the latest.

Enter it under *Settings → Devices & services → KitaPlus → Configure*:

- **Order deadline: days before the meal** (example: `1`): `0` means on the day itself. Leave it empty if you do not know it.
- **Order deadline: time** (example: `11:00`): the time ordering closes.
- **Count only weekdays** (example: off): switch on if your Kita does not count Saturdays and Sundays (a Monday meal then closes on Friday). The example sentence in the app on a Monday tells you.
- **Reminder before the deadline (minutes)** (example: `120`): how long before the deadline you are reminded. `0` turns the reminder off.

With the deadline entered:
- The **order status** switches to "deadline missed" **exactly at the deadline**, even if the last poll is older.
- The sensor **Next order deadline** shows when the next order closes.
- Before the deadline the integration fires the event `kitaplus_order_deadline`, but only if the day is still not ordered. It fetches **fresh data first**. The blueprint "Reminder shortly before the order deadline" turns this into a notification.
- Public holidays are not known to the integration. If your Kita counts them for the deadline, the status relies on what KitaPlus reports.

**Without a deadline** only what KitaPlus reports counts, which is as current as the last poll. The blueprint with fixed times therefore fetches fresh data before every reminder, and you set its time **well before** your deadline.

After a missed deadline the blueprints and the dashboard do **not** ask you to order. The integration **never orders or cancels by itself**. Future ordering functions may only act while KitaPlus reports the meal as orderable, and must report success or failure unambiguously.

**Event `kitaplus_order_deadline`:** `child`, `child_id`, `day`, `days_ahead`, `weekday` (0 = Monday), `deadline`, `minutes_left` and `fresh` (`false` if KitaPlus was not reachable and the last known state was used).

## Use cases

- **Never forget to order a meal:** remind yourself in the evening if **Nothing ordered tomorrow** is on.
- **Closure days:** do not wake anyone, or plan the childcare backup, when **Closed today** or **Closed tomorrow** is on.
- **News from the bulletin board or the mailbox:** send a phone notification from the event.
- **Keep an eye on the balance:** a notice when the **balance** falls below a value.
- **Family calendar:** **Appointments**, **Closures** and **Ordered meals** appear as calendars and can be shown on the dashboard.

## Examples

Reminder when nothing is ordered for tomorrow:
```yaml
automation:
  - alias: "Kita: order the meal"
    triggers:
      - trigger: time
        at: "18:00:00"
    conditions:
      - condition: state
        entity_id: sensor.child_order_status_tomorrow
        state: "open"
    actions:
      - action: notify.notify
        data:
          message: "No meal is ordered for tomorrow."
```

Notification for a new bulletin board post:
```yaml
automation:
  - alias: "Kita: new post"
    triggers:
      - trigger: event
        event_type: kitaplus_new_board_post
    actions:
      - action: notify.notify
        data:
          message: "Kita: {{ trigger.event.data.title }}"
```

Entity ids depend on your child's name. Check them under Settings → Entities.

## Blueprints

Ready-made automations: you only choose **what** you want to know and **how** you want to be notified (phone notification, speech output …). The button opens **your** Home Assistant and imports the blueprint; nothing is created before that. You pick the entities from a list. In Home Assistant they are called **"KitaPlus: …"**, like below. The blueprints themselves are in German.

**Which one do I need?** For most families **"Reminder shortly before the order deadline"** is enough. Everything else is optional.

### Ordering meals

- **Reminder shortly before the order deadline** *(recommended)*: a message shortly before ordering closes, but only if nothing is ordered. You set how much earlier (for example 2 hours). Enter your Kita's deadline once (see [Order deadlines](#order-deadlines)).
  **[Import into Home Assistant](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdbl-mm%2Fha-kitaplus%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fkitaplus%2Fbestellfrist_erinnerung.yaml)**

- **Reminder at fixed times**: the same with fixed times, for example every evening at 18:00 for tomorrow. Only needed if you do not want to enter a deadline.
  **[Import into Home Assistant](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdbl-mm%2Fha-kitaplus%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fkitaplus%2Fessen_erinnerung.yaml)**

### Messages

- **New message**: a notification for every new bulletin board post or mailbox message, optionally only for certain keywords.
  **[Import into Home Assistant](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdbl-mm%2Fha-kitaplus%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fkitaplus%2Fneue_mitteilung.yaml)**

- **Pending replies**: reminds you of messages you have to confirm or answer, with title and deadline.
  **[Import into Home Assistant](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdbl-mm%2Fha-kitaplus%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fkitaplus%2Frueckmeldung_erinnerung.yaml)**

### Kita and account

- **Closure day**: a notice the evening before that the Kita is closed tomorrow (with the reason). In the morning something can happen as well, for example the alarm is switched off.
  **[Import into Home Assistant](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdbl-mm%2Fha-kitaplus%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fkitaplus%2Fschliesstag.yaml)**

- **Low balance**: a warning when the meal balance falls below an amount.
  **[Import into Home Assistant](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdbl-mm%2Fha-kitaplus%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fkitaplus%2Fguthaben_niedrig.yaml)**

- **Daily briefing**: a single message in the morning with the essentials: closures, meals, pending replies, balance.
  **[Import into Home Assistant](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdbl-mm%2Fha-kitaplus%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fkitaplus%2Ftagesbriefing.yaml)**

- **Sign-in expires**: a notice a few days before you have to sign in to KitaPlus again.
  **[Import into Home Assistant](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdbl-mm%2Fha-kitaplus%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fkitaplus%2Fsitzung_laeuft_ab.yaml)**

More, including the available variables: [docs/blueprints.md](docs/blueprints.md) (German). If the button does not work for you (for example without [My Home Assistant](https://my.home-assistant.io/)): *Settings → Automations & scenes → Blueprints → Import blueprint* and paste the address of the file from [`blueprints/automation/kitaplus/`](blueprints/automation/kitaplus).

## Dashboard templates

A deliberately calm dashboard in the new sections layout, using built-in cards only, in German and English: **Heute** (today: one status card that says what matters, Kita, meals per child, board, mailbox, appointments, balance), **Wand** (wall tablet, three columns) and **Kalender** (calendar). There are also single cards to paste into your own dashboard. Setup in two minutes: [dashboards/README.md](dashboards/README.md) (German). The English files are `dashboards/kitaplus_en.yaml` and the cards in `dashboards/cards/en/`. In the files replace `KIND` with your child's name as shown in Home Assistant and `kind` with the same name in the entity ids (lower case, no umlauts).

## Dishes from the menu plan (experimental)

Many Kitas publish the meal plan only as a PDF on the bulletin board, while the order data of KitaPlus only says "Mittagessen" (lunch). With the option **Read the dishes from the menu plan PDF** (*Configure*) the integration reads each day's dish from that PDF. It is **off by default**.

- **What you get:** the sensors **Menu today** and **Menu tomorrow** (the dish, plus attributes `vegetarian` and `uncertain`). The meal card on the dashboard shows the dish instead of "Mittagessen", with the note "according to the menu plan PDF, no guarantee".
- **What is read:** PDFs with text content and a recognisable layout: a date range in the heading ("02.-06. November"), then one block per day with "Mo.", "Di." etc. and the dish, optionally with "( veg. )" for vegetarian. Photos or scans are not read.
- **Careful instead of guessing:** if the layout is not recognised nothing is shown. If a character cannot be read with certainty (some PDFs lose the "fl" in "Geflügel"), the name shows a question mark and the card asks you to check the plan.
- **Allergens** are **not** read or shown. Always rely on the original PDF for them (link on the dashboard under "Anhang").
- The PDF is only downloaded when a new attachment appears and processed in memory only. For this the integration needs the small library `pypdf`, which Home Assistant installs at startup.

## Attachments (for example the menu plan)

If a file is attached to a bulletin board post or a message (often the menu plan as a PDF), the dashboard shows "Anhang: …" as a link for the newest post. It opens the file in a new tab; the integration fetches it with your sign-in at KitaPlus. The links are **signed by Home Assistant and expire**, they are not permanent public addresses. PDFs and images are shown, other file types are only offered as a download. The names are also in the attribute `attachments` of the sensors **Bulletin board** and **Mailbox**.

## Troubleshooting

What you see and what it means:

- **Repair "Sign-in rejected"**: KitaPlus rejected the stored session. Check your password in the KitaPlus app and sign in once more via **⋮ → Reconfigure**. Do not try repeatedly.
- **Repair "Account locked"**: KitaPlus locked the account. Only the **Kita management** can unlock it. Home Assistant stops polling.
- **"Paused for 15 minutes"**: too many failed attempts. This protects your account. Check your credentials in the KitaPlus app and try again afterwards.
- **Message about maintenance**: not a password problem. Home Assistant retries later by itself.
- **"Unexpected response format"**: KitaPlus probably changed. Share the diagnostics file in an [issue](https://github.com/dbl-mm/ha-kitaplus/issues).
- **Entities "unavailable"**: the last poll failed (internet, maintenance). Look at the log; with the next successful poll they come back.
- **A new child is missing**: the list of children is refreshed daily. Reload the integration to refresh it immediately.
- **Sign-in with a passkey is not possible**: set a password in the KitaPlus app.

**Share a diagnostics file:** Settings → Devices & services → KitaPlus → ⋮ → **Download diagnostics**. Names, texts, ids, tokens and bank data are redacted. Check the file anyway before you upload it.

## Removal

1. **Settings → Devices & services → KitaPlus → ⋮ → Delete.** This removes all devices and entities.
2. In HACS: KitaPlus → ⋮ → **Remove**, then restart Home Assistant (or delete the folder `custom_components/kitaplus` for a manual installation).
3. The stored sign-in is deleted with the entry. If the KitaPlus app shows a device list for your account you can remove the "Home Assistant" entry there (not verified).

## Privacy and security

- Home Assistant stores only your **e-mail address**, the **account number** and the **refresh token**. The **password is never stored**.
- No data is sent to third parties. The integration talks only to `eappbroker.kitaplus.de` over HTTPS.
- Data that is not needed (contacts, addresses, birth dates, documents) is discarded right after the request and neither stored nor shown.
- The **diagnostics file** redacts names, texts, ids, tokens and bank data.
- Please report vulnerabilities privately, see [SECURITY.md](SECURITY.md).

## Known limitations
- Read-only. Planned: sick notes and ordering and cancelling meals, each with a clear success or failure message.
- "Mailbox" counts all messages, not only unread ones.
- Guest children and several facilities are untested.
- The interface is undocumented and can change without notice.
- New children appear on their own within 24 hours at the latest.

What may come next is in the [roadmap](https://github.com/dbl-mm/ha-kitaplus/blob/main/ROADMAP.md) (German).

## Quality level

By our own assessment the integration meets all rules of the [Home Assistant Quality Scale](https://www.home-assistant.io/docs/quality_scale/) up to **Platinum**. This is a **self-assessment**: Home Assistant only awards the levels to core integrations, this one is distributed through HACS only. Every rule is listed with status and reasoning in [`quality_scale.yaml`](custom_components/kitaplus/quality_scale.yaml). CI checks `mypy --strict`, 95 % coverage per module, hassfest and HACS on every change.

## Development

```bash
uv venv --python 3.13
uv pip install pytest-homeassistant-custom-component aioresponses pytest-cov mypy ruff
.venv/bin/python -m pytest
.venv/bin/mypy --strict custom_components/kitaplus
```

The tests run with **anonymised** sample data only (`tests/fixtures`) and make **no network requests**. Raw data never belongs in the repository; `docs/_raw/` is excluded by `.gitignore`. `scripts/anonymize_fixtures.py` creates the fixtures and `scripts/privacy_scan.py` checks before every commit that no real data is contained. Notes on the API are in [docs/api.md](docs/api.md).

## License
[MIT](LICENSE)
