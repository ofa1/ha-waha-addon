"""Thin async client for the WAHA HTTP API.

Deliberately small: WAHA is a plain JSON-over-HTTP service, and the only piece
of real logic here is :func:`endpoint_for_mimetype`. That routing used to live
in a Jinja template inside the user's ``secrets.yaml``, where a mistake showed
up as an opaque HTTP 422 from WAHA and nothing else. It is Python now so it can
be tested.

Nothing in this module logs a request body. Media sends carry a URL that the
caller may have built with a bearer token in it (the Telegram mirror does
exactly that), and WAHA fetches it server-side, so the body must never reach
the Home Assistant log.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=30)
# WAHA downloads the media itself before it answers, so a send of a large file
# can legitimately sit here for a while.
MEDIA_TIMEOUT = aiohttp.ClientTimeout(total=120)

TEXT_ENDPOINT = "sendText"


class WahaError(Exception):
    """Base class for WAHA client errors."""


class WahaConnectionError(WahaError):
    """WAHA could not be reached."""


class WahaAuthError(WahaError):
    """WAHA rejected the API key."""


class WahaResponseError(WahaError):
    """WAHA returned an error response."""

    def __init__(self, status: int, detail: str) -> None:
        """Store the status alongside the message."""
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


def endpoint_for_mimetype(mimetype: str | None) -> str:
    """Return the WAHA endpoint that accepts a file of this MIME type.

    WhatsApp Channels accept exactly one audio type, so every ``audio/*`` file
    is sent as a voice note; the caller is expected to ask WAHA to transcode
    (see :meth:`WahaClient.async_send_media`). Unrecognised types fall through
    to ``sendFile``, which WAHA does not document as Channel-capable — it is
    attempted anyway so the failure is a visible HTTP error rather than a
    silent drop.
    """
    normalised = (mimetype or "").strip().lower()
    if normalised.startswith("image/"):
        return "sendImage"
    if normalised.startswith("video/"):
        return "sendVideo"
    if normalised.startswith("audio/"):
        return "sendVoice"
    return "sendFile"


def build_media_payload(
    *,
    session: str,
    chat_id: str,
    url: str,
    mimetype: str | None,
    filename: str,
    caption: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Build the (endpoint, body) pair for a media send.

    Split out from the request itself so the payload shape is testable without
    a running WAHA.
    """
    endpoint = endpoint_for_mimetype(mimetype)
    payload: dict[str, Any] = {
        "session": session,
        "chatId": chat_id,
        "file": {
            "mimetype": mimetype or "application/octet-stream",
            "filename": filename,
            "url": url,
        },
    }
    if endpoint == "sendVoice":
        # A voice note has no caption, and `convert` is what lets an mp3 in —
        # WhatsApp only accepts OGG/Opus here.
        payload["convert"] = True
    elif caption and caption.strip():
        payload["caption"] = caption
    return endpoint, payload


class WahaClient:
    """Minimal WAHA API client."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int,
        api_key: str,
        *,
        use_ssl: bool = False,
    ) -> None:
        """Initialise the client."""
        self._session = session
        self._api_key = api_key
        scheme = "https" if use_ssl else "http"
        self._base_url = f"{scheme}://{host}:{port}"

    @property
    def base_url(self) -> str:
        """Return the base URL, safe to show in the UI (carries no secret)."""
        return self._base_url

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        timeout: aiohttp.ClientTimeout = DEFAULT_TIMEOUT,
    ) -> Any:
        """Perform a request and return the decoded body."""
        url = f"{self._base_url}/{path.lstrip('/')}"
        try:
            response = await self._session.request(
                method,
                url,
                params=params,
                json=json,
                headers={"X-Api-Key": self._api_key},
                timeout=timeout,
            )
        except asyncio.TimeoutError as err:
            raise WahaConnectionError(f"Timeout contacting WAHA at {url}") from err
        except aiohttp.ClientError as err:
            raise WahaConnectionError(f"Cannot connect to WAHA at {url}: {err}") from err

        async with response:
            if response.status in (401, 403):
                raise WahaAuthError("WAHA rejected the API key")
            if response.status >= 400:
                # Capped: this is WAHA's message, not ours, and it ends up in
                # the Home Assistant log.
                detail = (await response.text())[:500]
                raise WahaResponseError(response.status, detail)
            body = await response.read()
            if not body:
                return None
            try:
                # WAHA is not always precise about its content-type header.
                return await response.json(content_type=None)
            except ValueError:
                return body.decode(errors="replace")

    async def async_list_sessions(self) -> list[dict[str, Any]]:
        """Return every session WAHA knows about, including stopped ones."""
        result = await self._request("GET", "/api/sessions", params={"all": "true"})
        if not isinstance(result, list):
            raise WahaResponseError(200, "Unexpected response from /api/sessions")
        return [item for item in result if isinstance(item, dict)]

    async def async_send_text(
        self,
        *,
        session: str,
        chat_id: str,
        text: str,
        link_preview: bool | None = None,
    ) -> Any:
        """Send a text message."""
        payload: dict[str, Any] = {
            "session": session,
            "chatId": chat_id,
            "text": text,
        }
        if link_preview is not None:
            payload["linkPreview"] = link_preview
        _LOGGER.debug("Sending text to %s via session %s", chat_id, session)
        return await self._request("POST", f"/api/{TEXT_ENDPOINT}", json=payload)

    async def async_send_media(
        self,
        *,
        session: str,
        chat_id: str,
        url: str,
        mimetype: str | None,
        filename: str,
        caption: str | None = None,
    ) -> Any:
        """Send a media message by URL, letting WAHA fetch the bytes."""
        endpoint, payload = build_media_payload(
            session=session,
            chat_id=chat_id,
            url=url,
            mimetype=mimetype,
            filename=filename,
            caption=caption,
        )
        # The URL is not logged: callers embed credentials in it.
        _LOGGER.debug(
            "Sending %s (%s) to %s via session %s",
            endpoint,
            mimetype,
            chat_id,
            session,
        )
        return await self._request(
            "POST", f"/api/{endpoint}", json=payload, timeout=MEDIA_TIMEOUT
        )
