#!/usr/bin/env bash
set -euo pipefail

# Audit chain finality and optionally enable the CORE finality approval bit.
# Read-only by default. Never submits transactions or prints RPC credentials.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/.env}"
CORE_URL="${CORE_URL:-http://127.0.0.1:8080}"
APPLY_FINALITY="${APPLY_FINALITY:-false}"

die() { echo "ERROR: $*" >&2; exit 1; }
[[ -f "$ENV_FILE" ]] || die "missing $ENV_FILE"
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
RPC_URL="${DOCKER_RPC_URL:-${RPC_URL:-}}"
[[ -n "$RPC_URL" ]] || die "DOCKER_RPC_URL or RPC_URL is not configured"
command -v python3 >/dev/null 2>&1 || die "python3 is required"

rpc_json() {
  local method="$1" params="$2"
  RPC_URL="$RPC_URL" RPC_METHOD="$method" RPC_PARAMS="$params" python3 - <<'PY'
import json, os, urllib.error, urllib.request
request = urllib.request.Request(
    os.environ["RPC_URL"],
    data=json.dumps({"jsonrpc":"2.0", "id":1, "method":os.environ["RPC_METHOD"], "params":json.loads(os.environ["RPC_PARAMS"])}).encode(),
    headers={"Content-Type":"application/json"},
)
try:
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.load(response)
except urllib.error.HTTPError as exc:
    raise SystemExit(f"RPC request rejected with HTTP {exc.code}")
except urllib.error.URLError:
    raise SystemExit("RPC endpoint is unreachable")
if payload.get("error"):
    raise SystemExit(1)
print(json.dumps(payload.get("result")))
PY
}

finalized="$(rpc_json eth_getBlockByNumber '["finalized",false]')" || die "RPC does not expose a finalized block"
latest="$(rpc_json eth_getBlockByNumber '["latest",false]')" || die "RPC latest-block query failed"
python3 - "$finalized" "$latest" "$APPLY_FINALITY" "$ENV_FILE" <<'PY'
import json, sys

finalized, latest, apply, env_file = sys.argv[1:]
finalized = json.loads(finalized)
latest = json.loads(latest)
if not isinstance(finalized, dict) or not finalized.get("number") or not finalized.get("hash"):
    raise SystemExit("RPC returned no usable finalized block; finality remains disabled")
fnum = int(finalized["number"], 16)
lnum = int(latest["number"], 16) if isinstance(latest, dict) and latest.get("number") else None
print(f"RPC finalized block: {fnum}")
if lnum is not None:
    print(f"RPC latest block: {lnum}")
if apply != "true":
    print("Dry run only. Re-run with APPLY_FINALITY=true to apply the approval bit.")
    raise SystemExit(0)
lines = open(env_file, encoding="utf-8").read().splitlines()
out, seen = [], False
for line in lines:
    if line.startswith("AGENT_DIRECTORY_FINALIZED="):
        if not seen:
            out.append("AGENT_DIRECTORY_FINALIZED=true")
            seen = True
    else:
        out.append(line)
if not seen:
    out.append("AGENT_DIRECTORY_FINALIZED=true")
open(env_file, "w", encoding="utf-8").write("\n".join(out) + "\n")
print(f"Set AGENT_DIRECTORY_FINALIZED=true in {env_file}")
PY

if [[ "$APPLY_FINALITY" == "true" ]]; then
  command -v docker >/dev/null 2>&1 || die "docker is required to apply finality"
  cd "$REPO_ROOT"
  AGENT_DIRECTORY_FINALIZED=true docker compose up -d --build --force-recreate oracle-backend
  core_ready=false
  for _ in $(seq 1 45); do
    if curl --fail --silent --show-error "$CORE_URL/healthz" >/dev/null 2>&1; then
      core_ready=true
      break
    fi
    sleep 1
  done
  [[ "$core_ready" == true ]] || die "CORE did not become healthy after enabling finality"
  snapshot=""
  for _ in $(seq 1 15); do
    snapshot="$(curl --fail --silent --show-error "$CORE_URL/v1/agents/snapshot" 2>/dev/null || true)"
    [[ -n "$snapshot" ]] && break
    sleep 1
  done
  [[ -n "$snapshot" ]] || die "CORE snapshot unavailable after enabling finality"
  SNAPSHOT="$snapshot" python3 - <<'PY'
import json, os
p = json.loads(os.environ["SNAPSHOT"])
if p.get("finalized") is not True:
    raise SystemExit(
        "CORE did not advertise a finalized snapshot after applying the approval bit "
        f"(block={p.get('block_number')}, finalized_block={p.get('finalized_block_number')})"
    )
print("CORE finalized snapshot verified")
PY
  echo "Oracle recreated with finality approval. Restart Cortex sync and verify its finalized snapshot consumption."
fi
