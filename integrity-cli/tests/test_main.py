"""CliRunner-based tests for the `integrity` Typer app.

HTTP calls are mocked with pytest-httpx (see tests/test_client.py docstring
for why that's a legitimate use of mocks here: we're testing our own CLI
logic, not standing in for integrity-oracle/bcc_middleware).
"""
from __future__ import annotations

import json

from typer.testing import CliRunner

from integrity_cli import chain, config, identity
from integrity_cli.main import app

runner = CliRunner()


# --------------------------------------------------------------------------
# config / auth
# --------------------------------------------------------------------------

def test_config_set_and_show():
    result = runner.invoke(app, ["config", "set", "ORACLE_URL", "http://test-oracle"])
    assert result.exit_code == 0
    assert "ORACLE_URL = http://test-oracle" in result.stdout

    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "http://test-oracle" in result.stdout


def test_config_show_masks_auth_token():
    config.set_config_value("AUTH_TOKEN", "supersecretvalue")
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "supersecretvalue" not in result.stdout
    assert "(masked)" in result.stdout


def test_auth_show_without_token_exits_nonzero():
    result = runner.invoke(app, ["auth", "show"])
    assert result.exit_code == 1
    assert "No AUTH_TOKEN configured" in result.stdout


def test_auth_set_token_then_show():
    result = runner.invoke(app, ["auth", "set-token", "abc123token"])
    assert result.exit_code == 0
    result = runner.invoke(app, ["auth", "show"])
    assert result.exit_code == 0
    assert "abc1" in result.stdout
    assert "abc123token" not in result.stdout  # full token never printed


def test_auth_show_fails_loudly_for_placeholder_outside_local():
    config.set_config_value("ENVIRONMENT", "staging")
    config.set_config_value("AUTH_TOKEN", "mock_demo_token")
    result = runner.invoke(app, ["auth", "show"])
    assert result.exit_code == 1
    assert "Refusing to use placeholder AUTH_TOKEN" in result.stdout


# --------------------------------------------------------------------------
# identity
# --------------------------------------------------------------------------

def test_identity_keygen_and_show():
    result = runner.invoke(app, ["identity", "keygen"])
    assert result.exit_code == 0
    assert "Identity 'default' created" in result.stdout
    assert "did:integrity:" in result.stdout
    assert "Ed25519VerificationKey2020" in result.stdout

    result = runner.invoke(app, ["identity", "show"])
    assert result.exit_code == 0
    assert "did:integrity:" in result.stdout


def test_identity_keygen_refuses_overwrite_without_force():
    runner.invoke(app, ["identity", "keygen"])
    result = runner.invoke(app, ["identity", "keygen"])
    assert result.exit_code == 1
    assert "already exists" in result.stdout

    result = runner.invoke(app, ["identity", "keygen", "--force"])
    assert result.exit_code == 0


def test_identity_show_missing_identity_exits_nonzero():
    result = runner.invoke(app, ["identity", "show", "--name", "nope"])
    assert result.exit_code == 1
    assert "No identity named 'nope'" in result.stdout


# --------------------------------------------------------------------------
# agent
# --------------------------------------------------------------------------

# NOTE on the register tests: `agent register` is no longer a single HTTP POST to the
# oracle — it now runs the real self-sovereign on-chain sequence (fund wallet -> deploy
# SovereignAgent + StateAnchor -> clone the other 5 primitives via AgentPrimitivesFactory
# -> optional oracle POST). The old httpx-mocked "success"/"oracle error" tests no longer
# describe how the command works, so they're replaced here by tests of the command's real
# pre-flight error paths (fast, no chain needed); the full happy path is covered against a
# real anvil chain in tests/test_chain.py, mirroring integrity-sdk's own real-chain test.


def test_agent_register_without_identity_exits_nonzero():
    result = runner.invoke(app, ["agent", "register", "--alias", "my-bot"])
    assert result.exit_code == 1
    assert "No identity named 'default'" in result.stdout


