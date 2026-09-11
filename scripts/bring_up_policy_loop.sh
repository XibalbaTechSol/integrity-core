#!/usr/bin/env bash
set -euo pipefail

# Bring up the local CORE -> Shield -> Cortex policy loop. This script performs
# service wiring and health checks only; it never submits blockchain transactions
# and never enables AGENT_DIRECTORY_FINALIZED.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORE_URL="${CORE_URL:-http://127.0.0.1:8080}"
SHIELD_URL="${SHIELD_URL:-http://127.0.0.1:8421}"
CORTEX_URL="${CORTEX_URL:-http://127.0.0.1:8420}"
SHIELD_TENANT_ID="${SHIELD_TENANT_ID:-}"
ROTATE_SHIELD_TOKEN="${ROTATE_SHIELD_TOKEN:-false}"
WAIT_SECONDS="${WAIT_SECONDS:-45}"

die() { echo "ERROR: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"; }
wait_http() {
  local url="$1" label="$2" i
  for ((i=1; i<=WAIT_SECONDS; i++)); do
    if curl --fail --silent --show-error "$url" >/dev/null 2>&1; then
      echo "$label is healthy at $url"
      return 0
    fi
    sleep 1
  done
  die "$label did not become healthy at $url within ${WAIT_SECONDS}s"
}

[[ "$(id -u)" -eq 0 ]] || die "run with sudo from the repository checkout"
[[ -n "$SHIELD_TENANT_ID" ]] || die "set SHIELD_TENANT_ID (normally tenant-a)"
need curl
need docker
need systemctl

cd "$REPO_ROOT"
if [[ "$ROTATE_SHIELD_TOKEN" == "true" ]]; then
  [[ -x /home/xibalba/Projects/xibalba-shield/scripts/rotate_backend_token.sh ]] || \
    die "Shield token rotation script is unavailable"
  echo "Rotating Shield backend token by explicit request"
  bash /home/xibalba/Projects/xibalba-shield/scripts/rotate_backend_token.sh
fi

echo "Starting CORE dependencies and oracle-backend"
docker compose up -d postgres redis oracle-backend
wait_http "$CORE_URL/healthz" "CORE"

unset SHIELD_ADMIN_TOKEN
set +e
SHIELD_TENANT_ID="$SHIELD_TENANT_ID" \
  bash "$REPO_ROOT/scripts/finish_production_setup.sh"
setup_rc=$?
set -e
if (( setup_rc != 0 )); then
  if [[ "${ENABLE_FINALITY:-false}" == "true" ]]; then
    die "finality gate refused setup (CORE snapshot is not finalized); no finality setting was changed"
  fi
  echo "--- Shield service status ---" >&2
  systemctl --no-pager --full status xibalba-shield-backend.service >&2 || true
  echo "--- Shield recent logs ---" >&2
  journalctl -u xibalba-shield-backend.service -n 30 --no-pager >&2 || true
  die "CORE-to-Shield setup failed (exit $setup_rc)"
fi

wait_http "$SHIELD_URL/api/shield/health" "Shield"
wait_http "$CORTEX_URL/healthz" "Cortex"

if ! systemctl is-active --quiet xibalba-core-shield-policy.service; then
  systemctl --no-pager status xibalba-core-shield-policy.service || true
  die "policy publisher service is not active"
fi

echo "Policy loop bring-up verified: CORE, Shield, Cortex, and publisher are healthy."
echo "Finality remains disabled until an independently verified finalized snapshot is supplied."
