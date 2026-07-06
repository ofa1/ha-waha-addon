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
  fi
  WAHA_API_KEY="$GENERATED_WAHA_API_KEY"
fi

if [ -n "${CONFIG_DASHBOARD_PASSWORD:-}" ]; then
  WAHA_DASHBOARD_PASSWORD="$CONFIG_DASHBOARD_PASSWORD"
else
  if [ -z "${GENERATED_WAHA_DASHBOARD_PASSWORD:-}" ]; then
    GENERATED_WAHA_DASHBOARD_PASSWORD="$(generate_secret)"
    UPDATED_SECRETS=1
  fi
  WAHA_DASHBOARD_PASSWORD="$GENERATED_WAHA_DASHBOARD_PASSWORD"
fi

if [ "${UPDATED_SECRETS:-0}" = "1" ]; then
  umask 077
  cat > "$SECRETS_FILE" <<EOF
GENERATED_WAHA_API_KEY='$GENERATED_WAHA_API_KEY'
GENERATED_WAHA_DASHBOARD_PASSWORD='$GENERATED_WAHA_DASHBOARD_PASSWORD'
EOF
  echo "Generated WAHA credentials and saved them to $SECRETS_FILE."
  echo "Copy these now from the add-on log, then clear/download logs according to your HA security preference:"
  echo "  Dashboard username: $CONFIG_DASHBOARD_USERNAME"
  echo "  Dashboard password: $GENERATED_WAHA_DASHBOARD_PASSWORD"
  echo "  API key: $GENERATED_WAHA_API_KEY"
fi

export WAHA_API_KEY
export WAHA_DASHBOARD_ENABLED="$CONFIG_DASHBOARD_ENABLED"
export WAHA_DASHBOARD_USERNAME="$CONFIG_DASHBOARD_USERNAME"
export WAHA_DASHBOARD_PASSWORD
export WHATSAPP_DEFAULT_ENGINE="$CONFIG_DEFAULT_ENGINE"
export WAHA_LOCAL_STORE_BASE_DIR="$CONFIG_LOCAL_STORE_BASE_DIR"
export WAHA_LOG_LEVEL="$CONFIG_LOG_LEVEL"
export TZ="$CONFIG_TZ"

mkdir -p "$WAHA_LOCAL_STORE_BASE_DIR"

echo "Starting WAHA with engine=${WHATSAPP_DEFAULT_ENGINE}, store=${WAHA_LOCAL_STORE_BASE_DIR}, dashboard_enabled=${WAHA_DASHBOARD_ENABLED}"
echo "WAHA API key and dashboard password are set. Values are intentionally not printed."

exec /entrypoint.sh
