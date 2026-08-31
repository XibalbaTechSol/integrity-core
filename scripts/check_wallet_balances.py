#!/usr/bin/env python3
"""Check configured Integrity operator wallets have enough native gas.

This guard exists because a low funder balance recently made agent registration
fail only when the first real transaction was attempted. It reads the configured
private keys, derives their addresses, and queries the configured RPC; it never
signs or submits a transaction.

Exit codes: 0 = all wallets funded, 1 = wallet below threshold, 2 = unable to
determine status. ``--warn-only`` reports findings but always exits 0.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

KEY_NAMES = (
    "FUNDER_PRIVATE_KEY",
    "ORACLE_SIGNER_PRIVATE_KEY",
    "DEPLOYER_PRIVATE_KEY",
    "ARBITRATOR_PRIVATE_KEY",
    "DISPUTER_PRIVATE_KEY",
    "GOVERNANCE_PRIVATE_KEY",
    "RESOLVER_PRIVATE_KEY",
)


def _load_dotenv() -> None:
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"\''))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-balance-eth", default="0.01", help="minimum required balance in ETH")
    parser.add_argument("--warn-only", action="store_true", help="report findings but exit successfully")
    args = parser.parse_args()
    _load_dotenv()

    try:
        threshold = Decimal(str(args.min_balance_eth))
        if threshold < 0:
            raise InvalidOperation
    except InvalidOperation:
        print("error: --min-balance-eth must be a non-negative decimal", file=sys.stderr)
        return 2

    rpc_url = os.getenv("RPC_URL")
    if not rpc_url:
        print("error: RPC_URL is not configured", file=sys.stderr)
        return 2

    keys = {value for name in KEY_NAMES if (value := os.getenv(name))}
    if not keys:
        print("error: no operator private-key variables are configured", file=sys.stderr)
        return 2

    try:
        wallets = set()
        invalid = []
        for key in keys:
            result = subprocess.run(["cast", "wallet", "address", "--private-key", key], capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                invalid.append(result.stderr.strip() or "invalid private key")
                continue
            wallets.add(result.stdout.strip())
        if invalid and not wallets:
            raise RuntimeError(f"could not derive operator address: {invalid[0]}")
        for error in invalid:
            print(f"error: ignoring malformed configured key: {error}", file=sys.stderr)
        chain = subprocess.run(["cast", "chain-id", "--rpc-url", rpc_url], capture_output=True, text=True, timeout=15)
        if chain.returncode != 0:
            raise RuntimeError(chain.stderr.strip() or "RPC is unreachable")
        chain_id = chain.stdout.strip()
        low = False
        for address in sorted(wallets):
            balance_result = subprocess.run(["cast", "balance", "--ether", address, "--rpc-url", rpc_url], capture_output=True, text=True, timeout=15)
            if balance_result.returncode != 0:
                raise RuntimeError(balance_result.stderr.strip() or f"could not read balance for {address}")
            balance = Decimal(balance_result.stdout.strip().split()[0])
            state = "LOW" if balance < threshold else "ok"
            print(f"chain={chain_id} address={address} balance={balance} ETH minimum={threshold} ETH status={state}")
            low |= balance < threshold
    except Exception as exc:  # noqa: BLE001 - operational probe must classify failures
        print(f"error: could not determine wallet balances: {exc}", file=sys.stderr)
        return 0 if args.warn_only else 2

    if args.warn_only:
        return 0
    if invalid:
        return 2
    return 1 if low else 0


if __name__ == "__main__":
    raise SystemExit(main())
