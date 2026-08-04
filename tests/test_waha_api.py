#!/usr/bin/env python3
"""Checks for the WAHA client's MIME routing and payload construction.

These two functions carry the logic that used to live in a Jinja template in
the user's `secrets.yaml`, where a mistake surfaced only as an opaque HTTP 422
from WAHA. Moving it into Python is the point of the integration, so it is
tested.

`api.py` is loaded directly rather than imported as `custom_components.waha.api`
so the test needs aiohttp and nothing else — importing the package would pull
in Home Assistant.

Run directly:  python3 tests/test_waha_api.py
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

API_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "custom_components"
    / "waha"
    / "api.py"
)

_spec = importlib.util.spec_from_file_location("waha_api", API_PATH)
if _spec is None or _spec.loader is None:  # pragma: no cover - import plumbing
    print(f"FAIL  could not load {API_PATH}")
    raise SystemExit(1)
api = importlib.util.module_from_spec(_spec)
try:
    _spec.loader.exec_module(api)
except ImportError as err:  # pragma: no cover - dependency plumbing
    print(f"SKIP: {err} (pip install aiohttp)")
    raise SystemExit(0) from err

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    """Record and print one assertion."""
    print(("PASS  " if ok else "FAIL  ") + name + ("" if ok else "  <- " + detail))
    if not ok:
        failures.append(name)


def test_routing() -> None:
    """Every MIME type reaches the endpoint WhatsApp Channels expect."""
    cases = [
        ("image/jpeg", "sendImage"),
        ("image/png", "sendImage"),
        ("video/mp4", "sendVideo"),
        ("audio/ogg", "sendVoice"),
        ("audio/mpeg", "sendVoice"),
        ("application/pdf", "sendFile"),
        # Degenerate inputs must route somewhere rather than raise. The Jinja
        # version this replaces was case-sensitive and sent `IMAGE/JPEG` as a
        # document; normalising is the fix.
        ("IMAGE/JPEG", "sendImage"),
        ("  image/jpeg  ", "sendImage"),
        ("", "sendFile"),
        (None, "sendFile"),
        ("application/octet-stream", "sendFile"),
        ("weird-no-slash", "sendFile"),
    ]
    for mimetype, want in cases:
        got = api.endpoint_for_mimetype(mimetype)
        check(f"{mimetype!r} routes to {want}", got == want, f"got {got}")


def test_payloads() -> None:
    """The body is valid JSON and carries the right keys per media type."""
    nasty = 'Quote " backslash \\ brace {"a": 1}\nnewline é\U0001f680'
    cases = [
        ("image + caption", "image/jpeg", "p.jpg", nasty),
        ("image, empty caption", "image/jpeg", "p.jpg", ""),
        ("image, blank caption", "image/jpeg", "p.jpg", "   "),
        ("image, no caption", "image/jpeg", "p.jpg", None),
        ("voice", "audio/ogg", "v.oga", "dropped"),
        ("video", "video/mp4", "v.mp4", "clip"),
        ("document", "application/pdf", "r.pdf", "doc"),
    ]

    for name, mimetype, filename, caption in cases:
        url = f"https://example.org/files/{filename}"
        endpoint, payload = api.build_media_payload(
            session="session_01abc",
            chat_id="120363000000000000@newsletter",
            url=url,
            mimetype=mimetype,
            filename=filename,
            caption=caption,
        )

        try:
            # aiohttp serialises the body with json.dumps, so this is the same
            # encoding step that would fail in production.
            round_tripped = json.loads(json.dumps(payload))
        except (TypeError, ValueError) as err:
            check(f"serialisable: {name}", False, str(err))
            continue
        check(f"serialisable: {name}", True)

        check(
            f"  url preserved: {name}",
            round_tripped["file"]["url"] == url,
            round_tripped["file"]["url"],
        )
        check(
            f"  session/chatId set: {name}",
            bool(round_tripped["session"]) and bool(round_tripped["chatId"]),
        )
        check(
            f"  mimetype/filename set: {name}",
            round_tripped["file"]["mimetype"] == mimetype
            and round_tripped["file"]["filename"] == filename,
        )

        if endpoint == "sendVoice":
            # A WhatsApp voice note has no caption, and without `convert` WAHA
            # will not transcode an mp3 into the OGG/Opus WhatsApp accepts.
            check("  voice omits caption", "caption" not in round_tripped)
            check("  voice sets convert", round_tripped.get("convert") is True)
        else:
            check(f"  no stray convert key: {name}", "convert" not in round_tripped)
            if caption and caption.strip():
                check(
                    f"  caption round-trips: {name}",
                    round_tripped["caption"] == caption,
                    repr(round_tripped.get("caption")),
                )
            else:
                check(f"  blank caption omitted: {name}", "caption" not in round_tripped)

    # A missing MIME type must still produce a body WAHA will accept.
    _, payload = api.build_media_payload(
        session="s",
        chat_id="c",
        url="https://example.org/x",
        mimetype=None,
        filename="x",
    )
    check(
        "missing mimetype defaults to octet-stream",
        payload["file"]["mimetype"] == "application/octet-stream",
        payload["file"]["mimetype"],
    )


def main() -> int:
    """Run every check."""
    test_routing()
    test_payloads()

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S): {failures}")
        return 1
    print("All WAHA client assertions passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
