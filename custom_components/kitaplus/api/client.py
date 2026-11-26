"""Async client for the KitaPlus parent API (reverse engineered, read only).

Auth flow (see docs/api.md): POST /app/login_check once, then renew with
POST /app/refresh_token. A failed login is NEVER retried, the account has a
login attempt counter.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

import aiohttp

from ..const import API_BASE_URL
from .exceptions import (
    KitaPlusApiError,
    KitaPlusAuthError,
    KitaPlusConnectionError,
    KitaPlusMaintenanceError,
    KitaPlusTwoFactorRequired,
)
from .models import Account, BoardPost, Child, Contact, Day, Event, Hours, Message, OrderRules

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


_WEEKDAYS = ("montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag")


def _clock(value: Any) -> str | None:
    """ "HH:MM" from KitaPlus' "1970-01-01T07:00:00"."""
    text = str(value or "")
    return text[11:16] if len(text) >= 16 and text[13] == ":" else None


def _opening_hours(facility: dict[str, Any]) -> list[Hours | None]:
    """Opening hours for Monday to Sunday. A day without hours is None (KitaPlus gives no weekend hours)."""
    raw = ((facility.get("currentStammdaten") or {}).get("einrichtungOeffnungszeiten")) or {}
    hours: list[Hours | None] = []
    for day in _WEEKDAYS:
        start, end = _clock(raw.get(f"{day}Von")), _clock(raw.get(f"{day}Bis"))
        hours.append(Hours(von=start, bis=end) if start and end else None)
    return hours


def _contacts(facility: dict[str, Any]) -> list[Contact]:
    """The facility's contact persons, in the order KitaPlus shows them."""
    people = sorted(facility.get("einrichtungAnsprechpartners") or [], key=lambda p: p.get("sortRank") or 0)
    contacts: list[Contact] = []
    for person in people:
        name = " ".join(str(person.get(k) or "").strip() for k in ("anrede", "vorname", "nachname")).strip()
        function = " ".join(str(person.get("funktion") or "").replace(",", " ").split())
        contact = Contact(
            name=" ".join(name.split()),
            funktion=function,
            telefon=str(person.get("telefon") or "").strip(),
            email=str(person.get("email") or "").strip(),
        )
        if contact["name"] or contact["telefon"] or contact["email"]:  # an empty entry says nothing
            contacts.append(contact)
    return contacts


