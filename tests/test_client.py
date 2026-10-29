import base64
import json
import time

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.kitaplus.api.client import KitaPlusClient, Tokens
from custom_components.kitaplus.api.exceptions import (
    KitaPlusApiError,
    KitaPlusAuthError,
    KitaPlusConnectionError,
    KitaPlusMaintenanceError,
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


# ---- error paths: every one of them must end in the right exception, never in a wrong "password" verdict


async def test_login_during_maintenance_is_not_a_credentials_error(client):
    with aioresponses() as m:
        m.post(
            f"{API_BASE_URL}/app/login_check",
            status=503,
            payload={"isWartungAktiv": True, "message": "Wartung"},
        )
        with pytest.raises(KitaPlusMaintenanceError):
            await client.async_login("a@b.de", "pw")


async def test_login_network_error_is_a_connection_error(client):
    with aioresponses() as m:
        m.post(f"{API_BASE_URL}/app/login_check", exception=aiohttp.ClientConnectionError("down"))
        with pytest.raises(KitaPlusConnectionError):
            await client.async_login("a@b.de", "pw")


async def test_login_answer_without_token_is_an_api_error(client):
    with aioresponses() as m:
        m.post(f"{API_BASE_URL}/app/login_check", payload={"success": True})
        with pytest.raises(KitaPlusApiError):
            await client.async_login("a@b.de", "pw")


async def test_login_with_a_non_json_answer_is_not_a_wrong_password(client):
    with aioresponses() as m:
        m.post(f"{API_BASE_URL}/app/login_check", status=200, body="<html>oops</html>")
        with pytest.raises(KitaPlusApiError):
            await client.async_login("a@b.de", "pw")


async def test_refresh_errors_are_classified(client):
    client.set_tokens(Tokens("", "r", time.time() + 3600))
    for status, expected in (
        (401, KitaPlusAuthError),
        (503, KitaPlusConnectionError),
        (200, KitaPlusApiError),
    ):
        with aioresponses() as m:
            m.post(f"{API_BASE_URL}/app/refresh_token", status=status, payload={})
            with pytest.raises(expected):
                await client.async_get_board()


async def test_requests_without_a_session_ask_for_a_login(client):
    with pytest.raises(KitaPlusAuthError):
        await client.async_get_board()


async def _logged_in(client, m):
    m.post(f"{API_BASE_URL}/app/login_check", payload=_ok())
    await client.async_login("a@b.de", "pw")


async def test_get_errors_are_classified(client):
    url = f"{API_BASE_URL}/orga_nachrichten/index?limit=15&page=1&start=0"
    cases = (
        (dict(status=503, payload={"isWartungAktiv": True}), KitaPlusMaintenanceError),
        (dict(status=403, payload={"message": "no"}), KitaPlusAuthError),
        (dict(status=404, payload={}), KitaPlusApiError),
        (dict(status=200, payload={"success": False}), KitaPlusApiError),
        (dict(status=200, payload=[1, 2]), KitaPlusApiError),
        (dict(exception=aiohttp.ClientConnectionError("down")), KitaPlusConnectionError),
    )
    for reply, expected in cases:
        with aioresponses() as m:
            await _logged_in(client, m)
            m.get(url, **reply)
            with pytest.raises(expected):
                await client.async_get_board()


async def test_all_read_endpoints_return_their_payload(client):
    with aioresponses() as m:
        await _logged_in(client, m)
        m.get(
            f"{API_BASE_URL}/nachrichten/getNachrichten?limit=15&page=1&start=0",
            payload={"success": True, "data": [1]},
        )
        m.get(f"{API_BASE_URL}/vpp/verpflegungskonten", payload={"success": True, "data": [2]})
        m.get(
            f"{API_BASE_URL}/termin/getTermine?limit=100&month=6&openEnd=1&page=1&start=0&year=2026",
            payload={"success": True, "data": [3]},
        )
        meals = {"success": True, "data": [{"tage": [{"datum": "2026-06-13T00:00:00"}]}]}
        m.get(
            f"{API_BASE_URL}/vpp/bestelldaten?elternkontoId=7&enddatum=2026-06-27&ignoriereSchliesstage=1"
            "&kindId=1&startdatum=2026-06-13",
            payload=meals,
        )
        m.get(
            f"{API_BASE_URL}/vpp/bestelldaten?elternkontoId=7&enddatum=2026-06-27&ignoriereSchliesstage=1"
            "&kindId=2&startdatum=2026-06-13",
            payload={"success": True, "data": []},
        )
        assert await client.async_get_messages() == [1]
        assert await client.async_get_accounts() == [2]
        assert await client.async_get_events(2026, 6) == [3]
        assert await client.async_get_meals(1, 7, "2026-06-13", "2026-06-27") == [
            {"datum": "2026-06-13T00:00:00"}
        ]
        assert await client.async_get_meals(2, 7, "2026-06-13", "2026-06-27") == []
