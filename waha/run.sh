#!/bin/sh
set -eu

OPTIONS_FILE=/data/options.json
SECRETS_FILE=/data/.secrets.env

if [ ! -f "$OPTIONS_FILE" ]; then
  echo "ERROR: Home Assistant options file not found at $OPTIONS_FILE" >&2
  exit 1
fi

generate_secret() {
  # 256-bit random hex token. Prefer OpenSSL, fall back to /dev/urandom.
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
  fi
}

# Load generated credentials from previous starts, if any.
GENERATED_WAHA_API_KEY=""
GENERATED_WAHA_DASHBOARD_PASSWORD=""
GENERATED_WAHA_SWAGGER_PASSWORD=""
if [ -f "$SECRETS_FILE" ]; then
  # shellcheck disable=SC1090
  . "$SECRETS_FILE"
fi

# Parse Home Assistant add-on options with Node, which is present in the WAHA image.
# Output shell-safe KEY=VALUE assignments without printing secret values to logs.
eval "$(node <<'NODE'
const fs = require('fs');
const options = JSON.parse(fs.readFileSync('/data/options.json', 'utf8'));
function shellQuote(value) {
  return "'" + String(value ?? '').replace(/'/g, "'\\''") + "'";
}
const opt = {
  CONFIG_API_KEY: options.api_key || '',
  CONFIG_DASHBOARD_ENABLED: options.dashboard_enabled ? 'true' : 'false',
  CONFIG_DASHBOARD_USERNAME: options.dashboard_username || 'admin',
  CONFIG_DASHBOARD_PASSWORD: options.dashboard_password || '',
  CONFIG_SWAGGER_ENABLED: options.swagger_enabled ? 'true' : 'false',
  CONFIG_DEFAULT_ENGINE: options.default_engine || 'GOWS',
  CONFIG_LOCAL_STORE_BASE_DIR: options.local_store_base_dir || '/data/.sessions',
  CONFIG_LOG_LEVEL: options.log_level || 'info',
  CONFIG_TZ: options.timezone || 'UTC',
};
for (const [key, value] of Object.entries(opt)) {
  console.log(`export ${key}=${shellQuote(value)}`);
}
NODE
)"

# If secrets are not supplied in the add-on UI, generate once and persist in /data.
# /data survives add-on restarts and is included in HA backups.
if [ -n "${CONFIG_API_KEY:-}" ]; then
  WAHA_API_KEY="$CONFIG_API_KEY"
else
  if [ -z "${GENERATED_WAHA_API_KEY:-}" ]; then
    GENERATED_WAHA_API_KEY="$(generate_secret)"
    UPDATED_SECRETS=1
    NEW_API_KEY=1
  fi
  WAHA_API_KEY="$GENERATED_WAHA_API_KEY"
fi

if [ -n "${CONFIG_DASHBOARD_PASSWORD:-}" ]; then
  WAHA_DASHBOARD_PASSWORD="$CONFIG_DASHBOARD_PASSWORD"
else
  if [ -z "${GENERATED_WAHA_DASHBOARD_PASSWORD:-}" ]; then
    GENERATED_WAHA_DASHBOARD_PASSWORD="$(generate_secret)"
    UPDATED_SECRETS=1
    NEW_DASHBOARD_PASSWORD=1
  fi
  WAHA_DASHBOARD_PASSWORD="$GENERATED_WAHA_DASHBOARD_PASSWORD"
fi

# WAHA prints any credential it had to generate itself into the add-on log on
# every start, in a "Generated credentials" banner. That is how a Swagger
# password ended up in plaintext in the Supervisor log.
#
# Setting WHATSAPP_SWAGGER_ENABLED=false does NOT suppress this — verified on
# 0.2.0, where WAHA still generated and printed a Swagger password with Swagger
# disabled. The only thing that stops it is supplying one, so generate a
# dedicated value unconditionally. It is deliberately NOT the dashboard
# password or the API key, so even if a future WAHA echoes it back, a leak
# there cannot escalate into WAHA API access.
if [ -z "$GENERATED_WAHA_SWAGGER_PASSWORD" ]; then
  GENERATED_WAHA_SWAGGER_PASSWORD="$(generate_secret)"
  UPDATED_SECRETS=1
fi

if [ "${UPDATED_SECRETS:-0}" = "1" ]; then
  umask 077
  cat > "$SECRETS_FILE" <<EOF
