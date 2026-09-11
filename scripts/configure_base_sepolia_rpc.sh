#!/usr/bin/env bash
set -euo pipefail

# Point the local CORE compose deployment at Base Sepolia and run a read-only
# finality audit. No private keys are read or changed, and finality approval is
# never enabled by this script.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/.env}"
RPC_URL="${BASE_SEPOLIA_RPC_URL:-https://sepolia.base.org}"

die() { echo "ERROR: $*" >&2; exit 1; }
[[ -f "$ENV_FILE" ]] || die "missing $ENV_FILE"
command -v python3 >/dev/null 2>&1 || die "python3 is required"
command -v cast >/dev/null 2>&1 || die "cast is required"

write_env() {
python3 - "$ENV_FILE" "$1" <<'PY'
from pathlib import Path
import sys

path, rpc = Path(sys.argv[1]), sys.argv[2]
keys = {
    "RPC_URL": rpc,
    "DOCKER_RPC_URL": rpc,
    "CHAIN_ID": "84532",
    "AGENT_DIRECTORY_FINALIZED": "false",
}
lines = path.read_text(encoding="utf-8").splitlines()
out, seen = [], set()
for line in lines:
    name = line.split("=", 1)[0] if "=" in line else ""
    if name in keys:
        if name not in seen:
            out.append(f"{name}={keys[name]}")
            seen.add(name)
    else:
        out.append(line)
for name, value in keys.items():
    if name not in seen:
        out.append(f"{name}={value}")
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
}

write_env "$RPC_URL"

chain_id="$(cast chain-id --rpc-url "$RPC_URL")" || die "could not reach Base Sepolia RPC"
[[ "$chain_id" == "84532" ]] || die "RPC returned chain ID $chain_id, expected 84532"
echo "Configured Base Sepolia RPC; chain ID verified as 84532"

if ! cast block finalized --rpc-url "$RPC_URL" >/dev/null 2>&1; then
  [[ -t 0 ]] || die "RPC does not expose finalized blocks; set BASE_SEPOLIA_RPC_URL to an authenticated provider URL"
  printf 'The RPC accepts Base Sepolia but does not provide finalized blocks.\n'
  printf 'Enter an authenticated Base Sepolia RPC URL (input hidden): '
  read -r -s RPC_URL
  printf '\n'
  [[ -n "$RPC_URL" ]] || die "no RPC URL supplied"
  chain_id="$(cast chain-id --rpc-url "$RPC_URL")" || die "could not reach supplied RPC"
  [[ "$chain_id" == "84532" ]] || die "supplied RPC returned chain ID $chain_id, expected 84532"
  cast block finalized --rpc-url "$RPC_URL" >/dev/null 2>&1 || die "supplied RPC still does not expose finalized blocks"
  write_env "$RPC_URL"
  echo "Authenticated Base Sepolia RPC validated and saved"
fi

cd "$REPO_ROOT"
if [[ "$(id -u)" -eq 0 ]]; then
  bash scripts/enable_finality_after_evidence.sh
else
  sudo -E bash scripts/enable_finality_after_evidence.sh
fi
