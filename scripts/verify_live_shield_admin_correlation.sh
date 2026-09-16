#!/usr/bin/env bash
set -euo pipefail

# Read-only verification of Shield's admin exporter-status readback.
# The active systemd EnvironmentFile is authoritative; never print credentials.

if [[ "$(id -u)" -ne 0 ]]; then
  exec sudo -- "$0" "$@"
fi

UNIT="${SHIELD_BACKEND_UNIT:-xibalba-shield-backend.service}"
ENV_FILE="${SHIELD_BACKEND_ENV:-/etc/xibalba-shield/backend.env}"
URL="${SHIELD_URL:-http://127.0.0.1:8421}/api/shield/exporter-status"

state="$(systemctl show "$UNIT" -p ActiveState --value 2>/dev/null || true)"
[[ "$state" == "active" ]] || { echo "backend=not-active state=${state:-unknown}"; exit 1; }
[[ -r "$ENV_FILE" ]] || { echo "backend-env=unreadable path=$ENV_FILE"; exit 1; }

token="$(awk -F= '$1 == "SHIELD_BACKEND_TOKEN" {sub(/^[^=]*=/, ""); print; exit}' "$ENV_FILE")"
[[ -n "$token" ]] || { echo "backend-token=missing-in-active-environment"; exit 1; }

response="$(printf 'header = "Authorization: Bearer %s"\nurl = "%s"\n' "$token" "$URL" |
  curl --config - --fail --silent --show-error --max-time 10)"

if command -v jq >/dev/null 2>&1 && jq -e '.ok == true' >/dev/null 2>&1 <<<"$response"; then
  echo "admin_correlation=CONFIRMED_HTTP_200"
else
  echo "admin_correlation=unexpected_response"
  exit 1
fi
