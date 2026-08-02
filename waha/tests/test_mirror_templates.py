#!/usr/bin/env python3
"""Validate the Telegram-mirror payload template documented in TELEGRAM-MIRROR.md.

That template is the most failure-prone piece of the mirror and the least
debuggable: it lives in the user's `secrets.yaml`, it is rendered by Home
Assistant rather than by anything in this repo, and when it produces malformed
JSON the only symptom is an opaque HTTP 422 from WAHA.

The template is READ OUT OF THE DOC rather than duplicated here, so the two
cannot drift. If you edit the `tg_mirror_media_payload` line in
TELEGRAM-MIRROR.md, this test checks the edit.

Requires jinja2. Run directly:  python3 waha/tests/test_mirror_templates.py
"""

import json
import pathlib
import re
import sys

try:
    from jinja2 import Environment
except ImportError:
    print("SKIP: jinja2 not installed (pip install jinja2)")
    raise SystemExit(0)

DOC = pathlib.Path(__file__).resolve().parent.parent / "TELEGRAM-MIRROR.md"

# Routing templates. These live in the Home Assistant automation, not in this
# repo, so they are mirrored here as documentation of the intended mapping —
# audio/* must reach sendVoice, because that is the only audio type WhatsApp
# Channels accept.
# The `(mime | string)` parenthesisation is load-bearing: `mime | string.startswith(...)`
# is a precedence error that fails at runtime, not at config load.
ENDPOINT = (
    "{% if (mime | string).startswith('image/') %}sendImage"
    "{% elif (mime | string).startswith('video/') %}sendVideo"
    "{% elif (mime | string).startswith('audio/') %}sendVoice"
    "{% else %}sendFile{% endif %}"
)
FILENAME = (
    "{{ file_name | default('', true) | string or "
    "('tg-' ~ msg_id ~ '.' ~ ((mime | string).split('/') | last)) }}"
)

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("" if ok else "  <- " + detail))
    if not ok:
        failures.append(name)


def extract_payload_template() -> str:
    """Pull the tg_mirror_media_payload block scalar out of the doc."""
    text = DOC.read_text(encoding="utf-8")
    m = re.search(r"^tg_mirror_media_payload:\s*>-\s*\n((?:^[ \t]+.*\n?)+)", text, re.M)
    if not m:
        print(f"FAIL  could not find tg_mirror_media_payload in {DOC}")
        raise SystemExit(1)
    # YAML `>-` folds the indented continuation lines into one line.
    body = " ".join(line.strip() for line in m.group(1).splitlines() if line.strip())
    return body.replace("PASTE_YOUR_BOT_TOKEN", "TOK123")


def main() -> int:
    env = Environment()
    env.filters["tojson"] = json.dumps  # HA's tojson filter

    payload_tpl = env.from_string(extract_payload_template())

    for mime, want in [
        ("image/jpeg", "sendImage"),
        ("video/mp4", "sendVideo"),
        ("audio/ogg", "sendVoice"),
        ("audio/mpeg", "sendVoice"),
        ("application/pdf", "sendFile"),
        # Degenerate inputs. The automation stops before this template when the
        # MIME type is absent entirely, but the routing must not raise if it is
        # ever reached with something malformed.
        ("", "sendFile"),
        ("application/octet-stream", "sendFile"),
        ("weird-no-slash", "sendFile"),
        ("IMAGE/JPEG", "sendFile"),  # case-sensitive by design; Telegram sends lowercase
    ]:
        got = env.from_string(ENDPOINT).render(mime=mime).strip()
        check(f"{mime!r} routes to {want}", got == want, f"got {got}")

    got = env.from_string(FILENAME).render(file_name="", mime="image/jpeg", msg_id=42)
    check("photo filename synthesised", got == "tg-42.jpeg", f"got {got}")
    got = env.from_string(FILENAME).render(
        file_name="report.pdf", mime="application/pdf", msg_id=42
    )
    check("supplied filename preserved", got == "report.pdf", f"got {got}")
    # A mime with no slash must still produce something usable rather than raising.
    got = env.from_string(FILENAME).render(file_name="", mime="weird-no-slash", msg_id=7)
    check("slashless mime still yields a filename", got == "tg-7.weird-no-slash", f"got {got}")
    got = env.from_string(FILENAME).render(file_name="", mime="", msg_id=7)
    check("empty mime still yields a filename", got == "tg-7.", f"got {got}")

    nasty = 'Quote " backslash \\ brace {"a": 1}\nnewline é\U0001f680'
    cases = [
        ("image + caption", "sendImage", "image/jpeg", "p.jpg", "photos/a.jpg", nasty),
        ("image, empty caption", "sendImage", "image/jpeg", "p.jpg", "photos/a.jpg", ""),
        ("image, blank caption", "sendImage", "image/jpeg", "p.jpg", "photos/a.jpg", "   "),
        ("voice", "sendVoice", "audio/ogg", "v.oga", "voice/b.oga", "dropped"),
        ("video", "sendVideo", "video/mp4", "v.mp4", "videos/c.mp4", "clip"),
        ("document", "sendFile", "application/pdf", "r.pdf", "documents/d.pdf", "doc"),
    ]

    for name, endpoint, mimetype, filename, file_path, caption in cases:
        out = payload_tpl.render(
            session="session_01abc",
            chat_id="120363000000000000@newsletter",
            endpoint=endpoint,
            mimetype=mimetype,
            filename=filename,
            file_path=file_path,
            caption=caption,
        )
        try:
            p = json.loads(out)
        except Exception as exc:  # noqa: BLE001 - want the raw text on failure
            check(f"valid JSON: {name}", False, f"{exc}\n      {out}")
            continue
        check(f"valid JSON: {name}", True)

        check(
            f"  media URL built: {name}",
            p["file"]["url"] == f"https://api.telegram.org/file/botTOK123/{file_path}",
            p["file"]["url"],
        )
        check(f"  session/chatId set: {name}", bool(p["session"]) and bool(p["chatId"]))

        if endpoint == "sendVoice":
            # WhatsApp voice notes have no caption, and WAHA needs convert:true
            # to transcode an mp3 into the OGG/Opus it will accept.
            check("  voice omits caption", "caption" not in p)
            check("  voice sets convert", p.get("convert") is True)
        else:
            check(f"  no stray convert key: {name}", "convert" not in p)
            if caption.strip():
                check(f"  caption round-trips: {name}", p["caption"] == caption,
                      repr(p.get("caption")))
            else:
                check(f"  blank caption omitted: {name}", "caption" not in p)

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S): {failures}")
        return 1
    print("All mirror template assertions passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
