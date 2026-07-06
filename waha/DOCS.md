# WAHA Home Assistant Add-on Docs

## Security model

WAHA is powerful: anyone with access to the API/dashboard can send WhatsApp messages as the paired number.

Minimum recommendations:

1. Use a dedicated WhatsApp number for automation.
2. Let the add-on auto-generate its local secrets, or set strong unique values yourself:
   - `api_key` protects the HTTP API via `X-Api-Key`.
   - `dashboard_password` protects the WAHA dashboard.
3. The auto-generated values live in `/data/.secrets.env`; treat that file, first-start logs, and HA backups as sensitive.
4. Do **not** expose port `3000` directly to the public internet.
5. If exposing via Cloudflare Tunnel, put Cloudflare Access in front of the route.
6. Use the API key on all automation calls:

   ```http
   X-Api-Key: YOUR_API_KEY
   ```

## Resource expectations

For a single paired number/session on a Raspberry Pi:

| Engine | Browser? | Approx footprint | Notes |
|---|---:|---:|---|
| GOWS | No | ~200 MB RAM / ~0.1 CPU | Recommended first try |
| NOWEB | No | ~200 MB RAM / ~0.1 CPU | Good fallback |
| WEBJS | Yes / Chromium | ~400 MB RAM / ~0.3 CPU | Avoid unless needed |

## Channel posting test

After pairing the dedicated WhatsApp number and making it a Channel admin, test a real Channel post before building the RSS automation.

Replace values:

```bash
WAHA_URL="http://homeassistant.local:3000"
WAHA_API_KEY="your_api_key"
CHANNEL_ID="123456789012345678@newsletter"
```

Send text:

```bash
curl -fsS "$WAHA_URL/api/sendText" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $WAHA_API_KEY" \
  -d "{\"session\":\"default\",\"chatId\":\"$CHANNEL_ID\",\"text\":\"Test post from WAHA on HAOS\"}"
```

A successful HTTP response is not enough: visually confirm the post appears in the Channel. If WAHA returns success but nothing appears:

1. Switch `default_engine` from `GOWS` to `NOWEB`.
2. Restart the add-on.
3. Re-pair or restart the WAHA session if needed.
4. Test again.

## Finding the Channel ID

WhatsApp Channel IDs usually end with:

```text
@newsletter
```

Depending on WAHA version/engine, you may be able to discover chats through WAHA's dashboard/API after the paired number is a Channel admin. If discovery is unreliable, use WAHA logs/dashboard or a temporary manual lookup flow and save the confirmed `@newsletter` ID for the Worker.

## Cloudflare Tunnel pattern

Recommended architecture:

```text
Cloudflare Worker cron
  -> Cloudflare Tunnel + Access
  -> HAOS WAHA add-on on port 3000
  -> WhatsApp Channel
```

Do not expose WAHA publicly without Access or another strong auth layer. The WAHA API key is necessary but should not be your only public-facing protection.

## Pinning WAHA versions

The Dockerfile currently uses:

```dockerfile
FROM devlikeapro/waha:noweb-arm
```

That keeps the image current, which is useful while WAHA channel support is evolving. Once you verify a version that posts to Channels reliably, pin the Dockerfile to a specific WAHA tag to avoid surprise breakage.