def test_agent_register_requires_funder_key(monkeypatch, tmp_path):
    """The funder is resolved lazily -- only once a funding step is actually needed --
    so the missing-key error can only surface on a reachable chain where the fresh
    agent wallet has no funds. Stub exactly the chain reads that come before that
    first funding step (idempotency, registrar role, domain membership) so the test
    runs without a live RPC; previously it only passed when something happened to be
    listening on localhost:8545, and failed in CI."""
    monkeypatch.delenv("FUNDER_PRIVATE_KEY", raising=False)
    # The agent wallet keystore is created before any funding step; give it a throwaway
    # password so the run reaches the funder check (CI has none set).
    monkeypatch.setenv("INTEGRITY_WALLET_PASSWORD", "test-only-password")

    class _Eth(_FakeEth):
        def get_balance(self, address) -> int:  # fresh wallet: nothing to spend
            return 0

    class _W3(_FakeConnectedW3):
        eth = _Eth()

    monkeypatch.setattr(chain, "get_w3", lambda rpc_url: _W3())
    monkeypatch.setattr(chain, "resolve_did", lambda *a, **k: None)
    monkeypatch.setattr(chain, "factory_has_registrar_role", lambda *a, **k: True)
    monkeypatch.setattr(chain, "domain_exists", lambda *a, **k: True)
    monkeypatch.setattr(chain, "can_join_domain", lambda *a, **k: True)
    deployments_file = tmp_path / "deployments.local.json"
    deployments_file.write_text(json.dumps({
        "singletons": {
            name: "0x" + f"{i:02x}" * 20
            for i, name in enumerate(
                ["AgentPrimitivesFactory", "IntegrityToken", "XibalbaAgentRegistry", "DomainRegistry"], start=1
            )
        },
        "protocolAddresses": {"oracleSigner": "0x" + "55" * 20},
    }))

    runner.invoke(app, ["identity", "keygen"])
    result = runner.invoke(app, ["agent", "register", "--alias", "my-bot", "--deployments-file", str(deployments_file)])
    assert result.exit_code == 1
    # The funder wallet pays for the agent's on-chain deploys; without it, the command
    # must stop with a clear message rather than a confusing mid-sequence RPC failure.
    assert "FUNDER_PRIVATE_KEY" in result.stdout


def test_agent_register_requires_reachable_rpc(monkeypatch):
    monkeypatch.setenv("FUNDER_PRIVATE_KEY", "0x" + "ac" * 32)
    # Point at a port nothing is listening on so the RPC connectivity pre-check trips
    # (this comes after the funder-key check but before any real transaction).
    monkeypatch.setenv("RPC_URL", "http://127.0.0.1:1")
    runner.invoke(app, ["identity", "keygen"])
    result = runner.invoke(app, ["agent", "register", "--alias", "my-bot"])
    assert result.exit_code == 1
    assert "RPC" in result.stdout or "connect" in result.stdout


def test_agent_show(httpx_mock):
    httpx_mock.add_response(
        method="GET",
        url="http://localhost:8080/v1/agent/did:integrity:abc",
        json={"agent_id": "did:integrity:abc", "alias": "bot"},
    )
    result = runner.invoke(app, ["agent", "show", "did:integrity:abc"])
    assert result.exit_code == 0
    assert "did:integrity:abc" in result.stdout


def test_agent_ais(httpx_mock):
    httpx_mock.add_response(
        method="GET",
        url="http://localhost:8080/v1/agent/did:integrity:abc/ais",
        json={"ais": 87.5, "zk_boost": 1.15},
    )
    result = runner.invoke(app, ["agent", "ais", "did:integrity:abc"])
    assert result.exit_code == 0
    assert "87.5" in result.stdout


def _set_resolvable_deployments_file(tmp_path, monkeypatch) -> None:
    """`agent intercept` now resolves chain_id/verifying_contract from
    DEPLOYMENTS_FILE (docs/plans/2026-08-18-phase1-canonical-intent-encoding-
    proposal.md) -- point it at a throwaway file with just enough shape to
    resolve, rather than relying on whatever the ambient repo-root .env
    happens to have configured."""
    deployments_file = tmp_path / "deployments.local.json"
    deployments_file.write_text(json.dumps({
        "chainId": 31337,
        "singletons": {"XibalbaAgentRegistry": "0x111111111111111111111111111111111111111a"},
    }))
    monkeypatch.setenv("DEPLOYMENTS_FILE", str(deployments_file))


def test_agent_intercept_authorized(httpx_mock, tmp_path, monkeypatch):
    _set_resolvable_deployments_file(tmp_path, monkeypatch)
    runner.invoke(app, ["identity", "keygen"])
    httpx_mock.add_response(
        method="POST",
        url="http://localhost:8000/v1/bcc/intercept",
        json={"authorized": True, "reason": "policy ok", "verification_token": "tok-1"},
    )
    result = runner.invoke(
        app, ["agent", "intercept", "-t", "payment", "-p", '{"amount": 5}']
    )
    assert result.exit_code == 0
    assert "AUTHORIZED" in result.stdout
    assert "tok-1" in result.stdout

    # The request body must be the bare commitment object per
    # INTERFACE_CONTRACT.md section 4.2 -- not wrapped in an envelope.
    request = httpx_mock.get_requests()[0]
    body = json.loads(request.content)
    assert set(body.keys()) == {
        "agent_id", "intent_type", "intended_state_hash", "nonce", "timestamp",
        "covered_entity_address", "agent_public_key", "chain_id", "verifying_contract", "signature",
    }
    assert body["intent_type"] == "payment"
    assert body["chain_id"] == 31337
    assert body["verifying_contract"] == "0x111111111111111111111111111111111111111a"


