"""Open the files attached to posts (for example a meal plan PDF) from Home Assistant.

KitaPlus only hands out files to the signed-in app. The integration fetches a file with the stored login and
passes it on through a Home Assistant web address. Three rules keep that safe:

* only files attached to a post or message in the latest data can be fetched (not any id a visitor tries),
* the address is signed by Home Assistant and expires, so it is no permanent public link,
* the answer carries headers that stop a browser from running anything inside the file.
"""

from __future__ import annotations

import asyncio
import re
import time
from datetime import timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING

from aiohttp import web
from homeassistant.components.http import HomeAssistantView  # type: ignore[attr-defined]
from homeassistant.components.http.auth import async_sign_path

from .api.exceptions import KitaPlusError
from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import KitaPlusCoordinator, KitaPlusData

URL_BASE = "/api/kitaplus/attachment"
# Shown inline in the browser. Everything else is offered as a download, never opened.
INLINE_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/webp", "image/gif"}
MAX_BYTES = 15 * 1024 * 1024
CACHE_SECONDS = 600
# Files live only in memory (nothing is written to disk). The cache is small, expires, and is emptied when the
# integration is unloaded, so opening many files never fills up memory or storage.
MAX_CACHE_BYTES = 20 * 1024 * 1024
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def attachment_ids(data: KitaPlusData) -> set[int]:
    """Ids of the files that belong to a post or message in the latest data."""
    ids: set[int] = set()
    for post in data.board:
        ids.update(int(a["id"]) for a in post.get("anhaenge") or [] if a.get("id") is not None)
    for message in data.messages:
        note = message.get("nachricht") or {}
        ids.update(int(a["id"]) for a in note.get("anhaenge") or [] if a.get("id") is not None)
    return ids


def signed_link(hass: HomeAssistant, entry_id: str, attachment_id: int, lifetime: timedelta) -> str | None:
    """A signed, expiring address for one file, or None when Home Assistant cannot sign (no content user)."""
    try:
        path: str = async_sign_path(
            hass, f"{URL_BASE}/{entry_id}/{attachment_id}", lifetime, use_content_user=True
        )
    except (ValueError, RuntimeError):
        return None
    return path


class KitaPlusAttachmentView(HomeAssistantView):
    """GET /api/kitaplus/attachment/<entry id>/<file id>, signed by Home Assistant."""

    url = URL_BASE + "/{entry_id}/{attachment_id:[0-9]+}"
    name = "api:kitaplus:attachment"
    requires_auth = True

    def __init__(self) -> None:
        self._cache: dict[tuple[str, int], tuple[float, bytes, str, str]] = {}
        self._fetching = (
            asyncio.Lock()
        )  # one download at a time: at most one big file is held besides the cache

    def forget(self, entry_id: str | None = None) -> None:
        """Drop cached files of one entry (or all), for example when the entry is unloaded."""
        self._cache = {k: v for k, v in self._cache.items() if entry_id is not None and k[0] != entry_id}

    def _remember(self, key: tuple[str, int], content: bytes, content_type: str, filename: str) -> None:
        now = time.monotonic()
        self._cache = {k: v for k, v in self._cache.items() if v[0] >= now}  # expired files go first
        if len(content) > MAX_CACHE_BYTES:
            return  # too big to keep, it is simply fetched again next time
        while self._cache and sum(len(v[1]) for v in self._cache.values()) + len(content) > MAX_CACHE_BYTES:
            del self._cache[min(self._cache, key=lambda k: self._cache[k][0])]  # the oldest goes
        self._cache[key] = (now + CACHE_SECONDS, content, content_type, filename)

    async def get(self, request: web.Request, entry_id: str, attachment_id: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
            return web.Response(status=HTTPStatus.NOT_FOUND)
        coordinator: KitaPlusCoordinator = entry.runtime_data
        file_id = int(attachment_id)
        if file_id not in attachment_ids(coordinator.data):
            return web.Response(status=HTTPStatus.NOT_FOUND)

        key = (entry_id, file_id)
        async with self._fetching:
            cached = self._cache.get(key)
            if cached is None or cached[0] < time.monotonic():
                try:
                    content, content_type, filename = await coordinator.client.async_get_file(
                        file_id, MAX_BYTES
                    )
                except KitaPlusError:
                    return web.Response(
                        status=HTTPStatus.BAD_GATEWAY, text="KitaPlus did not deliver the file"
                    )
                self._remember(key, content, content_type, filename)
            else:
                _, content, content_type, filename = cached

        inline = content_type in INLINE_TYPES
        safe = _SAFE_NAME.sub("_", filename).strip("._") or "file"
        return web.Response(
            body=content,
            content_type=content_type if inline else "application/octet-stream",
            headers={
                "Content-Disposition": f'{"inline" if inline else "attachment"}; filename="{safe}"',
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:",  # noqa: E501
                "Cache-Control": "private, no-store",
            },
        )
