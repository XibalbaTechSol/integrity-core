#!/usr/bin/env bash
set -euo pipefail

# One-paste Alchemy setup. The key is read without echo, used in memory, and
# removed from the shell on exit. The underlying configurator writes the URL to
# the local .env because CORE needs it at runtime; keep that file mode 0600.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
trap 'unset ALCHEMY_KEY BASE_SEPOLIA_RPC_URL' EXIT

[[ -t 0 ]] || { echo "ERROR: run this from an interactive terminal" >&2; exit 1; }
printf 'Paste the replacement Alchemy API key (input hidden): '
read -r -s ALCHEMY_KEY
printf '\n'
[[ -n "$ALCHEMY_KEY" ]] || { echo "ERROR: no API key supplied" >&2; exit 1; }

export BASE_SEPOLIA_RPC_URL="https://base-sepolia.g.alchemy.com/v2/${ALCHEMY_KEY}"
chmod 600 "$REPO_ROOT/.env" 2>/dev/null || true
cd "$REPO_ROOT"
bash scripts/configure_base_sepolia_rpc.sh
chmod 600 "$REPO_ROOT/.env" 2>/dev/null || true
echo "Alchemy Base Sepolia configuration completed; API key was not printed."
