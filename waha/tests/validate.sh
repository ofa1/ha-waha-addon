#!/usr/bin/env bash
#
# Pre-deploy validation for the WAHA add-on.
#
# Run it locally before bumping `version:` in config.yaml, or let CI run it.
# Every assertion here corresponds to a bug that actually shipped and took the
# add-on down; see CHANGELOG.md for the incidents.
#
#   ./waha/tests/validate.sh
#
set -euo pipefail

ADDON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
NGINX_PORT=18099
BACKEND_PORT=13000
FAILURES=0

cleanup() {
  [ -f "$WORK/nginx.pid" ] && kill "$(cat "$WORK/nginx.pid")" 2>/dev/null || true
  if [ -n "${BACKEND_PID:-}" ]; then
    kill "$BACKEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
  fi
  rm -rf "$WORK"
}
trap cleanup EXIT

pass() { printf '  \033[32mok\033[0m   %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
step() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# ---------------------------------------------------------------- shell syntax

step "run.sh"

# The container runs this under BusyBox/dash `sh`, not bash. Bash 3.2 chokes on
# the heredoc-inside-command-substitution that parses fine under a POSIX sh, so
# check with dash where available and fall back to whatever /bin/sh is.
SH_BIN="$(command -v dash || command -v sh)"
if "$SH_BIN" -n "$ADDON_DIR/run.sh"; then
  pass "parses under $SH_BIN"
else
  fail "syntax error"
fi

# 0.1.9: a failing `nginx -t` under `set -e` killed an already-running WAHA.
# The config test must come before the WAHA entrypoint.
nginx_test_line=$(grep -n 'nginx -t' "$ADDON_DIR/run.sh" | head -1 | cut -d: -f1)
entrypoint_line=$(grep -n '^/entrypoint.sh' "$ADDON_DIR/run.sh" | head -1 | cut -d: -f1)
if [ "$nginx_test_line" -lt "$entrypoint_line" ]; then
  pass "nginx -t runs before /entrypoint.sh"
else
  fail "nginx -t runs AFTER /entrypoint.sh — a bad config would kill a live session"
fi

# 0.2.1: WAHA prints any credential it generates itself. Supplying one is the
# only thing that stops it, and it must not be the dashboard password.
if grep -q 'export WHATSAPP_SWAGGER_PASSWORD=' "$ADDON_DIR/run.sh"; then
  pass "swagger password is supplied (stops WAHA generating and logging one)"
else
  fail "swagger password not supplied — WAHA will generate and log its own"
fi
if grep -q 'export WHATSAPP_SWAGGER_PASSWORD="\$GENERATED_WAHA_SWAGGER_PASSWORD"' "$ADDON_DIR/run.sh"; then
  pass "swagger password is a dedicated secret, not the dashboard password"
else
  fail "swagger password should be GENERATED_WAHA_SWAGGER_PASSWORD"
fi

# ------------------------------------------------------------------ manifests

step "config.yaml / Dockerfile"

version=$(grep '^version:' "$ADDON_DIR/config.yaml" | sed 's/.*"\(.*\)".*/\1/')
if [ -n "$version" ]; then
  pass "version: $version"
else
  fail "could not read version"
fi

# Stops a deploy that has no changelog entry, which is how a rollback target
# gets lost.
if head -20 "$ADDON_DIR/CHANGELOG.md" | grep -q "^## $version "; then
  pass "CHANGELOG.md has an entry for $version"
else
  fail "CHANGELOG.md has no '## $version' entry near the top"
fi

# 0.2.0: a floating tag plus auto_update let the Supervisor pull an untested
# upstream WAHA unprompted.
base=$(grep '^FROM ' "$ADDON_DIR/Dockerfile" | awk '{print $2}')
if printf '%s' "$base" | grep -Eq '(@sha256:[0-9a-f]{64}|:[a-z-]*[0-9]{4}\.[0-9]+\.[0-9]+)$'; then
  pass "base image is pinned: $base"
else
  fail "base image is not pinned to a version or digest: $base"
fi

if grep -q 'COPY channel-test.html' "$ADDON_DIR/Dockerfile"; then
  pass "channel-test.html is copied into the image"
else
  fail "channel-test.html missing from Dockerfile — /channel-test/ would 404"
fi

# ---------------------------------------------------------- page JS is parseable

step "channel-test.html"

sed -n '/^<script>/,/^<\/script>/p' "$ADDON_DIR/channel-test.html" \
  | sed '1d;$d' > "$WORK/page.js"
if command -v node >/dev/null 2>&1; then
  if node --check "$WORK/page.js" 2>"$WORK/js.err"; then
    pass "inline JS parses"
  else
    fail "inline JS syntax error: $(cat "$WORK/js.err")"
  fi
else
  printf '  skip node not available\n'
fi

# ------------------------------------------------------------- nginx behaviour

step "ingress.conf.template"

NGINX_BIN=""
for candidate in "$(command -v nginx || true)" /usr/sbin/nginx /opt/homebrew/bin/nginx /usr/local/bin/nginx; do
  [ -n "$candidate" ] && [ -x "$candidate" ] && NGINX_BIN="$candidate" && break
done
if [ -z "$NGINX_BIN" ]; then
  fail "nginx not found — install it (apt-get install nginx / brew install nginx)"
  exit 1
fi
for candidate in /etc/nginx/mime.types /opt/homebrew/etc/nginx/mime.types /usr/local/etc/nginx/mime.types; do
  [ -f "$candidate" ] && MIME_TYPES="$candidate" && break
done

mkdir -p "$WORK/www"
cp "$ADDON_DIR/channel-test.html" "$WORK/www/"

# Render exactly like run.sh does, then redirect the container-only bits
# (ports, the Supervisor-gateway ACL, absolute paths) at the test rig.
sed \
  -e "s#__WAHA_BASIC_AUTH__#Basic dGVzdDp0ZXN0#" \
  -e "s#__WAHA_API_KEY__#$(printf 'a%.0s' $(seq 64))#" \
  -e "s#pid /tmp/nginx.pid;#pid $WORK/nginx.pid;#" \
  -e "s#^daemon off;#daemon on;#" \
  -e "s#^error_log /dev/stdout info;#error_log $WORK/error.log info;#" \
  -e "s#access_log /dev/stdout;#access_log $WORK/access.log;#" \
  -e "s#include /etc/nginx/mime.types;#include $MIME_TYPES;#" \
  -e "s#root /usr/share/waha-ingress;#root $WORK/www;#" \
  -e "s#allow 172.30.32.2;#allow 127.0.0.1;#" \
  -e "s#listen \[::\]:8099 default_server;##" \
  -e "s#listen 8099 default_server;#listen $NGINX_PORT default_server;#" \
  -e "s#server 127.0.0.1:3000;#server 127.0.0.1:$BACKEND_PORT;#" \
  "$ADDON_DIR/ingress.conf.template" > "$WORK/nginx.conf"

# 0.1.8: the page was inlined as one 4936-byte quoted token and blew past
# nginx's 4096-byte config token buffer, aborting `nginx -t`.
if "$NGINX_BIN" -t -c "$WORK/nginx.conf" -p "$WORK" 2>"$WORK/nginx.err"; then
  pass "nginx -t passes"
else
  fail "nginx -t failed:"
  sed 's/^/       /' "$WORK/nginx.err"
  exit 1
fi
if grep -q '\[warn\]' "$WORK/nginx.err"; then
  fail "nginx emitted warnings:"
  grep '\[warn\]' "$WORK/nginx.err" | sed 's/^/       /'
else
  pass "no nginx warnings"
fi

# A stub upstream whose JSON body legitimately contains the strings the
# dashboard rewrite rules look for.
cat > "$WORK/backend.py" <<PY
import http.server
BODY = b'{"text":"see \\"/api/docs and \\"/dashboard tips"}'
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(BODY)))
        self.end_headers()
        self.wfile.write(BODY)
    def log_message(self, *a): pass
