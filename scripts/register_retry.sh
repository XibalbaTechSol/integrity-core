#!/usr/bin/env bash
# Retries scripts/register_with_oracle.py (in xibalba-shield) against the running docker-compose
# stack, up to MAX_ATTEMPTS times, with a short pause between attempts to let RPC state settle
# (the "insufficient funds" failure this was written for turned out to be a read-after-write lag
# right after fund_agent_wallet's tx confirmed, not a real funding shortfall -- see
# PRODUCTION_GAPS.md's 2026-08-14 registration entries for the full history of what's already
# been ruled out: nonce races, a broken REGISTRAR_ROLE grant, RPC provider inconsistency).
#
# Bounded on purpose, not a while-true loop: every failed attempt (even a transient one) spends
# real testnet gas and orphans a fresh SovereignAgent/StateAnchor pair, since registration is
# only idempotent AFTER it fully completes (see register_with_oracle.py's own docstring). Run
# from the integrity-core repo root: ./scripts/register_retry.sh
set -uo pipefail

MAX_ATTEMPTS=5
SLEEP_SECONDS=8

cd "$(dirname "$0")/.."
source .env

for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
    echo "=== registration attempt $attempt/$MAX_ATTEMPTS ==="
    output=$(docker compose exec \
        -e FUNDER_PRIVATE_KEY="$ORACLE_SIGNER_PRIVATE_KEY" \
        -e INTEGRITY_WALLET_PASSWORD \
        shield python scripts/register_with_oracle.py 2>&1)
    status=$?
    echo "$output"

    if [ "$status" -eq 0 ]; then
        echo "=== SUCCESS on attempt $attempt ==="
        exit 0
    fi

    echo "=== attempt $attempt failed (exit $status) ==="
    if [ "$attempt" -lt "$MAX_ATTEMPTS" ]; then
        echo "waiting ${SLEEP_SECONDS}s before retry..."
        sleep "$SLEEP_SECONDS"
    fi
done

echo "=== all $MAX_ATTEMPTS attempts failed -- stopping rather than keep spending gas ==="
echo "Current funder balance:"
cast balance 0x7530bd7Cb142C50d5cC742EdF02263f368e89E2f --rpc-url https://sepolia.base.org --ether 2>/dev/null || true
exit 1
