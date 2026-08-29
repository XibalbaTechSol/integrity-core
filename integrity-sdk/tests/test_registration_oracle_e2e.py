"""
Real end-to-end test of registration.register_agent's oracle re-verification
step (step 11: `POST {oracle_url}/v1/agent/register`) against a REAL, live
`integrity-oracle` instance — the one on-chain-only step
`test_registration.py` cannot cover, since that file always passes
`skip_oracle_registration=True` (integrity-oracle's HTTP layer didn't exist
yet when it was written).

This closes a real, confirmed gap: `register_agent()` without
`skip_oracle_registration` used to fail against a live oracle with a 422
("missing field `did`") because the SDK sent `{"agent_id": ..., ...}` while
integrity-oracle's `RegisterAgentRequest` (handlers.rs) requires `did`, plus
at least one of `ed25519_pubkey_hex`/`eth_address_hex` (400 if both absent).
See docs/wiki/WIKI_LOG.md's 2026-07-09 entry and
docs/INTERFACE_CONTRACT.md §6.3 for the full story and the now-documented
schema.

Opt-in via `ORACLE_E2E=1` — same gate `integrity-oracle/backend/tests/e2e.rs`
uses — because on top of this package's already-required `anvil`/`forge`,
this test also needs Docker (ephemeral Postgres + Redis, distinct from any
dev-time `docker-compose` services) and a real `cargo run` build of the
oracle binary. A bare `uv run pytest` without `ORACLE_E2E=1` skips this
file's test loudly (printed, not silent) rather than failing on missing
infra.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from pathlib import Path

import pytest
import requests

from integrity_sdk import registration

REPO_ROOT = Path(__file__).resolve().parents[2]
ORACLE_BACKEND_DIR = REPO_ROOT / "integrity-oracle" / "backend"
ANVIL_DEV_PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"

pytestmark = pytest.mark.skipif(
    os.environ.get("ORACLE_E2E") != "1",
    reason="set ORACLE_E2E=1 (with Docker + cargo on PATH) to run the real oracle registration e2e test",
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


def _wait_for_http_ok(url: str, timeout: float = 60.0) -> None:
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
def oracle_backend(deployed_chain):
    """
    Starts a REAL `integrity-oracle` backend (`cargo run`) pointed at the
    session's real anvil chain (`deployed_chain` from conftest.py, which
    already ran the real `Deploy.s.sol` + `DeployMarkets.s.sol` genesis and,
    as a real side effect of those forge scripts, wrote a full
    `deployments.local.json` to the repo root — reused here as-is rather than
    hand-built, so the oracle resolves the exact same on-chain state the SDK
    registered against), backed by ephemeral, dedicated Postgres + Redis
    Docker containers (never the shared dev-time `docker-compose` services,
    same reasoning as `integrity-dashboard/e2e/global-setup.ts`'s ephemeral
    containers). Yields the oracle's base URL; tears everything down after.
    """
    pg_port = _free_port()
    redis_port = _free_port()
    pg_container = f"sdk-oracle-e2e-pg-{pg_port}"
    redis_container = f"sdk-oracle-e2e-redis-{redis_port}"

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
        # `cargo run` spawns the actual `oracle-backend` binary as a CHILD
        # process -- a plain proc.terminate() would only signal `cargo`
        # itself and can leak an orphaned `oracle-backend` still bound to
        # oracle_port. `start_new_session=True` at Popen time put the whole
        # tree in its own process group so os.killpg can take it down
        # together. Guarded for the case `proc` was never created (a docker
        # setup failure above the Popen call).
        import signal

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
        deployments_file = REPO_ROOT / "deployments.local.json"
        assert deployments_file.exists(), (
            "deployed_chain's forge scripts should have written a real deployments.local.json "
            "to the repo root as a side effect"
        )

        env = {
            **os.environ,
            "DATABASE_URL": f"postgres://integrity:integrity_dev_only@127.0.0.1:{pg_port}/integrity",
            "REDIS_URL": f"redis://127.0.0.1:{redis_port}",
            "RPC_URL": deployed_chain["rpc_url"],
            "CHAIN_ID": str(deployed_chain["chain_id"]),
            "DEPLOYMENTS_FILE": str(deployments_file),
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
            _wait_for_http_ok(f"{base_url}/healthz", timeout=90.0)
        except Exception:
            out = proc.stdout.read() if proc.stdout else ""
            _kill_tree()
            raise RuntimeError(f"oracle-backend never became healthy. Output:\n{out}")

        yield base_url
    finally:
        _kill_tree()
        subprocess.run(["docker", "rm", "-f", pg_container, redis_container], capture_output=True)


@pytest.fixture
def _env(tmp_path, monkeypatch, deployed_chain):
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "dids"))
    monkeypatch.setenv("INTEGRITY_WALLET_HOME", str(tmp_path / "wallets"))
    monkeypatch.setenv("INTEGRITY_WALLET_PASSWORD", "test-only-password")
    monkeypatch.setenv("RPC_URL", deployed_chain["rpc_url"])
    monkeypatch.setenv("FUNDER_PRIVATE_KEY", deployed_chain["funder"].key.hex())
    # Reuse the SAME real deployments.local.json the oracle_backend fixture points
    # at (the actual file the forge scripts wrote), not a hand-built subset --
    # this is the on-chain state the oracle will independently re-verify against.
    monkeypatch.setenv("DEPLOYMENTS_FILE", str(REPO_ROOT / "deployments.local.json"))


def test_register_agent_full_flow_succeeds_against_real_oracle(oracle_backend, _env):
    """
    The actual regression test: `register_agent()` WITHOUT
    `skip_oracle_registration` must succeed end-to-end against a real,
    running oracle -- and the agent must then be independently visible via a
    real `GET /v1/agents` call. Before the fix, this failed with
    RegistrationError wrapping "422 ... missing field `did`".
    """
    result = registration.register_agent(
        "oracle-e2e-sdk-agent",
        domain_name="general.integrity",
        compliance_vertical="none",
        oracle_url=oracle_backend,
    )

    assert result.oracle_registered is True

    # Independently confirm via a real GET /v1/agent/{did} that the oracle's
    # own on-chain re-verification (XibalbaAgentRegistry.resolveDID) accepted
    # the claimed primitives.
    resp = requests.get(f"{oracle_backend}/v1/agent/{result.did}", timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["has_eth_address"] is True
    assert body["primitives"]["sovereign_agent"].lower() == result.sovereign_agent.lower()

    # And the agent shows up in the list endpoint used for AIS/discovery.
    resp = requests.get(f"{oracle_backend}/v1/agents", timeout=10)
    assert resp.status_code == 200, resp.text
    ids = [row["id"] for row in resp.json()]
    assert result.did in ids, f"registered agent {result.did} did not appear in GET /v1/agents: {ids}"
