#!/usr/bin/env bash
set -euo pipefail

# Read-only verification of Shield's admin exporter-status readback.
# The active systemd EnvironmentFile is authoritative; never print credentials.

if [[ "$(id -u)" -ne 0 ]]; then
  exec sudo -- "$0" "$@"
fi

UNIT="${SHIELD_BACKEND_UNIT:-xibalba-shield-backend.service}"
ENV_FILE="${SHIELD_BACKEND_ENV:-/etc/xibalba-shield/backend.env}"
DEVICE_CONFIG="${SHIELD_DEVICE_CONFIG:-/home/xibalba/.xibalba-shield/device.json}"
BASE_URL="${SHIELD_URL:-http://127.0.0.1:8421}/api/shield/exporter-status"

state="$(systemctl show "$UNIT" -p ActiveState --value 2>/dev/null || true)"
[[ "$state" == "active" ]] || { echo "backend=not-active state=${state:-unknown}"; exit 1; }
[[ -r "$ENV_FILE" ]] || { echo "backend-env=unreadable path=$ENV_FILE"; exit 1; }

token="$(awk -F= '$1 == "SHIELD_BACKEND_TOKEN" {sub(/^[^=]*=/, ""); print; exit}' "$ENV_FILE")"
[[ -n "$token" ]] || { echo "backend-token=missing-in-active-environment"; exit 1; }

if [[ -n "${SHIELD_TENANT_ID:-}" ]]; then
  tenant_id="$SHIELD_TENANT_ID"
elif [[ -r "$DEVICE_CONFIG" ]] && command -v jq >/dev/null 2>&1; then
  tenant_id="$(jq -r '.tenant_id // empty' "$DEVICE_CONFIG")"
else
  tenant_id=""
fi
[[ -n "$tenant_id" ]] || { echo "tenant-id=missing-set-SHIELD_TENANT_ID"; exit 1; }

url="${BASE_URL}?tenant_id=$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$tenant_id")"

response="$(printf 'header = "Authorization: Bearer %s"\nurl = "%s"\n' "$token" "$url" |
  curl --config - --fail --silent --show-error --max-time 10)"

if command -v jq >/dev/null 2>&1 && jq -e '.ok == true' >/dev/null 2>&1 <<<"$response"; then
  echo "admin_correlation=CONFIRMED_HTTP_200"
else
  echo "admin_correlation=unexpected_response"
  exit 1
fi
