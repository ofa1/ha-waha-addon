# WAHA Home Assistant Add-on Repository

A Home Assistant OS add-on repository for running [WAHA](https://waha.devlike.pro/) — a self-hosted WhatsApp HTTP API — on Home Assistant OS.

This repo is intended for a small, dedicated WhatsApp automation workload such as posting new nonprofit/blog announcements to a WhatsApp Channel through a dedicated WhatsApp number.

> **Important:** WAHA uses unofficial WhatsApp Web-style automation. That is not the same as Meta's official WhatsApp Business Cloud API and may violate WhatsApp's terms. Use a dedicated number that you can afford to lose; do not use your nonprofit's primary contact number.

## Add this repository to Home Assistant

[![Open your Home Assistant instance and show the add add-on repository dialog with this repository pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fofa1%2Fha-waha-addon)

Or add it manually:

1. In Home Assistant: **Settings → Add-ons → Add-on Store → ⋮ → Repositories**.
2. Paste this repository URL:

   ```text
   https://github.com/ofa1/ha-waha-addon
   ```

3. Install **WAHA WhatsApp API**.
4. Open the add-on configuration. You may leave `api_key` and `dashboard_password` blank; the add-on auto-generates and persists them on first start. If you want to manage secrets yourself, set strong values manually.

## What this add-on does

- Uses the browserless `devlikeapro/waha:noweb-arm-*` image, suitable for Raspberry Pi / HAOS on ARM.
- Defaults to the **GOWS** engine, with **NOWEB** as the recommended fallback if channel posting is engine-sensitive.
- Persists WAHA sessions under `/data/.sessions`, so QR pairing survives add-on restarts and Home Assistant backups.
- Browser access uses Home Assistant ingress through an internal Nginx proxy, so no host port is exposed by default.

See [`waha/DOCS.md`](waha/DOCS.md) for setup, Cloudflare Tunnel notes, and channel-post testing, and [`waha/SECURITY.md`](waha/SECURITY.md) for the threat model and residual risks.

## Home Assistant integration

This repository also ships a custom integration,
[`custom_components/waha`](custom_components/waha/), installable through HACS as
a **custom repository** with category *Integration*. It adds a config flow for
the API key, a session-status sensor, and `waha.send_text` / `waha.send_media`
services — so automations call actions instead of hand-written `rest_command`
blocks, and the MIME-type routing lives in tested Python rather than in a Jinja
template in your `secrets.yaml`.

`waha.send_media` takes a URL, so it replaces a `rest_command` only where that
URL needs no further authentication. The Telegram mirror below is a case where
it does not — see the integration's README for why.

The Supervisor and HACS read different files (`repository.yaml` + `waha/` versus
`hacs.json` + `custom_components/`), so the same repository serves both. They
are independent: the add-on works without the integration, and the integration
works against any reachable WAHA.

## Mirroring a Telegram channel

[`waha/TELEGRAM-MIRROR.md`](waha/TELEGRAM-MIRROR.md) sets up one-way replication
of a Telegram channel into a WhatsApp Channel — text, photos, videos and audio —
using only Home Assistant automations and this add-on. Media never passes
through Home Assistant: WAHA fetches it from Telegram directly.

## Development

The Supervisor builds this add-on on the Home Assistant device itself. A
failing `nginx -t` in `run.sh` takes WhatsApp down. To check the configuration
and ingress routes locally before updating the add-on:

```bash
./waha/tests/validate.sh
```

It renders the ingress template, boots it against a stub upstream, and asserts
the routing behaviour. Every assertion corresponds to a regression that has
actually shipped; see [`waha/CHANGELOG.md`](waha/CHANGELOG.md). Requires
`nginx` and `python3`. The same script runs in CI on every PR to `main`
and on pushes affecting the add-on.

The Telegram mirror's payload template is checked separately, by rendering the
snippet straight out of `TELEGRAM-MIRROR.md` and asserting the result is valid
JSON for every media type:

```bash
python3 ./waha/tests/test_mirror_templates.py   # needs jinja2
```

The integration's MIME routing and payload construction are checked the same
way, without needing Home Assistant installed:

```bash
python3 ./tests/test_waha_api.py                # needs aiohttp
```

CI additionally runs Home Assistant's `hassfest` and the HACS action against
`custom_components/waha`.

The **ARM add-on** workflow builds the Dockerfile on a native `linux/arm64`
runner, boots it with throwaway data on an isolated network, and checks that
`/api/server/version` reports GOWS through the real ingress proxy.

### Dependency updates

Renovate proposes GitHub Actions updates for manual review. The **Update WAHA**
workflow checks daily for a newer stable upstream release with a published
`noweb-arm-YYYY.M.P` image. It pins the ARM image by tag and digest, bumps the
add-on patch version in [`waha/config.yaml`](waha/config.yaml), and adds a
matching entry to [`waha/CHANGELOG.md`](waha/CHANGELOG.md) in one PR. Let the
workflow manage its `automation/waha` branch; make manual fixes on another branch.

The generated PR auto-merges only after GitHub's required checks pass.
**Keep auto-update off in the Home Assistant add-on settings** before enabling
the updater. Merge makes a new version available; install it separately.
After installation, confirm the existing GOWS session returns to `WORKING`
without re-pairing and send a test channel post. CI does not run Supervisor,
log into WhatsApp, or send a post.

#### Enable the WAHA updater

1. Enable auto-merge and squash merging in the GitHub repository settings.
2. Protect `main` for everyone (including admins). Require PR branches to be
   up to date and require these checks from GitHub Actions: `Config and routing`,
   `Add-on manifest`, `Custom integration`, and `Build and boot ARM add-on`.
   Do not require a human approval or grant the updater a bypass.
3. Create a private GitHub App with **Contents: Read and write** and
   **Pull requests: Read and write**. Disable webhooks and install it on this
   repository only. In the GitHub Actions environment `waha-updater`, allow
   deployments only from the `main` branch (this environment stores updater
   credentials, not a Home Assistant deployment). Set the variable
   `WAHA_UPDATER_APP_CLIENT_ID` to the app's client ID and the secret
   `WAHA_UPDATER_APP_PRIVATE_KEY` to its private key. The App token lets GitHub
   start CI on the generated PR without an approval click.

Disable the **Update WAHA** workflow to pause future proposals. If an update PR
is already open, turn off its auto-merge separately.