def test_agent_intercept_rejected_exits_nonzero(httpx_mock, tmp_path, monkeypatch):
    _set_resolvable_deployments_file(tmp_path, monkeypatch)
    runner.invoke(app, ["identity", "keygen"])
    httpx_mock.add_response(
        method="POST",
        url="http://localhost:8000/v1/bcc/intercept",
        json={"authorized": False, "reason": "policy violation: HIPAA"},
    )
    result = runner.invoke(app, ["agent", "intercept", "-t", "data_access", "-p", "{}"])
    assert result.exit_code == 1
    assert "REJECTED" in result.stdout
    assert "HIPAA" in result.stdout


def test_agent_intercept_invalid_payload_json():
    runner.invoke(app, ["identity", "keygen"])
    result = runner.invoke(app, ["agent", "intercept", "-t", "payment", "-p", "not-json"])
    assert result.exit_code == 1
    assert "Invalid --payload JSON" in result.stdout


def test_agent_intercept_without_identity_exits_nonzero():
    result = runner.invoke(app, ["agent", "intercept", "-t", "payment", "-p", "{}"])
    assert result.exit_code == 1
    assert "No identity named 'default'" in result.stdout


def test_agent_intercept_middleware_unreachable(httpx_mock, tmp_path, monkeypatch):
    import httpx as httpx_module

    _set_resolvable_deployments_file(tmp_path, monkeypatch)
    runner.invoke(app, ["identity", "keygen"])
    httpx_mock.add_exception(httpx_module.ConnectError("refused"))
    result = runner.invoke(app, ["agent", "intercept", "-t", "payment", "-p", "{}"])
    assert result.exit_code == 1
    assert "Error querying BCC middleware" in result.stdout


# --------------------------------------------------------------------------
# xns
# --------------------------------------------------------------------------

# NOTE: like `agent register`, the five `xns` commands (see main.py's
# `_xns_setup`/`_resolve_own_sovereign_agent`) run a real on-chain sequence --
# the full happy path against a real anvil chain is covered by
# tests/test_chain.py, mirroring the "real integration test" pattern used for
# `agent register`. What's tested here is the CLI's own argument-parsing and
# error-surfacing layer: the pre-flight checks every xns command runs before
# it ever needs a live chain (RPC reachability) or a funded wallet
# (INTEGRITY_WALLET_PASSWORD), fast and with no external services required.


class _FakeEth:
    chain_id = 31337


class _FakeConnectedW3:
    """Stands in for `chain.get_w3(...)` once RPC connectivity has already
    been established -- lets these tests reach the wallet-password check in
    the write commands without needing a real anvil chain listening."""

    eth = _FakeEth()

    def is_connected(self) -> bool:
        return True


def _write_xns_deployments(tmp_path) -> str:
    """A minimal deployments.local.json with just the one key `_xns_setup`
    reads (`singletons.XibalbaNameService`)."""
    deployments_file = tmp_path / "deployments.local.json"
    deployments_file.write_text(
        json.dumps({"singletons": {"XibalbaNameService": "0x" + "11" * 20}})
    )
    return str(deployments_file)


def test_xns_resolve_requires_reachable_rpc(monkeypatch):
    monkeypatch.setenv("RPC_URL", "http://127.0.0.1:1")
    result = runner.invoke(app, ["xns", "resolve", "hermes.integrity"])
    assert result.exit_code == 1
    assert "RPC" in result.stdout or "connect" in result.stdout


def test_xns_primary_handle_requires_reachable_rpc(monkeypatch):
    monkeypatch.setenv("RPC_URL", "http://127.0.0.1:1")
    result = runner.invoke(app, ["xns", "primary-handle", "0x" + "22" * 20])
    assert result.exit_code == 1
    assert "RPC" in result.stdout or "connect" in result.stdout


