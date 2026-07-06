# WAHA WhatsApp API

Runs [WAHA](https://waha.devlike.pro/) inside Home Assistant OS as a managed add-on.

## Before starting

Open the add-on **Configuration** tab and replace:

- `api_key`
- `dashboard_password`

Generate strong values with:

```bash
openssl rand -hex 32
```

The add-on refuses to start while either value still starts with `CHANGE_ME`.

## Recommended settings

- `default_engine: GOWS` — lightweight, browserless, recommended first try for channel posting.
- If a WhatsApp Channel send returns success but does not appear, try `default_engine: NOWEB` and restart.
- Keep `local_store_base_dir: /data/.sessions` so the WhatsApp QR/session survives restarts and HA backups.

## Pairing

1. Start the add-on.
2. Open the WAHA web UI.
3. Create/start the default session if needed.
4. Scan the QR code with a dedicated WhatsApp number.
5. Make that number an admin of the WhatsApp Channel you want to post to.

See `DOCS.md` for API tests and Cloudflare Tunnel notes.
