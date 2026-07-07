# Changelog

All notable changes to the WAHA WhatsApp API Home Assistant add-on are documented here.

## 0.1.2 - 2026-07-06

- Add this changelog so Home Assistant no longer reports "No changelog found" for the add-on.

## 0.1.1 - 2026-07-06

- Disable direct host port `3000` by default to avoid conflicts with other Home Assistant add-ons or services.
- Keep Home Assistant ingress enabled for browser access to the WAHA dashboard/API.
- Document that direct host port exposure is optional and should not be exposed publicly.

## 0.1.0 - 2026-07-06

- Initial WAHA Home Assistant add-on.
- Use `devlikeapro/waha:noweb-arm` as the base image.
- Persist WAHA sessions under `/data/.sessions`.
- Auto-generate local WAHA API key and dashboard password on first start when left blank.
- Add documentation for WhatsApp Channel testing and Cloudflare Tunnel usage.
