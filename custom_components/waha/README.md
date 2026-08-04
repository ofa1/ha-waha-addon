# WAHA integration for Home Assistant

A small custom integration that talks to a [WAHA](https://waha.devlike.pro/)
server — normally the [add-on in this repository](../../waha/), but any
reachable WAHA works.

It gives you:

- a **config flow**, so the API key is stored in the config entry instead of
  `secrets.yaml`, and can be rotated from the UI;
- a **session status sensor** per WAHA session, so an automation can notice
  when WhatsApp disconnects instead of you finding out from silence;
- two services — **`waha.send_text`** and **`waha.send_media`**.

### What it does not do

It does **not** remove the need for `rest_command` in every case. `send_media`
takes a URL, so it only helps when you already have one that WAHA can fetch
without further authentication. The Telegram mirror in this repository does not:
Telegram's file download URL embeds the bot token, and Home Assistant resolves
`!secret` only in YAML configuration — not in automations, templates or the
config API. So the mirror keeps one `rest_command` for its media path, and the
WAHA API key stays in `secrets.yaml` for that one call. Its text path is a
straight `waha.send_text`.

## Installing

**HACS:** HACS → ⋮ → Custom repositories → add `https://github.com/ofa1/ha-waha-addon`
with category **Integration** → install **WAHA WhatsApp API** → restart Home
Assistant.

This is a *separate* step from adding the repository to the add-on store. The
same repository serves both: the Supervisor reads `repository.yaml` and
`waha/`, HACS reads `hacs.json` and `custom_components/`.

**Manual:** copy `custom_components/waha/` into your `config/custom_components/`
directory and restart.

Then **Settings → Devices & Services → Add Integration → WAHA WhatsApp API**.

### What to put in the form

| Field | Value |
|---|---|
| Host | The add-on's hostname: its slug with every `_` replaced by `-`, e.g. `a1b2c3d4-waha-whatsapp-api`. The slug is in the URL when you open the add-on page. |
| Port | `3000`. This is WAHA's port on the internal Supervisor network — it does **not** need to be exposed on the host. |
| API key | The add-on's `api_key` option. If you left it blank the add-on generated one and printed it to the log on first start only; set an explicit one and restart the add-on if that has scrolled away. |
| Default session | Your WAHA session name, usually `default`. Service calls can override it. |
| Connect over HTTPS | Off for the add-on. |

Running WAHA elsewhere: use its hostname or IP and whatever port it listens on.

## Services

### `waha.send_text`

| Field | Required | Notes |
|---|---|---|
| `chat_id` | yes | `…@newsletter` for a channel, `…@c.us` for a contact, `…@g.us` for a group |
| `text` | yes | |
| `session` | no | defaults to the entry's session |
| `link_preview` | no | whether WhatsApp renders a preview for links |
| `config_entry_id` | no | only needed with more than one WAHA configured |

### `waha.send_media`

WAHA fetches the file itself, so the bytes never pass through Home Assistant —
a 40 MB video costs one small JSON round-trip. The URL must be reachable **from
the WAHA container**, not from your browser.

| Field | Required | Notes |
|---|---|---|
| `chat_id` | yes | |
| `url` | yes | where WAHA downloads the file from |
| `filename` | yes | the name WhatsApp displays |
| `mimetype` | no | decides how it is sent — see below |
| `caption` | no | ignored for audio |
| `session` | no | |
| `config_entry_id` | no | |

`mimetype` drives the routing, in Python rather than in a template:

| MIME type | Sent as | Endpoint |
|---|---|---|
| `image/*` | photo | `sendImage` |
| `video/*` | video | `sendVideo` |
| `audio/*` | voice note, transcoded (`convert: true`) | `sendVoice` |
| anything else, or absent | document | `sendFile` |

Both services return the WAHA response when called with `response_variable`.

## Limits worth knowing

- **Audio always becomes a voice note.** WhatsApp Channels accept exactly one
  audio type, so an mp3 arrives as a voice note and loses its artist/title
  metadata. This is WhatsApp's constraint, not the integration's.
- **Documents may be rejected on Channels.** WAHA documents Channel support for
  text, image, video and voice; `sendFile` is not on that list. It is attempted
  anyway so you get a visible HTTP error rather than a silent drop.
- **The status sensor polls every 30 seconds.** A session that drops is noticed
  within that window, not instantly.
- **`STOPPED` is a normal state**, not a fault — it means the session exists but
  is not started. `WORKING` is the one you want; `SCAN_QR_CODE` means it needs
  re-pairing.

## Example

```yaml
- alias: Post to the WhatsApp channel
  triggers:
    - trigger: state
      entity_id: binary_sensor.something
      to: "on"
  conditions:
    - condition: state
      # Check the real entity_id in Developer Tools → States; it is derived
      # from the config entry title and the session name, so it will look
      # something like sensor.waha_a1b2c3d4_waha_whatsapp_api_default_status.
      entity_id: sensor.CHANGE_ME_status
      state: WORKING
  actions:
    - action: waha.send_text
      data:
        chat_id: "120363000000000000@newsletter"
        text: "Something happened."
```

The `condition` is the part worth copying: without it a post made while the
session is down fails with an HTTP error and is simply lost.
