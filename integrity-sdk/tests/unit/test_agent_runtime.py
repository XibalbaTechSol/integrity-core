from __future__ import annotations

import pytest

from integrity_sdk import IntegrityAgent
from integrity_sdk.agent_runtime import AgentIdentityError
from integrity_sdk import did
from integrity_sdk.mcp_server import _load_doc_for, _load_keypair_for


def test_each_slug_gets_a_stable_unique_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "dids"))
    xibalba = IntegrityAgent.open("xibalba", harness="hermes", client_kwargs={"auto_flush": False, "enable_otel_export": False})
    quant = IntegrityAgent.open("xibalba-quant", harness="hermes", profile="xibalba-quant", client_kwargs={"auto_flush": False, "enable_otel_export": False})
    assert xibalba.did != quant.did
    assert IntegrityAgent.open("xibalba", harness="hermes", client_kwargs={"auto_flush": False, "enable_otel_export": False}).did == xibalba.did
    xibalba.close(flush=False)
    quant.close(flush=False)


def test_expected_did_mismatch_refuses_attribution(tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "dids"))
    with pytest.raises(AgentIdentityError, match="expected"):
        IntegrityAgent.open("claude", harness="claude", expected_did="did:integrity:not-this-agent", client_kwargs={"auto_flush": False, "enable_otel_export": False})


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
