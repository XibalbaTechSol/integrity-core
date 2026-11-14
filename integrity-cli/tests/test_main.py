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

# `agent register` is the gas-free off-chain flow (integrity_sdk.registration_offchain):
# it proves control of the identity's Ed25519 key to the Oracle and never touches chain
# state, so it needs no funder key, no RPC and no deployments file. The old on-chain
# "7 primitives" flow was removed outright; `register_offchain` is stubbed here and its
# wire behavior is covered by the SDK's own tests.


def _stub_register_offchain(monkeypatch, *, result=None, error=None):
    from integrity_cli import main as cli_main
    from integrity_sdk.registration_offchain import OffchainRegistration

    calls = []

    def fake(oracle_url, did, keypair, **kwargs):
        calls.append({"oracle_url": oracle_url, "did": did, "keypair": keypair, **kwargs})
        if error is not None:
            raise error
        return result or OffchainRegistration(
            agent_id=did, verification_tier=1, outcome="created", handle=kwargs.get("handle")
        )

    monkeypatch.setattr(cli_main, "register_offchain", fake)
    return calls


def test_agent_register_without_identity_exits_nonzero():
    result = runner.invoke(app, ["agent", "register"])
    assert result.exit_code == 1
    assert "No identity named 'default'" in result.stdout


def test_agent_register_is_offchain_and_needs_no_funder(monkeypatch):
    for var in ("FUNDER_PRIVATE_KEY", "INTEGRITY_WALLET_PASSWORD", "RPC_URL"):
        monkeypatch.delenv(var, raising=False)
    calls = _stub_register_offchain(monkeypatch)
    runner.invoke(app, ["identity", "keygen"])
    did = identity.did_document("default")["id"]
    result = runner.invoke(app, ["agent", "register"])
    assert result.exit_code == 0, result.stdout
    assert "tier=1" in result.stdout
    assert f"registered {did}" in result.stdout
    assert len(calls) == 1
    assert calls[0]["did"] == did
    assert calls[0]["oracle_url"] == "http://localhost:8080"
    assert calls[0]["did_document"]["id"] == did


def test_agent_register_passes_handle(monkeypatch):
    calls = _stub_register_offchain(monkeypatch)
    runner.invoke(app, ["identity", "keygen"])
    result = runner.invoke(
        app, ["agent", "register", "--handle", "my-bot", "--oracle-url", "https://oracle.example"]
    )
    assert result.exit_code == 0, result.stdout
    assert calls[0]["handle"] == "my-bot"
    assert calls[0]["oracle_url"] == "https://oracle.example"


def test_agent_register_reports_conflict_exit_1(monkeypatch):
    from integrity_sdk.registration_offchain import OffchainRegistrationError

    _stub_register_offchain(monkeypatch, error=OffchainRegistrationError(409, "handle already taken"))
    runner.invoke(app, ["identity", "keygen"])
    result = runner.invoke(app, ["agent", "register", "--handle", "taken"])
    assert result.exit_code == 1
    assert "409" in result.stdout
    assert "handle already taken" in result.stdout


def test_agent_register_reports_unreachable_oracle_exit_1(monkeypatch):
    from integrity_sdk.registration_offchain import OffchainRegistrationError

    _stub_register_offchain(monkeypatch, error=OffchainRegistrationError(None, "connection refused"))
    runner.invoke(app, ["identity", "keygen"])
    result = runner.invoke(app, ["agent", "register"])
    assert result.exit_code == 1
    assert "unreachable" in result.stdout.lower()


def test_agent_register_removed_options_are_rejected():
    runner.invoke(app, ["identity", "keygen"])
    for flag in ("--alias", "--skip-oracle", "--rpc-url", "--full"):
        args = ["agent", "register", flag] + ([] if flag in ("--skip-oracle", "--full") else ["x"])
        assert runner.invoke(app, args).exit_code == 2, flag


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
