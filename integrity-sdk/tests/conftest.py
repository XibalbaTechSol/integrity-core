"""
Shared pytest fixtures.

`deployed_chain` spins up a REAL local anvil instance and runs the REAL
`contracts/script/Deploy.s.sol` genesis deploy against it (the same script
used for the real Base Sepolia deploy — see docs/INTERFACE_CONTRACT.md §6),
so chain.py's deploy/registration code paths get exercised against real,
freshly-deployed contracts on every test run, not a mock or a stale shared
deployments.local.json. Mirrors bcc_middleware/tests/conftest.py's
`anvil_chain` fixture pattern (real anvil subprocess, real forge toolchain).
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from pathlib import Path

import pytest
from eth_account import Account
from web3 import Web3

CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "contracts"
ANVIL_DEV_PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_rpc(url: str, timeout: float = 15.0) -> None:
    w3 = Web3(Web3.HTTPProvider(url))
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if w3.is_connected():
                return
        except Exception:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"anvil at {url} did not become reachable in {timeout}s")


@pytest.fixture(scope="session")
def deployed_chain():
    """
    Starts a real `anvil` subprocess, runs the real Deploy.s.sol genesis
    script against it (funder = anvil's well-known dev account #0, which
    anvil always pre-funds), and yields connection info + every deployed
    address parsed straight from forge's own broadcast log — not a
    hand-maintained address table that could drift from what the script
    actually deploys.
    """
    port = _free_port()
    rpc_url = f"http://127.0.0.1:{port}"

    # Ensure foundry.toml fs_permissions don't block the genesis script
    deployments_file = CONTRACTS_DIR.parent / "deployments.local.json"
    deployments_file.touch(exist_ok=True)

    proc = subprocess.Popen(
        ["anvil", "--port", str(port), "--silent"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_rpc(rpc_url)

        (CONTRACTS_DIR.parent / "deployments.local.json").touch(exist_ok=True)

        result = subprocess.run(
            ["forge", "script", "script/Deploy.s.sol", "--rpc-url", rpc_url, "--broadcast"],
            cwd=CONTRACTS_DIR,
            capture_output=True,
            text=True,
            env=dict(os.environ, FUNDER_PRIVATE_KEY=ANVIL_DEV_PRIVATE_KEY),
        )
        if result.returncode != 0:
            raise RuntimeError(f"Deploy.s.sol failed:\n{result.stdout}\n{result.stderr}")

        broadcast_path = CONTRACTS_DIR / "broadcast" / "Deploy.s.sol" / "31337" / "run-latest.json"
        broadcast = json.loads(broadcast_path.read_text())
        addresses = {
            tx["contractName"]: Web3.to_checksum_address(tx["contractAddress"])
            for tx in broadcast["transactions"]
            if tx.get("transactionType") == "CREATE"
        }

        # Market/application layer is a separate INCREMENTAL script (see
        # contracts/script/DeployMarkets.s.sol's own NatSpec on why it's not
        # folded into genesis Deploy.s.sol) -- run it here too, against the
        # same fresh anvil + the deployments.local.json Deploy.s.sol just
        # wrote, so tests exercising markets.py get real deployed addresses.
        markets_result = subprocess.run(
            ["forge", "script", "script/DeployMarkets.s.sol", "--rpc-url", rpc_url, "--broadcast"],
            cwd=CONTRACTS_DIR,
            capture_output=True,
            text=True,
            env=dict(os.environ, FUNDER_PRIVATE_KEY=ANVIL_DEV_PRIVATE_KEY),
        )
        if markets_result.returncode != 0:
            raise RuntimeError(f"DeployMarkets.s.sol failed:\n{markets_result.stdout}\n{markets_result.stderr}")

        markets_broadcast_path = CONTRACTS_DIR / "broadcast" / "DeployMarkets.s.sol" / "31337" / "run-latest.json"
        markets_broadcast = json.loads(markets_broadcast_path.read_text())
        for tx in markets_broadcast["transactions"]:
            if tx.get("transactionType") == "CREATE":
                addresses[tx["contractName"]] = Web3.to_checksum_address(tx["contractAddress"])

        w3 = Web3(Web3.HTTPProvider(rpc_url))
        funder = Account.from_key(ANVIL_DEV_PRIVATE_KEY)

        yield {
            "rpc_url": rpc_url,
            "chain_id": w3.eth.chain_id,
            "w3": w3,
            "funder": funder,
            "addresses": addresses,
        }
    finally:
        proc.terminate()
        proc.wait(timeout=10)
