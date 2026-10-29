"""Async client for the KitaPlus parent API (reverse engineered, read only).

Auth flow (see docs/api.md): POST /app/login_check once, then renew with
POST /app/refresh_token. A failed login is NEVER retried, the account has a
login attempt counter.
"""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Callable
from dataclasses import dataclass

import aiohttp

from ..const import API_BASE_URL
from .exceptions import (
    KitaPlusApiError,
    KitaPlusAuthError,
    KitaPlusConnectionError,
    KitaPlusMaintenanceError,
    KitaPlusTwoFactorRequired,
)

_TIMEOUT = aiohttp.ClientTimeout(total=30)
_REFRESH_MARGIN = 60  # seconds before JWT expiry


@dataclass
class Tokens:
    """JWT plus refresh token."""

    jwt: str
    refresh_token: str
    refresh_expires: float  # epoch seconds


def _jwt_exp(jwt: str) -> float:
    """Expiry of a JWT. A missing or malformed token counts as already expired."""
    try:
        payload = jwt.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except (IndexError, KeyError, TypeError, ValueError):
        return 0.0


class KitaPlusClient:
    """Talk to eappbroker.kitaplus.de."""

    def __init__(self, session: aiohttp.ClientSession, client_id: str) -> None:
        self._session = session
        self._client_id = client_id
        self._tokens: Tokens | None = None
        self._on_tokens: Callable[[Tokens], None] | None = None

    def set_token_listener(self, listener: Callable[[Tokens], None] | None) -> None:
        """Called right after every new token pair, so a rotated refresh token is saved at once."""
        self._on_tokens = listener

    @property
    def tokens(self) -> Tokens | None:
        return self._tokens

    def set_tokens(self, tokens: Tokens | None) -> None:
        self._tokens = tokens

    def _client_info(self) -> dict:
        # Fixed identity so that Home Assistant shows up as ONE device.
        return {
            "userAgent": "HomeAssistant-KitaPlus",
            "geraetTyp": "desktop",
            "geraet": "Home Assistant",
            "browser": "HomeAssistant",
            "os": "Home Assistant",
            "browserFingerprint": self._client_id,
            "features": "{}",
        }

    def _store(self, data: dict) -> None:
        previous = self._tokens
        expires = data.get("refresh_token_expiration")
        if expires:
            refresh_expires = float(expires)
        elif previous is not None:
            refresh_expires = previous.refresh_expires  # do not invent a shorter lifetime
        else:
            refresh_expires = time.time() + 86400
        self._tokens = Tokens(
            jwt=data["token"],
            refresh_token=data.get("refresh_token") or (previous.refresh_token if previous else ""),
            refresh_expires=refresh_expires,
        )
        if self._on_tokens is not None:
            self._on_tokens(self._tokens)

    async def _post(self, path: str, **kwargs) -> tuple[int, dict]:
        try:
            async with self._session.post(f"{API_BASE_URL}{path}", timeout=_TIMEOUT, **kwargs) as resp:
                try:
                    body = await resp.json(content_type=None)
                except (aiohttp.ContentTypeError, json.JSONDecodeError):
                    body = {}
                return resp.status, body if isinstance(body, dict) else {}
        except (aiohttp.ClientError, TimeoutError) as err:
            raise KitaPlusConnectionError(str(err)) from err

    async def async_login(self, email: str, password: str, auth_code: str | None = None) -> None:
        """Log in once. Raises KitaPlusAuthError without retrying."""
        status, body = await self._post(
            "/app/login_check",
            json={
                "username": email.strip(),
                "password": password,
                "rememberMe": True,
                "authCode": auth_code,
                "clientInfo": self._client_info(),
            },
        )
        if body.get("isWartungAktiv"):
            raise KitaPlusMaintenanceError(body.get("message") or "KitaPlus maintenance")
        if status >= 500 or status == 429:
            # A gateway error or rate limit says nothing about the credentials.
            raise KitaPlusConnectionError(f"KitaPlus answered with HTTP {status}")
        if body.get("twoFaRequired"):
            raise KitaPlusTwoFactorRequired(body.get("twoFaMethod"))
        if status in (400, 401, 403, 422) or body.get("success") is False:
            raise KitaPlusAuthError("Login rejected", server_message=body.get("message"))
        if "token" not in body:
            raise KitaPlusApiError("Login response without token")
        self._store(body)

    async def _async_refresh(self) -> None:
        if self._tokens is None or self._tokens.refresh_expires < time.time():
            raise KitaPlusAuthError("Refresh token expired")
        status, body = await self._post(
            "/app/refresh_token",
            data={
                "refresh_token": self._tokens.refresh_token,
                "rememberMe": "true",
                "withUser": "false",
                "clientInfo": json.dumps(self._client_info()),
            },
        )
        if status in (401, 403):
            raise KitaPlusAuthError("Refresh rejected", server_message=body.get("message"))
        if status >= 500 or status == 429:
            raise KitaPlusConnectionError(f"KitaPlus answered with HTTP {status}")
        if status != 200 or "token" not in body:
            raise KitaPlusApiError(f"Refresh failed ({status})")
        self._store(body)

    async def _async_headers(self) -> dict[str, str]:
        if self._tokens is None:
            raise KitaPlusAuthError("Not logged in")
        if _jwt_exp(self._tokens.jwt) - time.time() < _REFRESH_MARGIN:
            await self._async_refresh()
        return {
            "Authorization": f"Bearer {self._tokens.jwt}",
            "X-Requested-With": "XMLHttpRequest",
        }

    async def _get(self, path: str, **params: str | int) -> dict:
        headers = await self._async_headers()
        try:
            async with self._session.get(
                f"{API_BASE_URL}{path}", params=params, headers=headers, timeout=_TIMEOUT
            ) as resp:
                if resp.status >= 400:
                    body = await resp.json(content_type=None) if resp.content_length else {}
                    if isinstance(body, dict) and body.get("isWartungAktiv"):
                        raise KitaPlusMaintenanceError("KitaPlus maintenance")
                    if resp.status in (401, 403):
                        raise KitaPlusAuthError(
                            "Token rejected",
                            server_message=body.get("message") if isinstance(body, dict) else None,
                        )
                    raise KitaPlusApiError(f"{path} returned {resp.status}")
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise KitaPlusConnectionError(str(err)) from err
        if not isinstance(data, dict) or not data.get("success", True):
            raise KitaPlusApiError(f"Unsuccessful response for {path}")
        return data

    async def async_get_board(self, limit: int = 15) -> list[dict]:
        return (await self._get("/orga_nachrichten/index", page=1, start=0, limit=limit))["data"]

    async def async_get_messages(self, limit: int = 15) -> list[dict]:
        return (await self._get("/nachrichten/getNachrichten", page=1, start=0, limit=limit))["data"]

    async def async_get_accounts(self) -> list[dict]:
        return (await self._get("/vpp/verpflegungskonten"))["data"]

    async def async_get_children(self) -> list[dict]:
        """Children, reduced to what the integration needs.

        The endpoint also returns contacts, addresses and birth dates. They are
        dropped here, before the data leaves the client.
        """
        return [
            {
                "id": kind["id"],
                "vorname": kind.get("vorname"),
                "istVppAktiv": bool(kind.get("istVppAktiv")),
                "elternkonto": {"id": (kind.get("elternkonto") or {}).get("id")},
            }
            for kind in (await self._get("/benutzer/get_einrichtungen_kinder"))["kinder"]
        ]

    async def async_get_events(self, year: int, month: int) -> list[dict]:
        data = await self._get(
            "/termin/getTermine", month=month, year=year, openEnd=1, page=1, start=0, limit=100
        )
        return data["data"]

    async def async_get_meals(
        self, child_id: int, parent_account_id: int, start: str, end: str
    ) -> list[dict]:
        """Meal plan and orders per day, dates as YYYY-MM-DD."""
        data = await self._get(
            "/vpp/bestelldaten",
            kindId=child_id,
            elternkontoId=parent_account_id,
            startdatum=start,
            enddatum=end,
            ignoriereSchliesstage=1,
        )
        rows = data.get("data") or []
        return rows[0].get("tage", []) if rows else []
