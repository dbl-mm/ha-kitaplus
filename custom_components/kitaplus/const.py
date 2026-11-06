"""Constants for the KitaPlus integration."""

DOMAIN = "kitaplus"

API_BASE_URL = "https://eappbroker.kitaplus.de"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_AUTH_CODE = "auth_code"
CONF_CLIENT_ID = "client_id"
CONF_ACCOUNT_ID = "account_id"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_REFRESH_EXPIRES = "refresh_expires"

CONF_SCAN_INTERVAL = "scan_interval"
# Be gentle with the service: nothing polls faster than MIN_SCAN_INTERVAL minutes.
DEFAULT_SCAN_INTERVAL = 30
MIN_SCAN_INTERVAL = 15
MAX_SCAN_INTERVAL = 240

EVENT_NEW_BOARD_POST = f"{DOMAIN}_new_board_post"
EVENT_NEW_MESSAGE = f"{DOMAIN}_new_message"

# A config flow stops after this many failed logins so nobody locks the account by trial and error.
MAX_LOGIN_ATTEMPTS = 2
# After that many failed attempts new ones are paused, even across restarted flows.
LOGIN_COOLDOWN_MINUTES = 15

MANUFACTURER = "kitaplus"
CONFIGURATION_URL = "https://eltern.kitaplus.de"

# The order deadline is set by each Kita. KitaPlus tells us per meal whether it can still be ordered and gives
# the rule ("1 day before at 11:00") as a sentence. The integration reads that sentence; what is entered in
# the options wins. The rule makes the status exact to the minute.
CONF_DEADLINE_DAYS = "order_deadline_days"
CONF_DEADLINE_TIME = "order_deadline_time"
CONF_DEADLINE_WORKDAYS = "order_deadline_workdays"
CONF_LEAD_MINUTES = "reminder_lead_minutes"
# Whether Saturdays and Sundays count as "Kita closed" (off by default: only closure days and holidays do).
CONF_WEEKEND_CLOSED = "weekend_closed"
WEEKEND_REASON = {"de": "Wochenende", "en": "Weekend"}
DEFAULT_DEADLINE_TIME = "11:00:00"
DEFAULT_LEAD_MINUTES = 120
MAX_DEADLINE_DAYS = 14
EVENT_ORDER_DEADLINE = f"{DOMAIN}_order_deadline"

# Action that builds a dashboard for the real children and entity ids.
SERVICE_DASHBOARD_YAML = "dashboard_yaml"
ATTR_CONFIG_ENTRY = "config_entry"
ATTR_LANGUAGE = "language"
# Set on a new entry so that the first setup shows the hint about the dashboard once.
CONF_DASHBOARD_HINT = "show_dashboard_hint"
