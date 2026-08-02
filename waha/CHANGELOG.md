# Changelog

All notable changes to the WAHA WhatsApp API Home Assistant add-on are documented here.

## 0.1.9 - 2026-08-01

- Fix the add-on failing to start since 0.1.8. The `/channel-test/` page was inlined in the Nginx config as a single 4,936-byte quoted string, which overran Nginx's 4096-byte config token buffer and aborted `nginx -t` with `too long parameter, probably missing terminating "'" character`. Because `run.sh` runs under `set -e`, that config test failure terminated the whole container, taking WAHA down with it.
- Serve `/channel-test/` as a static file (`channel-test.html`) instead. This also avoids Nginx's script engine trying to interpolate the `$` characters inside the page's JavaScript regexes, which would have failed with `invalid variable name`.
- Derive the ingress prefix in the page from `window.location.pathname` rather than a templated `$ingress_path`.

## 0.1.8 - 2026-07-07

- Add a simple Home Assistant ingress-only `/channel-test/` helper page that resolves a WhatsApp Channel invite link and sends one manual test post without exposing the WAHA API key to the browser.

## 0.1.7 - 2026-07-07

- Disable Nginx absolute redirects in the ingress proxy so redirects remain relative to the Home Assistant ingress host instead of pointing browsers at the add-on's internal Docker address.

## 0.1.6 - 2026-07-07

- Rewrite WAHA dashboard's Nuxt-generated absolute `/dashboard`, `/api`, and `baseURL` references under the Home Assistant ingress prefix to fix blank pages caused by frontend assets/API calls escaping ingress.

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
