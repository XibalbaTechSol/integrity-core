"""
Regression tests for PRODUCTION_GAPS.md §28: `integrity agent register` used to have
NO idempotency protection at all (unlike integrity_sdk.registration, which at least
checked resolve_did before this fix) -- every invocation deployed a fresh
SovereignAgent/StateAnchor pair, even for an already-registered DID or a retry after a
failure partway through. Real gas spent, real orphaned contracts on Base Sepolia across
multiple sessions (see that section for the full incident history).

Runs against a real local anvil chain (`deployed_chain` fixture below, same shape as
test_register_oracle_e2e.py's) with `--skip-oracle` -- no Docker/cargo/oracle-backend
needed, so this is cheap to run and doesn't require the heavier ORACLE_E2E=1 opt-in.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from eth_account import Account
from typer.testing import CliRunner
from web3 import Web3

from integrity_cli import chain as chain_module
from integrity_cli.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "contracts"
ANVIL_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"


def _free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def deployed_chain(tmp_path):
    """Real anvil + real Deploy.s.sol, function-scoped (unlike
    test_register_oracle_e2e.py's module-scoped fixture) so each test starts from a
    clean chain -- these tests specifically need to control what's already on-chain."""
    if shutil.which("anvil") is None or shutil.which("forge") is None:
        pytest.skip("anvil/forge (foundry) required")

    port = _free_port()
    rpc_url = f"http://127.0.0.1:{port}"

    deployments_file = tmp_path / "deployments.local.json"
    deployments_file.touch()

    proc = subprocess.Popen(["anvil", "--port", str(port), "--silent"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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

        import os as _os

        env = {**_os.environ, "FUNDER_PRIVATE_KEY": ANVIL_KEY}
        result = subprocess.run(
            ["forge", "script", "script/Deploy.s.sol", "--rpc-url", rpc_url, "--broadcast"],
            cwd=CONTRACTS_DIR, capture_output=True, text=True, env=env,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Deploy.s.sol failed:\n{result.stdout}\n{result.stderr}")
        # Deploy.s.sol always writes to the repo-root deployments.local.json -- copy it
        # into this test's own tmp_path so each test gets an independent copy to point
        # --deployments-file at (tests in this file run serially, not parallel, so the
        # shared repo-root write itself is not a race).
        repo_deployments = REPO_ROOT / "deployments.local.json"
        deployments_file.write_text(repo_deployments.read_text())

        yield {
            "rpc_url": rpc_url,
            "chain_id": w3.eth.chain_id,
            "w3": w3,
            "funder": Account.from_key(ANVIL_KEY),
            "deployments_file": str(deployments_file),
        }
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def _register_args(deployed_chain, **overrides):
    args = [
        "agent", "register",
        "--alias", "resume-test-agent",
        "--rpc-url", deployed_chain["rpc_url"],
        "--deployments-file", deployed_chain["deployments_file"],
        "--skip-oracle",
    ]
    for flag, value in overrides.items():
        args += [flag, value]
    return args


def test_agent_register_resumes_from_partial_failure_without_redeploying(deployed_chain, monkeypatch):
    monkeypatch.setenv("FUNDER_PRIVATE_KEY", deployed_chain["funder"].key.hex())
    monkeypatch.setenv("INTEGRITY_WALLET_PASSWORD", "resume-test-pw")

    runner = CliRunner()
    keygen_result = runner.invoke(app, ["identity", "keygen"])
    assert keygen_result.exit_code == 0, keygen_result.stdout

    real_register_primitives = chain_module.register_primitives
    call_count = {"n": 0}

    def flaky_register_primitives(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated registerPrimitives revert (e.g. a missing role grant)")
        return real_register_primitives(*args, **kwargs)

    monkeypatch.setattr(chain_module, "register_primitives", flaky_register_primitives)

    first = runner.invoke(app, _register_args(deployed_chain))
    assert first.exit_code != 0, first.stdout
    assert "Error during on-chain registration" in first.stdout

    from integrity_cli import identity

    progress_path = identity.IDENTITY_DIR / "default.registration_progress.json"
    assert progress_path.exists(), first.stdout
    progress = json.loads(progress_path.read_text())
    assert progress["sovereign_agent"].startswith("0x")
    assert progress["state_anchor"].startswith("0x")

    second = runner.invoke(app, _register_args(deployed_chain))
    assert second.exit_code == 0, second.stdout
    assert call_count["n"] == 2
    assert "reusing already-deployed SovereignAgent" in second.stdout
    assert "reusing already-deployed StateAnchor" in second.stdout

    primitives_path = identity.IDENTITY_DIR / "default.primitives.json"
    result = json.loads(primitives_path.read_text())
    assert result["sovereign_agent"].lower() == progress["sovereign_agent"].lower()
    assert result["state_anchor"].lower() == progress["state_anchor"].lower()
    assert not progress_path.exists()  # cleared once registration genuinely completed


def test_agent_register_is_idempotent_for_an_already_registered_did(deployed_chain, monkeypatch):
    monkeypatch.setenv("FUNDER_PRIVATE_KEY", deployed_chain["funder"].key.hex())
    monkeypatch.setenv("INTEGRITY_WALLET_PASSWORD", "idempotent-test-pw")

    runner = CliRunner()
    assert runner.invoke(app, ["identity", "keygen"]).exit_code == 0

    first = runner.invoke(app, _register_args(deployed_chain))
    assert first.exit_code == 0, first.stdout

    from integrity_cli import identity

    first_primitives = json.loads((identity.IDENTITY_DIR / "default.primitives.json").read_text())

    second = runner.invoke(app, _register_args(deployed_chain))
    assert second.exit_code == 0, second.stdout
    assert "already registered on-chain" in second.stdout

    second_primitives = json.loads((identity.IDENTITY_DIR / "default.primitives.json").read_text())
    assert second_primitives["sovereign_agent"].lower() == first_primitives["sovereign_agent"].lower()