http.server.HTTPServer(("127.0.0.1", $BACKEND_PORT), H).serve_forever()
PY
python3 "$WORK/backend.py" &
BACKEND_PID=$!
"$NGINX_BIN" -c "$WORK/nginx.conf" -p "$WORK" 2>/dev/null

for _ in $(seq 50); do
  curl -fsS --max-time 1 -o /dev/null "http://127.0.0.1:$BACKEND_PORT/" 2>/dev/null && break
  sleep 0.1
done

get()      { curl -sS -H 'X-Ingress-Path: /PFX' "http://127.0.0.1:$NGINX_PORT$1"; }
head_of()  { curl -sSi -H 'X-Ingress-Path: /PFX' "http://127.0.0.1:$NGINX_PORT$1"; }
status_of(){ curl -sS -o /dev/null -w '%{http_code}' -H 'X-Ingress-Path: /PFX' "http://127.0.0.1:$NGINX_PORT$1"; }

step "routing"

# 0.2.0: sub_filter was applied to application/json from /api, so any response
# body containing "/api or "/dashboard — a WhatsApp message mentioning either —
# came back silently rewritten.
for path in /api /api/sendText "/api/sessions?all=true"; do
  if get "$path" | grep -q '/PFX'; then
    fail "$path was rewritten — API response bodies are being corrupted"
  else
    pass "$path proxied verbatim"
  fi
