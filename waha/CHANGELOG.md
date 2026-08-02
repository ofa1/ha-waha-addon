# Changelog

All notable changes to the WAHA WhatsApp API Home Assistant add-on are documented here.

## 0.2.3 - 2026-08-01

Fixes reported by the Home Assistant add-on linter, now running in CI.

- Replace the obsolete `watchdog:` config key with a Docker `HEALTHCHECK`.
  Home Assistant reads container health for the Supervisor watchdog now. The
  probe hits a new loopback-only `/healthz` location that proxies through to
  WAHA, so "unhealthy" means WhatsApp stopped answering rather than merely that
  Nginx is still accepting sockets.
- Drop `panel_admin`, `boot` and `ingress_port`. All three were set to their
  default values. `panel_admin: true` in 0.2.0 was therefore a no-op rather
  than a hardening change; SECURITY.md has been corrected.

## 0.2.2 - 2026-08-01

- Narrow the no-rewrite API location. `location ^~ /api` also matched paths
  merely starting with `/api`, such as `/apidocs` — Swagger UI HTML, which does
  need the dashboard's path rewriting to render under ingress. Split into
  `= /api` and `^~ /api/` so only real API paths bypass `sub_filter`.

## 0.2.1 - 2026-08-01

- Actually stop the Swagger password leak. 0.2.0 assumed that disabling Swagger
  meant WAHA had no credential to generate, but a live check showed WAHA still
  generating and printing one with `WHATSAPP_SWAGGER_ENABLED=false`. The
  dedicated Swagger password is now supplied unconditionally, which is the only
  thing that stops WAHA generating its own.

## 0.2.0 - 2026-08-01

Security and robustness pass. See the new `SECURITY.md` for the full threat
model and the risks that remain.

### Fixed

- **API responses were being silently corrupted.** The `sub_filter` rules that
  rewrite the WAHA dashboard's absolute paths were applied to every proxied
  response, including `application/json` from `/api`. Any response body
  containing `"/api` or `"/dashboard` — for example a WhatsApp message whose
  text mentions one — was rewritten to include the ingress prefix. `/api` and
  `/mcp` now have their own locations and are proxied verbatim; path rewriting
  applies only to dashboard assets.
- **A WAHA-generated Swagger password was printed to the add-on log on every
  start.** WAHA prints a "Generated credentials" banner for any credential it
  had to generate itself. Swagger is now off by default (`swagger_enabled`), so
  there is nothing to generate. When enabled, the add-on supplies a dedicated
  Swagger password from `/data/.secrets.env` — deliberately not the dashboard
  password or the API key, so a leak there cannot escalate into API access.
- Generated secrets are no longer re-printed to the log on later starts. Only
  credentials created on that specific start are echoed.

### Changed

- Pin the base image to `devlikeapro/waha:noweb-arm-2026.7.2`. The floating
  `noweb-arm` tag combined with `auto_update` allowed a rebuild to pull an
  untested upstream release unprompted.
- Validate the Nginx config before starting WAHA rather than after. Under
  `set -e` a bad config aborts the script, which previously tore down an
  already-connected WhatsApp session; it now fails before WhatsApp comes up.
- Add a Supervisor watchdog (`tcp://[HOST]:8099`) so a dead ingress proxy is
  restarted instead of leaving WhatsApp silently unreachable.
- Set `panel_admin: true`. Note this governs sidebar visibility and is not a
  reliable authorization boundary; see `SECURITY.md`.
- Send `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer` on
  all responses, and a `Content-Security-Policy` on `/channel-test/`.
  `X-Frame-Options` is intentionally not set — HA renders the panel in an iframe.
- Set `server_tokens off` to stop advertising the Nginx version.
- Consolidate the proxy headers at `server` level so the API and dashboard
  locations cannot drift apart on credential injection.

### Removed

- The `addon_config` map. `run.sh` never read `/config`, so the read-write mount
  was unnecessary surface.

## 0.1.11 - 2026-08-01

- Populate the `/channel-test/` session field from `GET /api/sessions` instead of hardcoding `default`. WAHA generates session names (e.g. `session_01kwy9...`), so the hardcoded value produced a confusing `HTTP 422 Session "default" does not exist`. A single WORKING session is selected automatically; otherwise all sessions are offered as suggestions.
- Fail with a clear message when no session is selected, rather than silently retrying `default`.

## 0.1.10 - 2026-08-01

- Fix `/channel-test/` returning HTTP 500. The `alias <file>` added in 0.1.9 does not work in a location whose URI ends in `/`: Nginx treats it as a directory request and appends the index filename to the alias value, producing the bogus path `channel-test.htmlindex.html`. Serve the page with `root` + `try_files` instead, which skips index handling.
- Drop the redundant `text/html` from `sub_filter_types` (Nginx always includes it) to clear a startup warning.

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
