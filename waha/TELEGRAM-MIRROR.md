# Mirroring a Telegram channel into a WhatsApp Channel

One-way replication: every new post in a Telegram channel is reposted to a
WhatsApp Channel through this add-on. Text, photos, videos and audio are
covered. It runs entirely inside Home Assistant — no extra service, no
container, no code.

> **Read [`SECURITY.md`](SECURITY.md) first if you have not.** This turns a
> manually-driven WhatsApp integration into an unattended one. Unattended bulk
> posting through an unofficial API is the pattern most likely to get a number
> banned, which is why the mirror is deliberately throttled (see
> [Rate limiting](#rate-limiting)). Use a number you can afford to lose.

## How it works

```
Telegram channel
      │  bot receives channel_post (bot must be a channel admin)
      ▼
telegram_bot integration ──fires──► telegram_text / telegram_attachment event
      ▼
automation.telegram_channel_to_whatsapp_channel_mirror
      │  dedupe on message id, then split by event type
      │
      ├─ text ──► waha.send_text ──────────────► WAHA add-on :3000
      │
      └─ media ─► rest_command: Telegram getFile → a file path
                  (no bytes enter Home Assistant)
                        │
                        ▼
                  rest_command ──► WAHA :3000 ──fetches the media──► Telegram
      ▼
WhatsApp Channel
```

The two halves are asymmetric, and the reason is worth stating once: text goes
through the [`waha` integration](../custom_components/waha/), so there is no
YAML and no API key in `secrets.yaml` for that path. Media cannot, because
Telegram's file download URL embeds the bot token and `!secret` is only
resolvable from YAML configuration — not from automations, templates, or
anything written through the config API. So the media path keeps two
`rest_command`s and the WAHA API key in `secrets.yaml`.

The media handoff is the part worth understanding: Home Assistant never
downloads the file. It asks Telegram for the file *path*, builds a URL, and
hands that URL to WAHA, which fetches the bytes server-side. Nothing is written
to `/config/www`, nothing is exposed unauthenticated, and a 40 MB video costs
Home Assistant nothing but one small JSON round-trip.

## What you need to set up

Six things. Four are one-time lookups; two are edits.

### 1. Set the WAHA API key

Home Assistant has to authenticate to WAHA, and the current key was
auto-generated and has already scrolled out of the add-on log — it is not
recoverable. Set an explicit one.

Generate a key:

```bash
openssl rand -hex 32
```

Then **Settings → Add-ons → WAHA WhatsApp API → Configuration**, put it in
`api_key`, save, and restart the add-on. Config-only; no rebuild.

Keep this value. It is used twice: once in the `waha` integration's setup form,
and once in `secrets.yaml` for the media path (step 5).

Then install the integration — HACS → ⋮ → Custom repositories → this repository
with category **Integration** → install → restart Home Assistant → **Settings →
Devices & Services → Add Integration → WAHA WhatsApp API**. See
[the integration's README](../custom_components/waha/README.md) for what goes in
each field. It also gives you a session-status sensor, which is the only thing
that will tell you the WhatsApp session has dropped.

### 2. Create the Telegram bot and make it a channel admin

1. Message [@BotFather](https://t.me/BotFather) → `/newbot` → keep the token.
2. Open your Telegram channel → **Administrators** → **Add Administrator** →
   add your bot.

The admin step is not optional and not cosmetic. Telegram only delivers
`channel_post` updates to bots that administer the channel. A bot that is
merely a member receives nothing at all.

### 3. Add the Telegram Bot integration

**Settings → Devices & Services → Add Integration → Telegram bot**, choose
**polling**, and paste the token. Leave the "Additional settings" section
alone — the default API endpoint is correct and the proxy field is optional.
Polling needs no public URL, so this works behind your Cloudflare tunnel with
no extra exposure.

The setup form does *not* ask for a chat ID. Allowed chats are added
afterwards as sub-entries, which is step 4.

### 4. Find your channel's chat ID

Post anything into the Telegram channel, then look at
**Settings → System → Logs**. You will see:

```
Unauthorized update - neither user id None nor chat id -1001234567890 is in allowed chats: [...]
```

That `-100…` number is your channel's chat ID.

> This error is the *only* way to discover the ID, and it is worth knowing why:
> the integration authorizes an update **before** it fires the Home Assistant
> event. Until the channel is in the allowed list, no `telegram_text` event
> exists to inspect — the probe automation below will show you nothing.

Now authorise it: **Settings → Devices & Services → Telegram bot → Add allowed
chat ID**, and paste the `-100…` number (digits and the leading minus only —
the field takes an integer). Post in the channel again and confirm the
unauthorized error has stopped.

### 5. Add the REST commands

This is the one piece with no UI — `rest_command` is YAML-only. Use the File
editor or Studio Code Server add-on.

Append to **`configuration.yaml`**:

```yaml
rest_command:
  # Resolves a Telegram file_id to a downloadable path. The URL lives in
  # secrets.yaml because it embeds the bot token; rest_command renders the
  # {{ file_id }} template after the secret is loaded.
  tg_mirror_get_file:
    url: !secret tg_mirror_get_file_url
    method: get
    timeout: 30

  # Media posts. The payload template is a secret too, because it has to embed
  # the bot token in the file URL that WAHA fetches.
  #
  # There is deliberately no equivalent for text posts: those go through
  # `waha.send_text`, which needs no YAML and holds the API key in its config
  # entry rather than here.
  tg_mirror_waha_send_media:
    url: "http://a6137ac8-waha-whatsapp-api:3000/api/{{ endpoint }}"
    method: post
    content_type: "application/json"
    payload: !secret tg_mirror_media_payload
    headers:
      X-Api-Key: !secret waha_api_key
    timeout: 120
```

`a6137ac8-waha-whatsapp-api` is this add-on's DNS name on the Supervisor
network — the add-on slug with every `_` replaced by `-`. It resolves from Home
Assistant Core with no host port mapped, which is why `3000/tcp` can stay
disabled.

Append to **`secrets.yaml`**, replacing both placeholders:

```yaml
waha_api_key: "PASTE_THE_KEY_FROM_STEP_1"

tg_mirror_get_file_url: "https://api.telegram.org/botPASTE_YOUR_BOT_TOKEN/getFile?file_id={{ file_id }}"

# One line. Builds the WAHA request body and embeds the bot token in the media
# URL. Every value goes through `| tojson`, so captions containing quotes,
# newlines or emoji cannot break the JSON.
tg_mirror_media_payload: >-
  {"session": {{ session | tojson }}, "chatId": {{ chat_id | tojson }}{% if endpoint != 'sendVoice' and caption | trim %}, "caption": {{ caption | tojson }}{% endif %}, "file": {"mimetype": {{ mimetype | tojson }}, "filename": {{ filename | tojson }}, "url": {{ ('https://api.telegram.org/file/botPASTE_YOUR_BOT_TOKEN/' ~ file_path) | tojson }}}{% if endpoint == 'sendVoice' %}, "convert": true{% endif %}}
```

Both secrets carry the bot token, which is why they are secrets and not inline
in `configuration.yaml`.

Then **restart Home Assistant** — a brand-new top-level key needs a full
restart the first time. After that, edits only need
`rest_command.reload` from Developer Tools → Actions.

### 6. Fill in the three helpers

**Settings → Devices & Services → Helpers**:

| Helper | Value |
|---|---|
| `TG Mirror Source Chat ID` | The `-100…` channel ID from step 4 |
| `TG Mirror WhatsApp Channel ID` | The `…@newsletter` ID — see below |
| `TG Mirror WAHA Session` | Your WAHA session name |

For the last two, open the add-on's **Channel Test** page
(`/channel-test/` under the add-on's ingress URL). It lists your live sessions
in a dropdown, and resolving your channel invite link prints the channel
object — `id` is the value you want. That page already exists for exactly this.

The mirror **fails closed**: while any of the three is blank it does nothing,
so filling in the last one is what switches it on.

## Verifying it

Turn on `TG Mirror - payload probe (setup only)` and post one text message, one
photo, one voice note and one audio file into the Telegram channel. Then read
**Settings → System → Logs** — the probe logs each event's full payload at
WARNING.

This exists because the media routing keys off `file_mime_type`, and that field
is not uniformly present: photos get a hardcoded `image/jpeg`, voice notes and
documents report their real MIME type, and stickers carry no MIME type at all.
Confirm what your channel actually produces before trusting the dispatch.

**Turn the probe off once you are done** — it writes the content of every
message the bot sees into the Home Assistant log.

## Limits, and why they are there

**Edits are not propagated.** Telegram delivers an edit of an existing post as
a fresh event carrying the *same* message ID. The mirror only acts on IDs
strictly greater than the last one it posted, which is what stops an edit from
posting a duplicate. The trade-off is that once a post is mirrored, editing it
in Telegram changes nothing in WhatsApp. For a one-way mirror that is the right
default; there is no reliable way to have both.

**Attachments over 20 MB are skipped**, with a log line naming the size. This
is a hard Telegram Bot API limit on `getFile` — the file can exist in the
channel and still be undownloadable by a bot. Checked before the call so it
reads as a clear skip rather than an opaque error.

**An audio file becomes a voice note.** WhatsApp Channels accept exactly one
audio type — `sendVoice` — so a Telegram `audio` (an mp3, with artist and title
metadata) arrives in WhatsApp as a voice note, losing that metadata. WAHA's
`convert: true` handles the transcode to OGG/Opus. Telegram *voice* notes pass
through unchanged.

**Documents may not post at all.** WAHA documents channel support for text,
image, video, voice, reactions and poll votes — `sendFile` is not on that list.
The mirror still attempts it for unrecognised MIME types and logs the failure
if WhatsApp rejects it. Test one PDF before assuming documents work.

**Albums arrive as separate posts.** Telegram sends each photo of a media group
as its own update, so a 4-photo album becomes 4 WhatsApp posts.

**Polls and service messages are skipped**, and logged at INFO.

**The dedupe counter is bound to one channel.** `TG Mirror Last Message ID` is
a high-water mark, and Telegram message IDs are sequential *per chat* starting
at 1. If you ever point `TG Mirror Source Chat ID` at a different channel — or
delete and recreate the same one — the new channel's IDs start well below the
stored mark and **every post is silently suppressed**. Reset
`TG Mirror Last Message ID` to `0` whenever you change the source channel.

Leaving your personal chat authorised in the Telegram Bot integration is
harmless: posts from any chat other than the configured source are rejected by
the second condition, and never touch the counter.

### Rate limiting

The automation is `mode: queued` with a 5-second delay after each post, capping
the mirror at roughly 12 posts per minute. A backlog — for example after Home
Assistant has been down and Telegram replays up to 24 hours of updates — drains
steadily instead of firing as a burst. Do not remove this to "catch up faster";
bursts are what get numbers banned.

## Security notes

- The bot token appears in two `secrets.yaml` entries and in the URLs WAHA
  fetches. WAHA logs outbound request URLs at `debug`/`trace` level, so raising
  the add-on's `log_level` above `info` will write your Telegram bot token into
  the add-on log. Keep it at `info` unless you are actively debugging, and
  clear the log afterwards.
- The probe automation logs message content. It is a setup tool, not something
  to leave running.
- Nothing here opens a port. WAHA stays reachable only on the internal
  Supervisor network, and Telegram is contacted outbound-only via polling.

## If something does not post

Check in this order:

1. **Automation trace** — Settings → Automations → the mirror → Traces. Shows
   which condition rejected the run, or the exact WAHA response.
2. **`tg_mirror` log entries** — every skip and every HTTP failure is logged
   with the Telegram message ID.
3. **`Unauthorized update`** in the log means the chat ID in the Telegram Bot
   integration does not match the channel.
4. **HTTP 401 from WAHA on a media post** means `waha_api_key` in
   `secrets.yaml` does not match the add-on's `api_key`. If *text* posts fail
   on authentication instead, the stale key is in the `waha` integration —
   Home Assistant will raise a reauth prompt for it rather than a 401 in the
   trace.
5. **HTTP 422 mentioning the session** means the session name changed — WAHA
   regenerates it on re-pair. Update the `TG Mirror WAHA Session` helper.
6. **Nothing happens at all, and the trace shows condition 3 failing** — the
   dedupe counter is ahead of the channel's message IDs. This is what you see
   after switching source channels. Set `TG Mirror Last Message ID` to `0`.
7. **Nothing happens and there is no trace at all** — the bot is not receiving
   channel posts. Confirm it is an *administrator* of the channel, not just a
   member.

## What has been verified, and what has not

The routing logic was exercised end-to-end by firing synthetic
`telegram_text` / `telegram_attachment` events at the automation and reading
the traces: condition matching, the dedupe counter, the MIME dispatch
(`image/jpeg` → `sendImage`), the synthesised filename for a photo
(`tg-502.jpeg`), the no-MIME skip, and the 20 MB skip all behave as documented.
The payload template is covered by `tests/test_mirror_templates.py`.

The WhatsApp side has since been verified against live credentials:
`waha.send_text` and `waha.send_media` were both confirmed to post to a real
WhatsApp Channel, and a synthetic `telegram_text` event was run through the
whole automation — conditions, dedupe counter, text branch, throttle — landing
a post in WhatsApp.

Still not verified, because it needs a real Telegram attachment: the media
branch's two HTTP calls, Telegram's `getFile` and the `rest_command` that hands
the resulting URL to WAHA. Your first real photo or voice note in the channel is
the test for those, which is why the troubleshooting list above starts with the
automation trace.
