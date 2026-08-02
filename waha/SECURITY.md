# Security notes

WAHA can send WhatsApp messages as the paired number. Anyone who reaches its
API or dashboard has that capability. This document records the add-on's threat
model, what is actually enforced, and the risks that remain after hardening.

## What the add-on does not ask for

The Supervisor manifest requests no elevated capabilities. Confirmed on a
running instance:

| Capability | Value |
|---|---|
| `privileged` | *(empty)* |
| `full_access` | `false` |
| `host_network` / `host_pid` / `host_ipc` / `host_dbus` | `false` |
| `docker_api` | `false` |
| `hassio_api` / `homeassistant_api` / `auth_api` | `false` |
| `apparmor` | `default` |
| `protected` | `true` |

The add-on also maps no host directories. It only uses `/data`, which every
add-on gets.

## Credentials

Two secrets are generated on first start (256-bit, `openssl rand -hex 32`) and
persisted to `/data/.secrets.env` with mode `0600`:

- `api_key` — protects the HTTP API via `X-Api-Key`.
- `dashboard_password` — protects the WAHA dashboard.

A third, the Swagger password, is generated only when `swagger_enabled: true`.

Both are printed to the add-on log **once**, on the start where they are
generated, because that is the only practical way to retrieve them for an
external caller such as a Cloudflare Worker. Treat that log entry, the
`.secrets.env` file, and any Home Assistant backup as sensitive. Secrets are
never re-printed on later starts, including when Swagger is switched on.

The rendered Nginx config at `/tmp/waha-ingress.conf` contains both credentials
and is written with mode `0600`.

## Ingress proxy

Browser access goes through an internal Nginx proxy on port 8099:

- The proxy accepts connections only from `172.30.32.2`, the Home Assistant
  Supervisor ingress gateway. Everything else is denied.
- It injects the dashboard `Authorization` header and the `X-Api-Key` header
  server-side. The browser never receives either. These `proxy_set_header`
  directives also overwrite anything a client sends under the same names.
- `/api` and `/mcp` are proxied verbatim. The `sub_filter` path-rewriting rules
  apply only to dashboard assets, so API response bodies are never modified.
- `/channel-test/` is served with `Content-Security-Policy`,
  `X-Content-Type-Options: nosniff`, and `Referrer-Policy: no-referrer`.
  `X-Frame-Options` and `frame-ancestors` are deliberately omitted because Home
  Assistant renders the add-on panel inside an iframe.

## Residual risks

These are known and not fully solved by the add-on.

### WAHA's port 3000 is reachable from other containers

`ports: 3000/tcp: null` stops the port being published to the **host**. It does
not isolate it on the Docker bridge: WAHA still listens on the add-on's
container IP, and any other add-on on the `172.30.32.0/23` network can reach
`http://<addon-ip>:3000` directly, bypassing the Nginx ACL entirely.

This was verified — a request from another add-on reached WAHA and was rejected
with `HTTP 401` by WAHA's own Basic auth, so the API key and dashboard password
are what actually protect this path, not the proxy. Keep them strong, and treat
any add-on you install as having network reach to WAHA.

### Ingress access is not reliably restricted to admins

`panel_admin: true` keeps the add-on out of a non-admin user's sidebar. It is
**not** a reliable authorization boundary: Home Assistant users have reported
non-admin accounts reaching add-on ingress URLs directly despite this setting,
and Home Assistant does not enforce role-based access on the ingress path.
Because the proxy injects admin credentials, anyone who does reach the ingress
URL gets full WAHA access.

If your instance has non-admin users, verify this behaviour yourself rather than
assuming the setting protects you.

- <https://community.home-assistant.io/t/possible-bug-able-to-access-app-ingress-as-normal-user-despite-panel-admin-being-set-to-true/1018296>
- <https://github.com/home-assistant/frontend/issues/9419>

### Debug logging exposes WhatsApp metadata

At `log_level: debug` or `trace`, WAHA writes full event payloads to the add-on
log, including your phone number, LID, push name, and chat IDs. The default is
`info` for that reason. Raise it for troubleshooting, then lower it again.

### A broken proxy config still stops the add-on

`run.sh` runs under `set -e` and validates the Nginx config with `nginx -t`
before starting WAHA, so a bad config now fails before WhatsApp comes up rather
than tearing down a live session. If Nginx dies later, the supervision loop
exits and the Supervisor watchdog (`tcp://[HOST]:8099`) restarts the add-on.

WAHA is still not kept running independently of the proxy. That is a deliberate
trade-off: a running WAHA with no reachable UI is harder to notice than a
restart loop.

### Upstream image

The base image is pinned to `devlikeapro/waha:noweb-arm-2026.7.2`. It was
previously the floating `noweb-arm` tag, which combined with the add-on's
`auto_update` meant a rebuild could pull an untested upstream WAHA
unprompted. Bump the pin deliberately after reading WAHA's release notes.

## Hardening checklist

- [ ] Use a dedicated WhatsApp number, not your personal one.
- [ ] Leave `swagger_enabled` off unless you are actively using Swagger.
- [ ] Keep `log_level` at `info`.
- [ ] Leave the optional `3000/tcp` host port unmapped.
- [ ] Never expose WAHA to the internet without Cloudflare Access or equivalent
      in front of it; the API key should not be the only public-facing control.
- [ ] Rotate `api_key` and `dashboard_password` if the add-on log was ever
      shared, exported, or included in a support bundle.
