#!/usr/bin/env python3
"""Migrate xibalba's Base Sepolia verifier registry to verifier version 2.

The controller key is read from the encrypted local keystore and is never printed.
Set BASE_SEPOLIA_RPC_URL and INTEGRITY_WALLET_PASSWORD in the environment (or in
contracts/.env) before running this script.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

try:
    from eth_abi import encode
    from eth_account import Account
    from web3 import Web3
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    raise SystemExit(
        "Missing Python dependency. Run with the SDK environment:\n"
        "  uv run --project integrity-sdk python contracts/script/migrate_xibalba_verifier.py"
    ) from exc

AGENT = Web3.to_checksum_address("0x360e2a56eb23e383b81e5bb42ee5c3966688558a")
CONTROLLER = Web3.to_checksum_address("0x14bB099e3add7341a987a3fb435f051908f46ee2")
VERIFIER_REGISTRY = Web3.to_checksum_address("0x9baf461553e59904fb4e41973d995aa856cad0e7")
NEW_VERIFIER = Web3.to_checksum_address("0x565184C507CD2c22a0c95f914c9034C8F289818A")
CHAIN_ID = 84532

EXECUTE_SELECTOR = Web3.keccak(text="execute(address,uint256,bytes)")[:4]
PIN_SELECTOR = Web3.keccak(text="pinVersion(uint256,address)")[:4]
SET_SELECTOR = Web3.keccak(text="setCurrentVersion(uint256)")[:4]


def calldata(selector: bytes, types: list[str], values: list[object]) -> bytes:
    return selector + encode(types, values)


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE entries without overriding the process environment."""
    if not path.is_file():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def execute_data(inner: bytes) -> bytes:
    return EXECUTE_SELECTOR + encode(["address", "uint256", "bytes"], [VERIFIER_REGISTRY, 0, inner])


def submit(w3: Web3, account, nonce: int, data: bytes, label: str, dry_run: bool) -> int:
    tx = {
        "from": account.address,
        "to": AGENT,
        "value": 0,
        "data": data,
        "nonce": nonce,
        "chainId": CHAIN_ID,
    }
    tx["gas"] = w3.eth.estimate_gas(tx)
    latest = w3.eth.get_block("latest")
    base_fee = latest.get("baseFeePerGas", w3.to_wei(0.01, "gwei"))
    priority = w3.to_wei(0.001, "gwei")
    tx["maxPriorityFeePerGas"] = priority
    tx["maxFeePerGas"] = base_fee * 2 + priority
    print(f"{label}: estimated gas {tx['gas']}")
    if dry_run:
        return nonce + 1
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status != 1:
        raise RuntimeError(f"{label} reverted: {tx_hash.hex()}")
    print(f"{label}: https://sepolia.basescan.org/tx/{tx_hash.hex()}")
    return nonce + 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keystore", default=str(Path.home() / ".integrity/wallet/xibalba/keystore.json"))
    parser.add_argument("--dry-run", action="store_true", help="estimate only; do not sign or broadcast")
    parser.add_argument("--yes", action="store_true", help="skip the final broadcast confirmation")
    args = parser.parse_args()

    load_env_file(Path(__file__).resolve().parents[1] / ".env")
    rpc = os.environ.get("BASE_SEPOLIA_RPC_URL", "https://sepolia.base.org")
    password = os.environ.get("INTEGRITY_WALLET_PASSWORD")
    if not password:
        raise SystemExit("INTEGRITY_WALLET_PASSWORD is not set")
    if not Path(args.keystore).is_file():
        raise SystemExit(f"keystore not found: {args.keystore}")

    keystore = json.loads(Path(args.keystore).read_text())
    private_key = Account.decrypt(keystore, password)
    account = Account.from_key(private_key)
    if Web3.to_checksum_address(account.address) != CONTROLLER:
        raise SystemExit(f"keystore address does not match expected controller {CONTROLLER}")

    w3 = Web3(Web3.HTTPProvider(rpc))
    if not w3.is_connected():
        raise SystemExit("could not connect to Base Sepolia RPC")
    if w3.eth.chain_id != CHAIN_ID:
        raise SystemExit(f"wrong chain: expected {CHAIN_ID}, got {w3.eth.chain_id}")

    registry = w3.eth.contract(
        address=VERIFIER_REGISTRY,
        abi=[
            {"name": "currentVersion", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
            {"name": "verifierImpl", "type": "function", "stateMutability": "view", "inputs": [{"type": "uint256"}], "outputs": [{"type": "address"}]},
        ],
    )
    print(f"controller: {account.address}")
    current_version = registry.functions.currentVersion().call()
    pinned_verifier = Web3.to_checksum_address(registry.functions.verifierImpl(2).call())
    print(f"current version: {current_version}")
    if not args.dry_run and not args.yes:
        answer = input("Broadcast pinVersion(2) and setCurrentVersion(2)? [y/N] ").strip().lower()
        if answer != "y":
            raise SystemExit("cancelled")

    nonce = w3.eth.get_transaction_count(account.address, "pending")
    if pinned_verifier != NEW_VERIFIER:
        nonce = submit(w3, account, nonce, execute_data(calldata(PIN_SELECTOR, ["uint256", "address"], [2, NEW_VERIFIER])), "pinVersion", args.dry_run)
    else:
        print("pinVersion: already pinned")
    if current_version != 2:
        if args.dry_run:
            print("setCurrentVersion: deferred until pinVersion is mined")
        else:
            submit(w3, account, nonce, execute_data(calldata(SET_SELECTOR, ["uint256"], [2])), "setCurrentVersion", False)
    else:
        print("setCurrentVersion: already active")

    if not args.dry_run:
        for _ in range(10):
            if registry.functions.currentVersion().call() == 2 and Web3.to_checksum_address(registry.functions.verifierImpl(2).call()) == NEW_VERIFIER:
                break
            time.sleep(1)
        else:
            raise RuntimeError("transactions succeeded but RPC readback did not converge")
        print("verified: currentVersion=2 and verifierImpl(2)=new verifier")


if __name__ == "__main__":
    main()
