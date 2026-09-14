#!/usr/bin/env bash
# Register the prepared Shield replacement identity using the protocol funder.
#
# The funder pays the agent-wallet funding and ITK mint transactions. The CLI
# then signs the self-sovereign deployment/registration transactions with the
# new agent wallet; the funder is not made the agent controller.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLI_ROOT="$REPO_ROOT/integrity-cli"
IDENTITY_NAME="${INTEGRITY_SHIELD_IDENTITY:-shield-replacement}"
if [[ -n "${DEPLOYMENTS_FILE:-}" ]]; then
  DEPLOYMENTS_FILE="$DEPLOYMENTS_FILE"
else
  # The replacement registration targets Base Sepolia, not the local Anvil
  # deployment used by the development stack.
  DEPLOYMENTS_FILE="$REPO_ROOT/deployments.baseSepolia.json"
fi
ORACLE_URL="${ORACLE_URL:-http://127.0.0.1:8080}"

if [[ ! -d "$CLI_ROOT" ]]; then
  echo "ERROR: Integrity CLI checkout not found at $CLI_ROOT" >&2
  exit 1
fi
if [[ ! -f "$DEPLOYMENTS_FILE" ]]; then
  echo "ERROR: deployments file not found: $DEPLOYMENTS_FILE" >&2
  exit 1
fi
if [[ ! -f "$HOME/.integrity-cli/identity/$IDENTITY_NAME.pem" ]]; then
  echo "ERROR: identity '$IDENTITY_NAME' is missing." >&2
  echo "Create it with: uv run --project '$CLI_ROOT' integrity identity keygen --name '$IDENTITY_NAME'" >&2
  exit 1
fi

cleanup() {
  unset FUNDER_PRIVATE_KEY INTEGRITY_WALLET_PASSWORD RPC_URL
}
trap cleanup EXIT

read -r -s -p "Funder private key (input hidden): " FUNDER_PRIVATE_KEY
echo
read -r -s -p "Agent wallet password (input hidden): " INTEGRITY_WALLET_PASSWORD
echo
read -r -s -p "Alchemy API key (input hidden): " ALCHEMY_KEY
echo

if [[ -z "$FUNDER_PRIVATE_KEY" || -z "$INTEGRITY_WALLET_PASSWORD" || -z "$ALCHEMY_KEY" ]]; then
  echo "ERROR: all three hidden values are required" >&2
  exit 1
fi

RPC_URL="https://base-sepolia.g.alchemy.com/v2/$ALCHEMY_KEY"

# Resolve and display only the public funder address and its Base Sepolia
# balance. The private key remains in the child process environment and is
# never printed or passed on a command line.
export FUNDER_PRIVATE_KEY RPC_URL
FUNDER_INFO="$(uv run --project "$CLI_ROOT" python - <<'PY'
import os
from eth_account import Account
from web3 import Web3

account = Account.from_key(os.environ["FUNDER_PRIVATE_KEY"])
w3 = Web3(Web3.HTTPProvider(os.environ["RPC_URL"]))
print(account.address)
print(Web3.from_wei(w3.eth.get_balance(account.address), "ether"))
PY
)"
FUNDER_ADDRESS="$(printf '%s\n' "$FUNDER_INFO" | sed -n '1p')"
FUNDER_BALANCE="$(printf '%s\n' "$FUNDER_INFO" | sed -n '2p')"
echo
echo "This will broadcast the multi-transaction Shield registration on Base Sepolia."
echo "Identity: $IDENTITY_NAME"
echo "Oracle:   $ORACLE_URL"
echo "Funder:   $FUNDER_ADDRESS (balance: $FUNDER_BALANCE ETH)"
if [[ "$FUNDER_BALANCE" == "0" || "$FUNDER_BALANCE" == 0.* ]]; then
  echo "ERROR: this funder has insufficient Base Sepolia ETH. Fund this address or enter a different key." >&2
  exit 1
fi
read -r -p "Type REGISTER to continue: " confirmation
if [[ "$confirmation" != "REGISTER" ]]; then
  echo "Cancelled; no transaction was sent."
  exit 0
fi

export FUNDER_PRIVATE_KEY INTEGRITY_WALLET_PASSWORD RPC_URL ORACLE_URL DEPLOYMENTS_FILE
cd "$CLI_ROOT"
uv run integrity agent register \
  --identity "$IDENTITY_NAME" \
  --alias shield-replacement \
  --domain general.integrity \
  --rpc-url "$RPC_URL" \
  --oracle-url "$ORACLE_URL" \
  --deployments-file "$DEPLOYMENTS_FILE"

echo "Registration completed. Save the transaction hash above, then configure Cortex with it."