GENERATED_WAHA_API_KEY='$GENERATED_WAHA_API_KEY'
GENERATED_WAHA_DASHBOARD_PASSWORD='$GENERATED_WAHA_DASHBOARD_PASSWORD'
GENERATED_WAHA_SWAGGER_PASSWORD='$GENERATED_WAHA_SWAGGER_PASSWORD'
EOF
  echo "Generated WAHA credentials and saved them to $SECRETS_FILE."
  # Print only what was generated on THIS start. Re-printing an unchanged
  # secret (for example when Swagger is switched on later) would copy it into
  # the add-on log all over again for no reason.
  if [ "${NEW_DASHBOARD_PASSWORD:-0}" = "1" ] || [ "${NEW_API_KEY:-0}" = "1" ]; then
    echo "Copy these now from the add-on log, then clear/download logs according to your HA security preference:"
    if [ "${NEW_DASHBOARD_PASSWORD:-0}" = "1" ]; then
      echo "  Dashboard username: $CONFIG_DASHBOARD_USERNAME"
      echo "  Dashboard password: $GENERATED_WAHA_DASHBOARD_PASSWORD"
    fi
    if [ "${NEW_API_KEY:-0}" = "1" ]; then
      echo "  API key: $GENERATED_WAHA_API_KEY"
    fi
  fi
  # The Swagger password is never printed. It is recoverable from
  # $SECRETS_FILE, and nothing outside the container needs it.
fi

export WAHA_API_KEY
export WAHA_DASHBOARD_ENABLED="$CONFIG_DASHBOARD_ENABLED"
export WAHA_DASHBOARD_USERNAME="$CONFIG_DASHBOARD_USERNAME"
export WAHA_DASHBOARD_PASSWORD
export WHATSAPP_SWAGGER_ENABLED="$CONFIG_SWAGGER_ENABLED"
# Always supplied, even when Swagger is disabled — see the note above.
export WHATSAPP_SWAGGER_USERNAME="$CONFIG_DASHBOARD_USERNAME"
export WHATSAPP_SWAGGER_PASSWORD="$GENERATED_WAHA_SWAGGER_PASSWORD"
export WHATSAPP_DEFAULT_ENGINE="$CONFIG_DEFAULT_ENGINE"
export WAHA_LOCAL_STORE_BASE_DIR="$CONFIG_LOCAL_STORE_BASE_DIR"
export WAHA_LOG_LEVEL="$CONFIG_LOG_LEVEL"
export TZ="$CONFIG_TZ"

mkdir -p "$WAHA_LOCAL_STORE_BASE_DIR"

WAHA_BASIC_AUTH="Basic $(node -e "process.stdout.write(Buffer.from(process.argv[1] + ':' + process.argv[2]).toString('base64'))" "$CONFIG_DASHBOARD_USERNAME" "$WAHA_DASHBOARD_PASSWORD")"
export WAHA_BASIC_AUTH

# Render the ingress proxy config without printing secrets. The proxy is only
# reachable from Home Assistant's ingress gateway and injects WAHA credentials
# internally, so users do not see a second Basic Auth prompt inside HA.
node <<'NODE'
const fs = require('fs');
const templatePath = '/etc/nginx/templates/waha-ingress.conf.template';
const outputPath = '/tmp/waha-ingress.conf';
const template = fs.readFileSync(templatePath, 'utf8');
const rendered = template
  .replaceAll('__WAHA_BASIC_AUTH__', process.env.WAHA_BASIC_AUTH || '')
  .replaceAll('__WAHA_API_KEY__', process.env.WAHA_API_KEY || '');
fs.writeFileSync(outputPath, rendered, { mode: 0o600 });
NODE

echo "Starting WAHA with engine=${WHATSAPP_DEFAULT_ENGINE}, store=${WAHA_LOCAL_STORE_BASE_DIR}, dashboard_enabled=${WAHA_DASHBOARD_ENABLED}, swagger_enabled=${WHATSAPP_SWAGGER_ENABLED}"
echo "WAHA API key and dashboard password are set. Values are intentionally not printed."

# Validate the proxy config BEFORE bringing WhatsApp up. This script runs under
# `set -e`, so a failing `nginx -t` aborts it; doing that first means a bad
# config fails cleanly instead of tearing down an already-connected session.
nginx -t -c /tmp/waha-ingress.conf
echo "Starting Home Assistant ingress proxy on port 8099."

/entrypoint.sh &
WAHA_PID=$!

nginx -c /tmp/waha-ingress.conf &
NGINX_PID=$!

term_handler() {
  echo "Stopping WAHA and ingress proxy..."
  kill "$WAHA_PID" "$NGINX_PID" 2>/dev/null || true
}
trap term_handler TERM INT

while :; do
  if ! kill -0 "$WAHA_PID" 2>/dev/null; then
    wait "$WAHA_PID"
    exit $?
  fi
  if ! kill -0 "$NGINX_PID" 2>/dev/null; then
    wait "$NGINX_PID"
    exit $?
  fi
  sleep 2
done
