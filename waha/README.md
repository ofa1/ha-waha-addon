# WAHA WhatsApp API

Runs [WAHA](https://waha.devlike.pro/) inside Home Assistant OS as a managed add-on.

## Credentials

There are no external vendor API keys required for WAHA itself.

The add-on needs two local secrets only:

- `api_key` — protects WAHA's HTTP API (`X-Api-Key`).
- `dashboard_password` — protects the WAHA web dashboard.

Leave both fields blank to auto-generate 256-bit random values on first start. The generated values are saved under `/data/.secrets.env`, which persists across add-on restarts and is included in HA backups. On the first start only, the add-on prints the generated values to the add-on log so you can copy them into your Worker or password manager. Treat that log as sensitive.

If you prefer to manage or rotate credentials yourself, set either field explicitly in the add-on configuration. Generate strong values with:

```bash
openssl rand -hex 32
```

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
