# WAHA Home Assistant Add-on Repository

A Home Assistant OS add-on repository for running [WAHA](https://waha.devlike.pro/) — a self-hosted WhatsApp HTTP API — on Home Assistant OS.

This repo is intended for a small, dedicated WhatsApp automation workload such as posting new nonprofit/blog announcements to a WhatsApp Channel through a dedicated WhatsApp number.

> **Important:** WAHA uses unofficial WhatsApp Web-style automation. That is not the same as Meta's official WhatsApp Business Cloud API and may violate WhatsApp's terms. Use a dedicated number that you can afford to lose; do not use your nonprofit's primary contact number.

## Add this repository to Home Assistant

1. Fork or copy this repo to your GitHub account.
2. In Home Assistant: **Settings → Add-ons → Add-on Store → ⋮ → Repositories**.
3. Paste your repo URL, for example:

   ```text
   https://github.com/ofa1/ha-waha-addon
   ```

4. Install **WAHA WhatsApp API**.
5. Open the add-on configuration. You may leave `api_key` and `dashboard_password` blank; the add-on auto-generates and persists them on first start. If you want to manage secrets yourself, set strong values manually.

## What this add-on does

- Uses the browserless `devlikeapro/waha:noweb-arm` image, suitable for Raspberry Pi / HAOS on ARM.
- Defaults to the **GOWS** engine, with **NOWEB** as the recommended fallback if channel posting is engine-sensitive.
- Persists WAHA sessions under `/data/.sessions`, so QR pairing survives add-on restarts and Home Assistant backups.
- Exposes WAHA on port `3000` and via Home Assistant ingress.

See [`waha/DOCS.md`](waha/DOCS.md) for setup, security, Cloudflare Tunnel notes, and channel-post testing.
