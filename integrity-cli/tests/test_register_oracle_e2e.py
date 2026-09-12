"""
Real end-to-end test of `integrity agent register`'s oracle re-verification
step against a REAL, live `integrity-oracle` instance -- the one step
`test_chain.py` cannot cover, since that file exercises `chain.py` directly
and never runs the CLI's own oracle POST.

This closes a real, confirmed gap: `agent register` (without `--skip-oracle`)
used to fail against a live oracle with a 422 ("missing field `did`") because
`main.py` hand-built its own POST body as `{"agent_id": ..., "alias": ...,
"description": ..., "did_document": ..., "primitives": registration.to_dict()}`
while integrity-oracle's `RegisterAgentRequest` (handlers.rs) requires `did`,
plus at least one of `ed25519_pubkey_hex`/`eth_address_hex` (400 if both
absent). This is the exact same schema drift `integrity-sdk/integrity_sdk/
registration.py` had until 2026-07-09 (see docs/wiki/WIKI_LOG.md's
2026-07-09 entries and docs/INTERFACE_CONTRACT.md §6.3), just never fixed
here since this CLI hand-builds its own payload rather than importing
integrity_sdk.registration (per identity.py's "no sibling dependency"
philosophy -- see identity.py's module docstring).

Mirrors integrity-sdk/tests/test_registration_oracle_e2e.py's harness
(same ephemeral-Postgres/Redis-via-Docker + real `cargo run` oracle
pattern) and this package's own tests/test_chain.py's real-anvil fixture
convention (same `deployed_chain` shape: real anvil, real
`Deploy.s.sol`/`DeployMarkets.s.sol`, addresses parsed from forge's own
broadcast log). Opt-in via `ORACLE_E2E=1` -- same gate name
`integrity-oracle/backend/tests/e2e.rs` and the SDK's oracle e2e test use --
since on top of this package's already-required `anvil`/`forge`, this test
also needs Docker and a real `cargo run` build of the oracle binary. A bare
`uv run pytest` without `ORACLE_E2E=1` skips this file's test loudly
(printed, not silent) rather than failing on missing infra.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path

import pytest
import requests
from eth_account import Account
from eth_utils import keccak
from typer.testing import CliRunner
from web3 import Web3

from integrity_cli.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "contracts"
ORACLE_BACKEND_DIR = REPO_ROOT / "integrity-oracle" / "backend"
ANVIL_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
GENERAL_DOMAIN_ID = keccak(text="general.integrity")

pytestmark = pytest.mark.skipif(
    os.environ.get("ORACLE_E2E") != "1",
    reason="set ORACLE_E2E=1 (with Docker + cargo + anvil/forge on PATH) to run the real CLI oracle-register e2e test",
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(host: str, port: int, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError(f"{host}:{port} did not become reachable within {timeout}s")


def _wait_for_http_ok(url: str, timeout: float = 90.0) -> None:
    deadline = time.time() + timeout
    last_exc: Exception | None = None
    while time.time() < deadline:
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                return
        except requests.RequestException as exc:
            last_exc = exc
        time.sleep(0.3)
    raise RuntimeError(f"{url} did not respond 200 within {timeout}s (last error: {last_exc})")


@pytest.fixture(scope="module")
def deployed_chain():
    """Real anvil + real Deploy.s.sol/DeployMarkets.s.sol, same as
    tests/test_chain.py's own fixture (module-scoped there too), plus the
    market-layer script so the deployments.local.json this produces matches
    what a real integrity-oracle instance expects to resolve against."""
    if shutil.which("anvil") is None or shutil.which("forge") is None:
        pytest.skip("anvil/forge (foundry) required")

    port = _free_port()
    rpc_url = f"http://127.0.0.1:{port}"

    # Ensure foundry.toml fs_permissions don't block the genesis script
    deployments_file = REPO_ROOT / "deployments.local.json"
    deployments_file.touch(exist_ok=True)

    proc = subprocess.Popen(
        ["anvil", "--port", str(port), "--silent"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        for _ in range(50):
            try:
                if w3.is_connected():
                    break
            except Exception:
                pass
            time.sleep(0.2)
        else:
            raise RuntimeError("anvil did not become reachable")

        env = {**os.environ, "FUNDER_PRIVATE_KEY": ANVIL_KEY}
        result = subprocess.run(
            ["forge", "script", "script/Deploy.s.sol", "--rpc-url", rpc_url, "--broadcast"],
            cwd=CONTRACTS_DIR, capture_output=True, text=True, env=env,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Deploy.s.sol failed:\n{result.stdout}\n{result.stderr}")

        markets_result = subprocess.run(
            ["forge", "script", "script/DeployMarkets.s.sol", "--rpc-url", rpc_url, "--broadcast"],
            cwd=CONTRACTS_DIR, capture_output=True, text=True, env=env,
        )
        if markets_result.returncode != 0:
            raise RuntimeError(f"DeployMarkets.s.sol failed:\n{markets_result.stdout}\n{markets_result.stderr}")

        deployments_file = REPO_ROOT / "deployments.local.json"
        assert deployments_file.exists(), "Deploy.s.sol should have written deployments.local.json to the repo root"

        broadcast = json.loads((CONTRACTS_DIR / "broadcast/Deploy.s.sol/31337/run-latest.json").read_text())
        addresses = {
            tx["contractName"]: Web3.to_checksum_address(tx["contractAddress"])
            for tx in broadcast["transactions"]
            if tx.get("transactionType") == "CREATE"
        }
        yield {
            "rpc_url": rpc_url,
            "chain_id": w3.eth.chain_id,
            "w3": w3,
            "funder": Account.from_key(ANVIL_KEY),
            "addresses": addresses,
            "deployments_file": str(deployments_file),
        }
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture(scope="module")
def oracle_backend(deployed_chain):
    """Real `cargo run` oracle-backend against deployed_chain, backed by
    ephemeral Postgres + Redis Docker containers -- mirrors
    integrity-sdk/tests/test_registration_oracle_e2e.py's oracle_backend
    fixture byte-for-byte in structure (never the shared dev-time
    docker-compose services)."""
    if shutil.which("docker") is None or shutil.which("cargo") is None:
        pytest.skip("docker/cargo required")

    pg_port = _free_port()
    redis_port = _free_port()
    pg_container = f"cli-oracle-e2e-pg-{pg_port}"
    redis_container = f"cli-oracle-e2e-redis-{redis_port}"

    subprocess.run(["docker", "rm", "-f", pg_container, redis_container], capture_output=True)
    subprocess.run(
        [
            "docker", "run", "-d", "--name", pg_container,
            "-e", "POSTGRES_DB=integrity",
            "-e", "POSTGRES_USER=integrity",
            "-e", "POSTGRES_PASSWORD=integrity_dev_only",
            "-p", f"{pg_port}:5432",
            "postgres:16-alpine",
        ],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["docker", "run", "-d", "--name", redis_container, "-p", f"{redis_port}:6379", "redis:7-alpine"],
        check=True, capture_output=True,
    )
    proc: subprocess.Popen | None = None

    def _kill_tree() -> None:
        if proc is None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=10)
        except Exception:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                pass

    try:
        _wait_for_port("127.0.0.1", pg_port)
        _wait_for_port("127.0.0.1", redis_port)
        time.sleep(2)  # Postgres accepts TCP slightly before it can serve migrations.

        oracle_port = _free_port()
        env = {
            **os.environ,
            "DATABASE_URL": f"postgres://integrity:integrity_dev_only@127.0.0.1:{pg_port}/integrity",
            "REDIS_URL": f"redis://127.0.0.1:{redis_port}",
            "RPC_URL": deployed_chain["rpc_url"],
            "CHAIN_ID": str(deployed_chain["chain_id"]),
            "DEPLOYMENTS_FILE": deployed_chain["deployments_file"],
            "BIND_ADDR": f"0.0.0.0:{oracle_port}",
        }
        proc = subprocess.Popen(
            ["cargo", "run", "--quiet"],
            cwd=ORACLE_BACKEND_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )

        base_url = f"http://127.0.0.1:{oracle_port}"
        try:
            _wait_for_http_ok(f"{base_url}/healthz")
        except Exception:
            out = proc.stdout.read() if proc.stdout else ""
            _kill_tree()
            raise RuntimeError(f"oracle-backend never became healthy. Output:\n{out}")

        yield base_url
    finally:
        _kill_tree()
        subprocess.run(["docker", "rm", "-f", pg_container, redis_container], capture_output=True)


def test_agent_register_succeeds_against_real_oracle(oracle_backend, deployed_chain, tmp_path, monkeypatch):
    """
    The actual regression test: `integrity agent register` (without
    `--skip-oracle`) must succeed end-to-end against a real, running oracle
    -- and the agent must then be independently visible via a real
    `GET /v1/agents` call. Before the fix, this failed with an ApiError
    wrapping "422 ... missing field `did`".
    """
    monkeypatch.setenv("INTEGRITY_WALLET_HOME", str(tmp_path / "wallets"))
    monkeypatch.setenv("INTEGRITY_WALLET_PASSWORD", "cli-oracle-e2e-pw")
    monkeypatch.setenv("FUNDER_PRIVATE_KEY", deployed_chain["funder"].key.hex())

    runner = CliRunner()
    keygen_result = runner.invoke(app, ["identity", "keygen"])
    assert keygen_result.exit_code == 0, keygen_result.stdout

    register_result = runner.invoke(
        app,
        [
            "agent", "register",
            "--alias", "cli-oracle-e2e-agent",
            "--rpc-url", deployed_chain["rpc_url"],
            "--deployments-file", deployed_chain["deployments_file"],
            "--oracle-url", oracle_backend,
        ],
    )
    assert register_result.exit_code == 0, register_result.stdout
    assert "Oracle accepted the registration" in register_result.stdout

    # Read the real persisted registration record from disk (identity.py's
    # <name>.primitives.json, written by main.py's agent_register right after
    # the on-chain sequence, BEFORE the oracle POST -- so its own
    # `oracle_registered` field is always stale/False on disk; the DID and
    # primitive addresses it carries are what matter here) rather than
    # fragile-parsing rich's colored/pretty-printed stdout.
    primitives_path = tmp_path / ".integrity-cli" / "identity" / "default" / "primitives.json"
    assert primitives_path.exists(), f"expected {primitives_path} to exist after a successful register"
    body = json.loads(primitives_path.read_text())

    did = body.get("did")
    assert did, f"no 'did' in persisted primitives record: {body}"

    # The real proof the oracle POST succeeded: a live GET against the oracle
    # itself, not a locally-cached field. Before the fix, the CLI's POST body
    # used `agent_id` instead of `did`, so this DID would never resolve here.
    resp = requests.get(f"{oracle_backend}/v1/agent/{did}", timeout=10)
    assert resp.status_code == 200, resp.text
    agent_body = resp.json()
    assert agent_body["has_ed25519_key"] is True
    assert agent_body["has_eth_address"] is True
    assert agent_body["primitives"]["sovereign_agent"].lower() == body["sovereign_agent"].lower()

    resp = requests.get(f"{oracle_backend}/v1/agents", timeout=10)
    assert resp.status_code == 200, resp.text
    ids = [row["id"] for row in resp.json()]
    assert did in ids, f"registered agent {did} did not appear in GET /v1/agents: {ids}"