class KitaPlusClient:
    """Talk to eappbroker.kitaplus.de."""

    def __init__(self, session: aiohttp.ClientSession, client_id: str) -> None:
        self._session = session
        self._client_id = client_id
        self._tokens: Tokens | None = None
        self._on_tokens: Callable[[Tokens], None] | None = None
        self._refresh_lock = asyncio.Lock()  # a refresh token is used by one request at a time

    def set_token_listener(self, listener: Callable[[Tokens], None] | None) -> None:
        """Called right after every new token pair, so a rotated refresh token is saved at once."""
        self._on_tokens = listener

    @property
    def tokens(self) -> Tokens | None:
        return self._tokens

    def set_tokens(self, tokens: Tokens | None) -> None:
        self._tokens = tokens

    def _client_info(self) -> dict[str, Any]:
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

    def _store(self, data: dict[str, Any]) -> None:
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

    async def _post(self, path: str, **kwargs: Any) -> tuple[int, dict[str, Any]]:
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

    async def _async_renew(self, stale_jwt: str) -> None:
        """Renew a JWT that is expired or was rejected, even if several requests need it at the same moment.

        KitaPlus may hand out a new refresh token with every renewal and then reject the old one. Two
        renewals with the same token would make the second one fail and look like a lost session, so they
        wait for each other, and the later one sees that the first has already replaced the JWT.
        """
        async with self._refresh_lock:
            if self._tokens is not None and self._tokens.jwt != stale_jwt:
                return
            await self._async_refresh()

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
            await self._async_renew(self._tokens.jwt)
        return {
            "Authorization": f"Bearer {self._tokens.jwt}",
            "X-Requested-With": "XMLHttpRequest",
        }

    async def _get(self, path: str, **params: str | int) -> dict[str, Any]:
        headers = await self._async_headers()  # a failing renewal is a lost session and ends here
        try:
            return await self._get_with(path, headers, params)
        except KitaPlusAuthError:
            # A JWT can be rejected while the refresh token still works (for example when the server
            # restarted). Renewing is not a login and does not count as a failed attempt, so try it once.
            await self._async_renew(headers["Authorization"].removeprefix("Bearer "))
            return await self._get_with(path, await self._async_headers(), params)

    async def _get_with(
        self, path: str, headers: dict[str, str], params: dict[str, str | int]
    ) -> dict[str, Any]:
        try:
            async with self._session.get(
                f"{API_BASE_URL}{path}", params=params, headers=headers, timeout=_TIMEOUT
            ) as resp:
                if resp.status >= 400:
                    try:  # content_length is unset for gzip/chunked answers, so just try to read it
                        body = await resp.json(content_type=None)
                    except (aiohttp.ClientError, ValueError):
                        body = {}
                    if not isinstance(body, dict):
                        body = {}
                    if body.get("isWartungAktiv"):
                        raise KitaPlusMaintenanceError("KitaPlus maintenance")
                    if resp.status in (401, 403):
                        raise KitaPlusAuthError("Token rejected", server_message=body.get("message"))
                    raise KitaPlusApiError(f"{path} returned {resp.status}")
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise KitaPlusConnectionError(str(err)) from err
        if not isinstance(data, dict) or not data.get("success", True):
            raise KitaPlusApiError(f"Unsuccessful response for {path}")
        return data

    async def async_get_board(self, limit: int = 15) -> list[BoardPost]:
        data = await self._get("/orga_nachrichten/index", page=1, start=0, limit=limit)
        return cast("list[BoardPost]", data["data"])

    async def async_get_messages(self, limit: int = 15) -> list[Message]:
        data = await self._get("/nachrichten/getNachrichten", page=1, start=0, limit=limit)
        return cast("list[Message]", data["data"])

    async def async_get_accounts(self) -> list[Account]:
        return cast("list[Account]", (await self._get("/vpp/verpflegungskonten"))["data"])

    async def async_get_account_id(self) -> int:
        """Stable id of the KitaPlus user. The rest of the (personal) answer is ignored."""
        return int((await self._get("/benutzer/get_own"))["data"]["id"])

    async def async_get_children(self, include_contacts: bool = False) -> list[Child]:
        """Children, reduced to what the integration needs.

        The endpoint also returns the children's contacts, addresses and birth dates. They are dropped here,
        before the data leaves the client. The facility's opening hours are kept. Its contact persons are
        kept only when `include_contacts` is set (an option the user has to switch on).
        """
        answer = await self._get("/benutzer/get_einrichtungen_kinder")
        children: list[Child] = []
        for kind in answer["kinder"]:
            account = kind.get("elternkonto") or {}
            facility = account.get("einrichtung") or {}
            child = Child(
                id=kind["id"],
                vorname=kind.get("vorname"),
                istVppAktiv=bool(kind.get("istVppAktiv")),
                elternkonto={"id": account.get("id")},
                oeffnungszeiten=_opening_hours(facility),
            )
            if include_contacts:
                child["ansprechpartner"] = _contacts(facility)
            children.append(child)
        return children

    async def async_get_order_rules(self) -> list[OrderRules]:
        """The order deadline texts of every facility, one entry each.

        The answer also holds help pages with contact details, an account balance notice and file ids.
        They are dropped here, before the data leaves the client.
        """
        data = await self._get("/vpp/einrichtungen/index")
        rules: list[OrderRules] = []
        for row in data.get("data") or []:
            settings = (row or {}).get("vppEinrichtungseinstellungen") or {}
            rules.append(
                OrderRules(
                    bestellfristEinzelText=settings.get("bestellfristEinzelText"),
                    fristSonstigesText=settings.get("fristSonstigesText"),
                )
            )
        return rules

    async def async_get_file(self, source: str, attachment_id: int, max_bytes: int) -> tuple[bytes, str, str]:
        """A file attached to a bulletin board post ("board") or a message ("message").

        Returns (content, MIME type, file name). The parent app uses these two calls and gets JSON with the
        file as Base64.
        """
        if source == "board":
            data = await self._get("/orga_nachrichten/get_file", orgAnhangId=attachment_id)
        else:
            data = await self._get("/nachrichten/get_file", anhangId=attachment_id)
        encoded = data.get("data")
        if not isinstance(encoded, str) or len(encoded) > max_bytes * 4 // 3 + 4:
            raise KitaPlusApiError("File missing or too large")
        try:
            content = base64.b64decode(encoded, validate=True)
        except ValueError as err:
            raise KitaPlusApiError("File is not valid Base64") from err
        return (
            content,
            str(data.get("type") or "application/octet-stream").lower(),
            str(data.get("filename") or ""),
        )

    async def async_get_events(self, year: int, month: int) -> list[Event]:
        data = await self._get(
            "/termin/getTermine", month=month, year=year, openEnd=1, page=1, start=0, limit=100
        )
        return cast("list[Event]", data["data"])

    async def async_get_meals(self, child_id: int, parent_account_id: int, start: str, end: str) -> list[Day]:
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
        return cast("list[Day]", rows[0].get("tage", [])) if rows else []