def test_xns_register_without_identity_exits_nonzero(monkeypatch, tmp_path):
    # RPC/deployments both resolve fine here -- the command should still stop
    # at the identity check (mirrors `agent register`'s equivalent test)
    # rather than reaching any wallet/chain logic.
    monkeypatch.setattr(chain, "get_w3", lambda rpc_url: _FakeConnectedW3())
    deployments_file = _write_xns_deployments(tmp_path)
    result = runner.invoke(
        app,
        ["xns", "register", "hermes.integrity", "--deployments-file", deployments_file],
    )
    assert result.exit_code == 1
    assert "No identity named 'default'" in result.stdout


def _register_identity_and_mock_sovereign_agent(httpx_mock, sovereign_agent: str) -> None:
    runner.invoke(app, ["identity", "keygen"])
    did = identity.did_document("default")["id"]
    httpx_mock.add_response(
        method="GET",
        url=f"http://localhost:8080/v1/agent/{did}",
        json={"primitives": {"sovereign_agent": sovereign_agent}},
    )


def test_xns_register_requires_wallet_password(monkeypatch, tmp_path, httpx_mock):
    monkeypatch.delenv("INTEGRITY_WALLET_PASSWORD", raising=False)
    monkeypatch.setattr(chain, "get_w3", lambda rpc_url: _FakeConnectedW3())
    deployments_file = _write_xns_deployments(tmp_path)
    sovereign_agent = "0x" + "33" * 20
    _register_identity_and_mock_sovereign_agent(httpx_mock, sovereign_agent)

    result = runner.invoke(
        app,
        ["xns", "register", "hermes.integrity", "--deployments-file", deployments_file],
    )
    assert result.exit_code == 1
    assert "INTEGRITY_WALLET_PASSWORD" in result.stdout


def test_xns_set_primary_requires_wallet_password(monkeypatch, tmp_path, httpx_mock):
    monkeypatch.delenv("INTEGRITY_WALLET_PASSWORD", raising=False)
    monkeypatch.setattr(chain, "get_w3", lambda rpc_url: _FakeConnectedW3())
    deployments_file = _write_xns_deployments(tmp_path)
    sovereign_agent = "0x" + "44" * 20
    _register_identity_and_mock_sovereign_agent(httpx_mock, sovereign_agent)

    result = runner.invoke(
        app,
        ["xns", "set-primary", "hermes.integrity", "--deployments-file", deployments_file],
    )
    assert result.exit_code == 1
    assert "INTEGRITY_WALLET_PASSWORD" in result.stdout


def test_xns_release_requires_wallet_password(monkeypatch, tmp_path, httpx_mock):
    monkeypatch.delenv("INTEGRITY_WALLET_PASSWORD", raising=False)
    monkeypatch.setattr(chain, "get_w3", lambda rpc_url: _FakeConnectedW3())
    deployments_file = _write_xns_deployments(tmp_path)
    sovereign_agent = "0x" + "55" * 20
    _register_identity_and_mock_sovereign_agent(httpx_mock, sovereign_agent)

    result = runner.invoke(
        app,
        ["xns", "release", "hermes.integrity", "--deployments-file", deployments_file],
    )
    assert result.exit_code == 1
    assert "INTEGRITY_WALLET_PASSWORD" in result.stdout


# --------------------------------------------------------------------------
# hooks install --gate shield: what the operator is told
# --------------------------------------------------------------------------

def test_hooks_install_shield_warns_that_the_runner_fails_open_without_a_daemon(tmp_path, monkeypatch):
    for var in ("HERMES_HOME", "CODEX_HOME", "CLAUDE_CONFIG_DIR", "INTEGRITY_PROFILE_ROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "did_home"))
    monkeypatch.setenv("XIBALBA_SHIELD_GATE_SOCKET", str(tmp_path / "gate.sock"))
    root = tmp_path / "harness_root"
    root.mkdir()

    result = runner.invoke(app, ["hooks", "install", "--harness", "claude-code", "--gate", "shield",
                                 "--profile-root", str(root)])

    assert result.exit_code == 0, result.output
    output = " ".join(result.output.split())  # rich wraps lines; compare on normalized text
    assert "no Shield gate daemon is listening" in output
    assert "UNCHECKED" in output
    assert "--register-agent did:" in output, "the operator needs the DID to give the daemon"


def test_hooks_install_bcc_prints_no_shield_guidance(tmp_path, monkeypatch):
    for var in ("HERMES_HOME", "CODEX_HOME", "CLAUDE_CONFIG_DIR", "INTEGRITY_PROFILE_ROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "did_home"))
    root = tmp_path / "harness_root"
    root.mkdir()

    result = runner.invoke(app, ["hooks", "install", "--harness", "claude-code", "--gate", "bcc",
                                 "--profile-root", str(root)])

    assert result.exit_code == 0, result.output
    assert "Shield" not in result.output
