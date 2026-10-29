"""Exceptions raised by the KitaPlus API client."""

from __future__ import annotations

import re

_LOCK_HINT = re.compile(r"gesperrt|blocked|locked|sperr", re.IGNORECASE)


class KitaPlusError(Exception):
    """Base error."""


class KitaPlusAuthError(KitaPlusError):
    """Credentials are invalid or the session has expired. Never retry automatically.

    `server_message` is the text KitaPlus itself sent, shown to the user unchanged.
    `locked` is True when that text says the account is blocked.
    """

    def __init__(self, message: str | None = None, server_message: str | None = None) -> None:
        super().__init__(message or server_message or "Authentication failed")
        self.server_message = server_message
        self.locked = bool(server_message and _LOCK_HINT.search(server_message))


class KitaPlusTwoFactorRequired(KitaPlusError):
    """The account needs a second factor. method: 1 = authenticator app, 2 = e-mail code."""

    def __init__(self, method: int | None = None) -> None:
        super().__init__("Two-factor code required")
        self.method = method


class KitaPlusConnectionError(KitaPlusError):
    """The service could not be reached."""


class KitaPlusMaintenanceError(KitaPlusConnectionError):
    """KitaPlus reports maintenance. This is NOT a credentials problem."""


class KitaPlusApiError(KitaPlusError):
    """The service returned an unexpected response."""
