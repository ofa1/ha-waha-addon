#!/usr/bin/env bash
set -euo pipefail

addon_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
version=$(sed -n 's/^version: "\([^"]*\)"$/\1/p' "$addon_dir/config.yaml")
work=$(mktemp -d)
name="waha-arm-${work##*.}"
image="waha-arm-smoke:${work##*.}"

cleanup() {
  if [ "$?" -ne 0 ]; then
    docker logs "$name" >&2 || true
  fi
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker network rm "$name" >/dev/null 2>&1 || true
  docker image rm "$image" >/dev/null 2>&1 || true
  rm -rf "$work"
}
trap cleanup EXIT

docker build --pull --platform linux/arm64 --tag "$image" \
  --build-arg BUILD_VERSION="$version" --build-arg BUILD_ARCH=aarch64 "$addon_dir"

# No persisted session or external network. The probe uses Supervisor's ingress
# source address so the production Nginx access rules can stay untouched.
printf '%s\n' '{"api_key":"smoke-test-key","dashboard_password":"smoke-test-password","default_engine":"GOWS"}' \
  > "$work/options.json"
docker network create --internal --subnet 172.30.32.0/24 "$name" >/dev/null
docker run -d --name "$name" --network "$name" --ip 172.30.32.3 \
  --platform linux/arm64 --tmpfs /data \
  --mount "type=bind,src=$work/options.json,dst=/data/options.json,readonly" "$image" >/dev/null

docker run --rm -i --network "$name" --ip 172.30.32.2 --platform linux/arm64 \
  --entrypoint node "$image" --input-type=module - <<'JS'
import { setTimeout as delay } from 'node:timers/promises';

const deadline = Date.now() + 30_000;
let lastError;
while (Date.now() < deadline) {
  try {
    // No client API key: the add-on's proxy injects it.
    const response = await fetch('http://172.30.32.3:8099/api/server/version', {
      redirect: 'manual', signal: AbortSignal.timeout(2_000),
    });
    if (response.status !== 200) throw new Error(`Ingress returned HTTP ${response.status}`);
    const { version, engine } = await response.json();
    if (typeof version !== 'string' || !version || engine !== 'GOWS') {
      throw new Error(`Expected WAHA version and GOWS engine, got ${version} / ${engine}`);
    }
    console.log(`WAHA ${version} (${engine}) responded through add-on ingress`);
    lastError = undefined;
    break;
  } catch (error) {
    lastError = error;
    await delay(1_000);
  }
}
if (lastError) throw lastError;
JS