done

# 0.2.2: `^~ /api` also swallowed /apidocs, which is Swagger HTML and *does*
# need the ingress prefix to render.
for path in /apidocs /dashboard/x; do
  if get "$path" | grep -q '/PFX'; then
    pass "$path rewritten for ingress"
  else
    fail "$path was NOT rewritten — assets would escape the ingress prefix"
  fi
done

# 0.1.10: `alias <file>` in a location whose URI ends in `/` made nginx append
# the index name to the alias value, returning HTTP 500.
code=$(status_of /channel-test/)
if [ "$code" = "200" ]; then
  pass "/channel-test/ returns 200"
else
  fail "/channel-test/ returned $code (expected 200)"
fi

if head_of /channel-test/ | grep -qi '^content-security-policy:'; then
  pass "/channel-test/ sends a CSP"
else
  fail "/channel-test/ has no Content-Security-Policy header"
fi

# HA renders the add-on panel in an iframe; framing must stay permitted.
if head_of /channel-test/ | grep -qiE '^(x-frame-options:|content-security-policy:.*frame-ancestors)'; then
  fail "framing is restricted — this breaks the Home Assistant ingress panel"
else
  pass "framing not restricted (required for the HA ingress iframe)"
fi

# 0.2.3: the Docker HEALTHCHECK drives the Supervisor watchdog, so a broken
# /healthz means the add-on restart-loops or never recovers.
code=$(status_of /healthz)
if [ "$code" = "200" ]; then
  pass "/healthz returns 200 from loopback"
else
  fail "/healthz returned $code (expected 200) — the watchdog would flap"
fi
if grep -q 'HEALTHCHECK' "$ADDON_DIR/Dockerfile"; then
  pass "Dockerfile declares a HEALTHCHECK"
else
  fail "no HEALTHCHECK — the Supervisor watchdog has nothing to read"
fi

# 0.1.5 / 0.1.7: the panel opens at `/` and redirects must stay relative.
code=$(status_of /)
if [ "$code" = "302" ]; then
  pass "/ redirects to the dashboard"
else
  fail "/ returned $code (expected 302)"
fi
location=$(head_of / | grep -i '^location:' | tr -d '\r')
if printf '%s' "$location" | grep -q '/PFX/dashboard/'; then
  pass "redirect carries the ingress prefix"
else
  fail "redirect lost the ingress prefix: $location"
fi

# The browser must never receive the credentials nginx injects upstream.
if head_of /channel-test/ | grep -qiE '^(x-api-key|authorization):'; then
  fail "credentials are leaking to the browser"
else
  pass "no credentials in responses to the browser"
fi

step "result"
if [ "$FAILURES" -eq 0 ]; then
  printf '\033[32mAll checks passed.\033[0m\n'
else
  printf '\033[31m%d check(s) failed.\033[0m\n' "$FAILURES"
  exit 1
fi
