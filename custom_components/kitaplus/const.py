"""Constants for the KitaPlus integration."""

from datetime import timedelta

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
UPDATE_INTERVAL = timedelta(minutes=DEFAULT_SCAN_INTERVAL)

EVENT_NEW_BOARD_POST = f"{DOMAIN}_new_board_post"
EVENT_NEW_MESSAGE = f"{DOMAIN}_new_message"

# A config flow stops after this many failed logins so nobody locks the account by trial and error.
MAX_LOGIN_ATTEMPTS = 2
# After that many failed attempts new ones are paused, even across restarted flows.
LOGIN_COOLDOWN_MINUTES = 15

MANUFACTURER = "kitaplus"
CONFIGURATION_URL = "https://eltern.kitaplus.de"
