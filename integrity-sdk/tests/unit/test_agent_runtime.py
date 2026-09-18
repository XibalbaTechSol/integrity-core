from __future__ import annotations

import pytest

from integrity_sdk import IntegrityAgent
from integrity_sdk.agent_runtime import AgentIdentityError
from integrity_sdk import did
from integrity_sdk.mcp_server import _load_doc_for, _load_keypair_for
from integrity_sdk.identity_registry import history, latest


def test_each_slug_gets_a_stable_unique_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "dids"))
    xibalba = IntegrityAgent.open("xibalba", harness="hermes", client_kwargs={"auto_flush": False, "enable_otel_export": False})
    quant = IntegrityAgent.open("xibalba-quant", harness="hermes", profile="xibalba-quant", client_kwargs={"auto_flush": False, "enable_otel_export": False})
    assert xibalba.did != quant.did
    assert IntegrityAgent.open("xibalba", harness="hermes", client_kwargs={"auto_flush": False, "enable_otel_export": False}).did == xibalba.did
    xibalba.close(flush=False)
    quant.close(flush=False)


def test_profile_root_scopes_identity_and_records_canonical_root(tmp_path, monkeypatch):
    monkeypatch.delenv("INTEGRITY_DID_HOME", raising=False)
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    profile_root = tmp_path / "profiles" / "agent-a"
    profile_root.mkdir(parents=True)
    agent = IntegrityAgent.open(
        "agent-a", harness="hermes", profile="agent-a", profile_root=profile_root,
        client_kwargs={"auto_flush": False, "enable_otel_export": False},
    )
    canonical = profile_root / ".integrity" / "did" / "agent-a"
    assert (canonical / "document.json").is_file()
    assert (canonical / "private_key.pem").is_file()
    snapshot = agent.identity_snapshot()
    assert snapshot["profile_root"] == str(profile_root.resolve())
    assert snapshot["identity_store_reference"] == str(canonical)
    binding_path = profile_root / ".integrity" / "identity.json"
    assert binding_path.is_file()
    reopened = IntegrityAgent.open(
        harness="hermes", profile_root=profile_root,
        client_kwargs={"auto_flush": False, "enable_otel_export": False},
    )
    assert reopened.agent_slug == "agent-a"
    assert reopened.did == agent.did
    with pytest.raises(AgentIdentityError, match="bound to agent"):
        IntegrityAgent.open(
            "other-agent", harness="hermes", profile_root=profile_root,
            client_kwargs={"auto_flush": False, "enable_otel_export": False},
        )
    reopened.close(flush=False)
    agent.close(flush=False)


def test_profile_root_must_be_an_existing_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "dids"))
    with pytest.raises(AgentIdentityError, match="existing directory"):
        IntegrityAgent.open(
            "agent-a", harness="codex", profile_root=tmp_path / "missing",
            client_kwargs={"auto_flush": False, "enable_otel_export": False},
        )


def test_harness_home_environment_scopes_default_did_home(tmp_path, monkeypatch):
    monkeypatch.delenv("INTEGRITY_DID_HOME", raising=False)
    profile_root = tmp_path / "codex-home"
    profile_root.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(profile_root))
    agent = IntegrityAgent.open(
        "agent-a", harness="codex",
        client_kwargs={"auto_flush": False, "enable_otel_export": False},
    )
    assert (profile_root / ".integrity" / "did" / "agent-a" / "document.json").is_file()
    assert agent.identity_snapshot()["profile_root"] == str(profile_root.resolve())
    agent.close(flush=False)


def test_expected_did_mismatch_refuses_attribution(tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "dids"))
    with pytest.raises(AgentIdentityError, match="expected"):
        IntegrityAgent.open("claude", harness="claude", expected_did="did:integrity:not-this-agent", client_kwargs={"auto_flush": False, "enable_otel_export": False})
    assert not (tmp_path / "dids" / "claude").exists()


def test_profile_binding_rejects_conflicting_expected_did(tmp_path, monkeypatch):
    monkeypatch.delenv("INTEGRITY_DID_HOME", raising=False)
    root = tmp_path / "bound-profile"
    root.mkdir()
    agent = IntegrityAgent.open(
        "agent-a", harness="hermes", profile_root=root,
        client_kwargs={"auto_flush": False, "enable_otel_export": False},
    )
    agent.close(flush=False)
    with pytest.raises(AgentIdentityError, match="conflicts with the profile identity binding"):
        IntegrityAgent.open(
            "agent-a", harness="hermes", profile_root=root,
            expected_did="did:integrity:not-this-agent",
            client_kwargs={"auto_flush": False, "enable_otel_export": False},
        )
    assert (root / ".integrity" / "identity.json").is_file()


def test_shield_requires_device_binding(tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "dids"))
    with pytest.raises(AgentIdentityError, match="device_id"):
        IntegrityAgent.open("xibalba-shield", harness="hermes", require_device_binding=True, client_kwargs={"auto_flush": False, "enable_otel_export": False})


def test_lifecycle_events_carry_immutable_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "dids"))
    agent = IntegrityAgent.open("agy", harness="antigravity", client_kwargs={"auto_flush": False, "enable_otel_export": False})
    agent.start_session("session-1")
    agent.model_call(model="test-model")
    entries = agent.client._batcher.get_batch_and_clear()
    assert {entry["metadata"]["event"] for entry in entries} == {"session_started", "model_call"}
    for entry in entries:
        assert entry["metadata"]["agent_did"] == agent.did
        assert entry["metadata"]["agent_slug"] == "agy"
        assert entry["metadata"]["harness"] == "antigravity"
    agent.close(flush=False)


def test_mcp_loaders_use_the_canonical_sdk_identity_store(tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "dids"))
    expected_did, expected_keypair, _ = did.load_or_create_did("mcp-agent")
    assert _load_keypair_for("mcp-agent").private_bytes_raw() == expected_keypair.private_bytes_raw()
    assert _load_doc_for("mcp-agent")["id"] == expected_did


def test_identity_snapshot_is_non_secret_and_keeps_boundaries_distinct(tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "dids"))
    agent = IntegrityAgent.open(
        "snapshot-agent", harness="hermes", principal="cortex-principal",
        device_id="shield-device", client_kwargs={"auto_flush": False, "enable_otel_export": False},
    )
    snapshot = agent.identity_snapshot()
    assert snapshot["agent_id"] == "snapshot-agent"
    assert snapshot["did"] == agent.did
    assert snapshot["principal"] == "cortex-principal"
    assert snapshot["device_id"] == "shield-device"
    assert snapshot["did_controller"] == agent.did
    assert snapshot["key_fingerprint"] in agent.did
    assert "private" not in str(snapshot).lower()
    assert "keypair" not in str(snapshot).lower()
    agent.close(flush=False)


def test_runtime_open_records_append_only_identity_registry_observation(tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "dids"))
    agent = IntegrityAgent.open("registry-agent", harness="codex", principal="principal-1",
                               device_id="device-1", client_kwargs={"auto_flush": False, "enable_otel_export": False})
    agent.close(flush=False)
    agent2 = IntegrityAgent.open("registry-agent", harness="codex", principal="principal-1",
                                device_id="device-1", client_kwargs={"auto_flush": False, "enable_otel_export": False})
    rows = history("registry-agent")
    assert len(rows) == 2
    assert latest("registry-agent")["did"] == agent.did
    assert all("private_key" not in row and "keypair" not in row for row in rows)
    assert {row["event"] for row in rows} == {"identity_loaded"}
    agent2.close(flush=False)
