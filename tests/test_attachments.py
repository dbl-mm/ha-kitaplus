"""Attached files: only files of the latest data, signed addresses, safe response headers."""

from contextlib import ExitStack
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.kitaplus.api.exceptions import KitaPlusApiError
from custom_components.kitaplus.attachments import attachment_ids, signed_link

from .common import CLIENT, setup_integration

PDF = (b"%PDF-1.4 test", "application/pdf", "Menü plan?.pdf")


def post(files):
    return {"id": 1, "datum": "2026-10-28", "titel": "Mittagessen", "text": "", "anhaenge": files}


FILES = [{"id": 7, "name": "Menüplan", "istDateiVorhanden": True}]


async def open_file(hass, hass_client, path, answer=PDF, side_effect=None):
    with ExitStack() as stack:
        entry = await setup_integration(hass, stack, async_get_board=[post(FILES)])
        mock = stack.enter_context(
            patch(f"{CLIENT}.async_get_file", AsyncMock(return_value=answer, side_effect=side_effect))
        )
        client = await hass_client()
        response = await client.get(path.format(entry=entry.entry_id))
        return response, mock, entry


async def test_a_listed_file_is_delivered_inline_with_safe_headers(hass: HomeAssistant, hass_client) -> None:
    response, mock, _ = await open_file(hass, hass_client, "/api/kitaplus/attachment/{entry}/7")
    assert response.status == 200 and await response.read() == PDF[0]
    assert response.headers["Content-Type"].startswith("application/pdf")
    assert response.headers["Content-Disposition"] == 'inline; filename="Men_plan_.pdf"'
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "sandbox" in response.headers["Content-Security-Policy"]
    assert response.headers["Cache-Control"] == "private, no-store"
    mock.assert_awaited_once()


async def test_a_file_that_is_not_attached_to_anything_is_not_delivered(
    hass: HomeAssistant, hass_client
) -> None:
    response, mock, _ = await open_file(hass, hass_client, "/api/kitaplus/attachment/{entry}/8")
    assert response.status == 404
    mock.assert_not_awaited()  # KitaPlus is not even asked


async def test_an_unknown_entry_is_not_found(hass: HomeAssistant, hass_client) -> None:
    response, mock, _ = await open_file(hass, hass_client, "/api/kitaplus/attachment/nope/7")
    assert response.status == 404
    mock.assert_not_awaited()


async def test_other_file_types_are_only_offered_as_a_download(hass: HomeAssistant, hass_client) -> None:
    html = (b"<script>alert(1)</script>", "text/html", "x.html")
    response, _, _ = await open_file(hass, hass_client, "/api/kitaplus/attachment/{entry}/7", html)
    assert response.headers["Content-Type"].startswith("application/octet-stream")
    assert response.headers["Content-Disposition"].startswith("attachment;")


async def test_kitaplus_problems_give_a_clear_error(hass: HomeAssistant, hass_client) -> None:
    response, _, _ = await open_file(
        hass, hass_client, "/api/kitaplus/attachment/{entry}/7", side_effect=KitaPlusApiError("x")
    )
    assert response.status == 502


async def test_a_file_is_fetched_once_for_several_requests(hass: HomeAssistant, hass_client) -> None:
    with ExitStack() as stack:
        entry = await setup_integration(hass, stack, async_get_board=[post(FILES)])
        mock = stack.enter_context(patch(f"{CLIENT}.async_get_file", AsyncMock(return_value=PDF)))
        client = await hass_client()
        for _ in range(3):
            assert (await client.get(f"/api/kitaplus/attachment/{entry.entry_id}/7")).status == 200
    assert mock.await_count == 1


async def test_without_signature_or_login_nothing_is_delivered(
    hass: HomeAssistant, hass_client_no_auth
) -> None:
    with ExitStack() as stack:
        entry = await setup_integration(hass, stack, async_get_board=[post(FILES)])
        client = await hass_client_no_auth()
        assert (await client.get(f"/api/kitaplus/attachment/{entry.entry_id}/7")).status == 401


async def test_the_signed_address_works_without_a_login(hass: HomeAssistant, hass_client_no_auth) -> None:
    with ExitStack() as stack:
        entry = await setup_integration(hass, stack, async_get_board=[post(FILES)])
        stack.enter_context(patch(f"{CLIENT}.async_get_file", AsyncMock(return_value=PDF)))
        link = signed_link(hass, entry.entry_id, 7, timedelta(hours=1))
        assert link and link.startswith(f"/api/kitaplus/attachment/{entry.entry_id}/7?authSig=")
        client = await hass_client_no_auth()
        assert (await client.get(link)).status == 200
        assert (await client.get(link.replace("authSig=", "authSig=x"))).status == 401


async def test_the_sensors_carry_the_signed_links(hass: HomeAssistant) -> None:
    with ExitStack() as stack:
        entry = await setup_integration(hass, stack, async_get_board=[post(FILES)])
    state = hass.states.get("sensor.kitaplus_bulletin_board")
    attachment = state.attributes["posts"][0]["attachments"][0]
    assert attachment["name"] == "Menüplan"
    assert attachment["url"].startswith(f"/api/kitaplus/attachment/{entry.entry_id}/7?authSig=")


def test_only_files_of_the_latest_data_count() -> None:
    from custom_components.kitaplus.coordinator import KitaPlusData

    data = KitaPlusData(
        board=[post([{"id": 1}, {"name": "no id"}])],
        messages=[{"nachricht": {"anhaenge": [{"id": 2}]}}, {"nachricht": None}],
    )
    assert attachment_ids(data) == {1, 2}


@pytest.mark.parametrize("error", [ValueError, RuntimeError])
def test_a_failed_signature_gives_no_address(hass: HomeAssistant, error) -> None:
    with patch("custom_components.kitaplus.attachments.async_sign_path", side_effect=error):
        assert signed_link(hass, "e", 1, timedelta(hours=1)) is None


def test_the_file_cache_is_small_expires_and_can_be_emptied() -> None:
    from custom_components.kitaplus import attachments as att

    view = att.KitaPlusAttachmentView()
    one_mb = b"x" * 1024 * 1024
    for i in range(30):  # 30 MB offered, only 20 MB are kept, the oldest go first
        view._remember(("e", i), one_mb, "application/pdf", "f.pdf")
    assert sum(len(v[1]) for v in view._cache.values()) <= att.MAX_CACHE_BYTES
    assert ("e", 29) in view._cache and ("e", 0) not in view._cache
    view._remember(("e", 99), b"x" * (att.MAX_CACHE_BYTES + 1), "application/pdf", "big.pdf")
    assert ("e", 99) not in view._cache, "a file larger than the cache is never kept"
    view._remember(("other", 1), one_mb, "application/pdf", "g.pdf")
    view.forget("e")
    assert set(view._cache) == {("other", 1)}
    view.forget()
    assert view._cache == {}


async def test_unloading_the_entry_empties_its_cached_files(hass: HomeAssistant, hass_client) -> None:
    with ExitStack() as stack:
        entry = await setup_integration(hass, stack, async_get_board=[post(FILES)])
        stack.enter_context(patch(f"{CLIENT}.async_get_file", AsyncMock(return_value=PDF)))
        client = await hass_client()
        assert (await client.get(f"/api/kitaplus/attachment/{entry.entry_id}/7")).status == 200
        view = hass.data["kitaplus_view"]
        assert view._cache
        await hass.config_entries.async_unload(entry.entry_id)
        assert not view._cache
