import base64
import json
import time

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.kitaplus.api.client import KitaPlusClient, Tokens
from custom_components.kitaplus.api.exceptions import (
    KitaPlusAuthError,
    KitaPlusConnectionError,
    KitaPlusTwoFactorRequired,
)
from custom_components.kitaplus.const import API_BASE_URL


def _jwt(exp: float) -> str:
    seg = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")  # noqa: E731
    return f"{seg({'alg': 'none'})}.{seg({'exp': exp})}.sig"


def _ok(exp_in=3600):
    return {
        "success": True,
        "token": _jwt(time.time() + exp_in),
        "refresh_token": "r1",
        "refresh_token_expiration": time.time() + 86400,
    }


@pytest.fixture
async def client():
    async with aiohttp.ClientSession() as session:
        yield KitaPlusClient(session, "cid")


async def test_login_stores_tokens(client):
    with aioresponses() as m:
        m.post(f"{API_BASE_URL}/app/login_check", payload=_ok())
        await client.async_login("a@b.de", "pw")
    assert client.tokens and client.tokens.refresh_token == "r1"


async def test_wrong_password_is_not_retried(client):
    with aioresponses() as m:
        m.post(f"{API_BASE_URL}/app/login_check", status=401, payload={"success": False})
        with pytest.raises(KitaPlusAuthError):
            await client.async_login("a@b.de", "bad")
        assert len(m.requests) == 1  # exactly one attempt


async def test_two_factor_is_signalled(client):
    with aioresponses() as m:
        m.post(f"{API_BASE_URL}/app/login_check", payload={"success": False, "twoFaRequired": True})
        with pytest.raises(KitaPlusTwoFactorRequired):
            await client.async_login("a@b.de", "pw")


async def test_expiring_jwt_is_refreshed_before_request(client):
    with aioresponses() as m:
        m.post(f"{API_BASE_URL}/app/login_check", payload=_ok(exp_in=10))
        m.post(f"{API_BASE_URL}/app/refresh_token", payload=_ok())
        m.get(
            f"{API_BASE_URL}/orga_nachrichten/index?limit=15&page=1&start=0",
            payload={"success": True, "data": []},
        )
        await client.async_login("a@b.de", "pw")
        assert await client.async_get_board() == []
        assert any("refresh_token" in str(k[1]) for k in m.requests)


async def test_rejected_token_raises_auth_error_without_relogin(client):
    with aioresponses() as m:
        m.post(f"{API_BASE_URL}/app/login_check", payload=_ok())
        m.get(f"{API_BASE_URL}/orga_nachrichten/index?limit=15&page=1&start=0", status=401)
        await client.async_login("a@b.de", "pw")
        with pytest.raises(KitaPlusAuthError):
            await client.async_get_board()
        assert sum(1 for k in m.requests if "login_check" in str(k[1])) == 1


async def test_children_are_reduced_to_the_minimum(client):
    raw = {
        "success": True,
        "kinder": [
            {
                "id": 1,
                "vorname": "Anna",
                "nachname": "Muster",
                "geburtsdatum": "2022-01-01T00:00:00",
                "istVppAktiv": True,
                "kindKontakte": [{"telefon": "123", "strasse": "x"}],
                "elternkonto": {"id": 7, "einrichtung": {}},
            }
        ],
    }
    with aioresponses() as m:
        m.post(f"{API_BASE_URL}/app/login_check", payload=_ok())
        m.get(f"{API_BASE_URL}/benutzer/get_einrichtungen_kinder", payload=raw)
        await client.async_login("a@b.de", "pw")
        children = await client.async_get_children()
    assert children == [{"id": 1, "vorname": "Anna", "istVppAktiv": True, "elternkonto": {"id": 7}}]


async def test_restored_session_without_jwt_refreshes_instead_of_crashing(client):
    """Regression: after a restart only the refresh token is stored (jwt is empty)."""
    client.set_tokens(Tokens("", "stored-refresh", time.time() + 3600))
    with aioresponses() as m:
        m.post(f"{API_BASE_URL}/app/refresh_token", payload=_ok())
        m.get(
            f"{API_BASE_URL}/orga_nachrichten/index?limit=15&page=1&start=0",
            payload={"success": True, "data": []},
        )
        assert await client.async_get_board() == []
        assert not any("login_check" in str(k[1]) for k in m.requests)  # never a password login


async def test_expired_refresh_token_means_auth_error_without_any_request(client):
    client.set_tokens(Tokens("", "old", time.time() - 10))
    with aioresponses() as m, pytest.raises(KitaPlusAuthError):
        await client.async_get_board()
    assert not m.requests


async def test_gateway_error_on_login_is_not_a_wrong_password(client):
    with aioresponses() as m:
        m.post(f"{API_BASE_URL}/app/login_check", status=502, body="<html>Bad Gateway</html>")
        with pytest.raises(KitaPlusConnectionError):
            await client.async_login("a@b.de", "pw")


async def test_rate_limit_on_login_is_not_a_wrong_password(client):
    with aioresponses() as m:
        m.post(f"{API_BASE_URL}/app/login_check", status=429, payload={})
        with pytest.raises(KitaPlusConnectionError):
            await client.async_login("a@b.de", "pw")


async def test_rotated_refresh_token_is_reported_immediately(client):
    saved = []
    client.set_token_listener(saved.append)
    with aioresponses() as m:
        m.post(f"{API_BASE_URL}/app/login_check", payload=_ok())
        await client.async_login("a@b.de", "pw")
    assert [t.refresh_token for t in saved] == ["r1"]


async def test_refresh_without_expiry_keeps_the_known_expiry(client):
    far = time.time() + 30 * 86400
    client.set_tokens(Tokens(_jwt(time.time() - 5), "old", far))
    answer = {"success": True, "token": _jwt(time.time() + 3600), "refresh_token": "new"}
    with aioresponses() as m:
        m.post(f"{API_BASE_URL}/app/refresh_token", payload=answer)
        m.get(
            f"{API_BASE_URL}/orga_nachrichten/index?limit=15&page=1&start=0",
            payload={"success": True, "data": []},
        )
        await client.async_get_board()
    assert client.tokens.refresh_token == "new"
    assert client.tokens.refresh_expires == far  # not shortened to 24 hours
