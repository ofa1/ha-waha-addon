#!/bin/sh
set -eu

OPTIONS_FILE=/data/options.json

if [ ! -f "$OPTIONS_FILE" ]; then
  echo "ERROR: Home Assistant options file not found at $OPTIONS_FILE" >&2
  exit 1
fi

# Parse Home Assistant add-on options with Node, which is present in the WAHA image.
# Output shell-safe KEY=VALUE assignments without printing secret values to logs.
eval "$(node <<'NODE'
const fs = require('fs');
const options = JSON.parse(fs.readFileSync('/data/options.json', 'utf8'));
function shellQuote(value) {
  return "'" + String(value ?? '').replace(/'/g, "'\\''") + "'";
}
const env = {
  WAHA_API_KEY: options.api_key,
  WAHA_DASHBOARD_ENABLED: options.dashboard_enabled ? 'true' : 'false',
  WAHA_DASHBOARD_USERNAME: options.dashboard_username,
  WAHA_DASHBOARD_PASSWORD: options.dashboard_password,
  WHATSAPP_DEFAULT_ENGINE: options.default_engine || 'GOWS',
  WAHA_LOCAL_STORE_BASE_DIR: options.local_store_base_dir || '/data/.sessions',
  WAHA_LOG_LEVEL: options.log_level || 'info',
  TZ: options.timezone || 'UTC',
};
for (const [key, value] of Object.entries(env)) {
  console.log(`export ${key}=${shellQuote(value)}`);
}
NODE
)"

case "${WAHA_API_KEY:-}" in
  ""|CHANGE_ME*)
    echo "ERROR: Set a strong WAHA API key in the add-on configuration before starting." >&2
    echo "Example: openssl rand -hex 32" >&2
    exit 1
    ;;
esac

case "${WAHA_DASHBOARD_PASSWORD:-}" in
  ""|CHANGE_ME*)
    echo "ERROR: Set a strong WAHA dashboard password in the add-on configuration before starting." >&2
    echo "Example: openssl rand -hex 32" >&2
    exit 1
    ;;
esac

mkdir -p "$WAHA_LOCAL_STORE_BASE_DIR"

echo "Starting WAHA with engine=${WHATSAPP_DEFAULT_ENGINE}, store=${WAHA_LOCAL_STORE_BASE_DIR}, dashboard_enabled=${WAHA_DASHBOARD_ENABLED}"

exec /entrypoint.sh
