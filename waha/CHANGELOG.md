# Changelog

All notable changes to the WAHA WhatsApp API Home Assistant add-on are documented here.

## 0.1.5 - 2026-07-07

- Redirect the Home Assistant ingress root (`/`) to WAHA's dashboard path (`/dashboard/`) to avoid a blank ingress panel when WAHA serves no UI at the root path.

## 0.1.4 - 2026-07-06

- Re-enable Home Assistant ingress using an internal Nginx proxy on port `8099`.
- Disable default host-port exposure again; the optional direct `3000/tcp` mapping can remain blank when ingress works.
- Inject WAHA dashboard/API credentials inside the ingress-only proxy so Home Assistant users should not see a second Basic Auth prompt.
- Add path and redirect rewrites for WAHA dashboard assets/API calls under the Home Assistant ingress prefix.

## 0.1.3 - 2026-07-06

- Switch the add-on Web UI to direct host-port access on `3001` instead of Home Assistant ingress.
- Keep WAHA's internal container port at `3000` while avoiding conflict with existing host services.

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
