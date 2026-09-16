from integrity_sdk.readiness import assess_local_readiness
from integrity_sdk.did import load_or_create_did
from integrity_sdk.memory_dag import MemoryGraph, MemoryNode
import sqlite3


def test_readiness_reports_missing_authority_as_unknown_without_mutation(tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "did"))
    monkeypatch.setenv("INTEGRITY_WALLET_HOME", str(tmp_path / "wallet"))
    monkeypatch.setenv("INTEGRITY_VAULT_HOME", str(tmp_path / "vault"))
    result = assess_local_readiness("new-agent")
    assert result.ready is False
    assert {check.name for check in result.checks} >= {"identity_and_key_continuity", "persistent_memory", "memory_genesis", "wallet_available", "on_chain_preflight", "oracle_registration"}
    assert not (tmp_path / "did" / "new-agent" / "private_key.pem").exists()


def test_readiness_resolves_slug_to_did_scoped_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "did"))
    monkeypatch.setenv("INTEGRITY_WALLET_HOME", str(tmp_path / "wallet"))
    monkeypatch.setenv("INTEGRITY_VAULT_HOME", str(tmp_path / "vault"))

    did, _, _ = load_or_create_did("agent-slug")
    graph = MemoryGraph(did, home=tmp_path / "vault")
    graph.append(MemoryNode(
        agent_id=did,
        kind="memory",
        content_hash="0x" + "11" * 32,
        parents=(),
        edge_type="genesis",
        timestamp=1,
        source="readiness-test",
    ))

    result = assess_local_readiness("agent-slug")
    checks = {check.name: check for check in result.checks}
    assert checks["identity_and_key_continuity"].status == "pass"
    assert checks["persistent_memory"].status == "pass"
    assert checks["memory_genesis"].status == "pass"


def test_readiness_detects_cortex_memory_and_requires_explicit_root(tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "did"))
    monkeypatch.setenv("INTEGRITY_WALLET_HOME", str(tmp_path / "wallet"))
    did, _, _ = load_or_create_did("cortex-agent")
    cortex_home = tmp_path / "cortex"
    cortex_home.mkdir()
    connection = sqlite3.connect(cortex_home / "graph-memory.sqlite3")
    connection.executescript("""
        CREATE TABLE sources (id TEXT PRIMARY KEY, agent_id TEXT);
        CREATE TABLE memories (id TEXT PRIMARY KEY, source_id TEXT);
    """)
    connection.execute("INSERT INTO sources VALUES (?, ?)", ("source-1", did))
    connection.execute("INSERT INTO memories VALUES (?, ?)", ("memory-1", "source-1"))
    connection.commit()
    connection.close()

    result = assess_local_readiness("cortex-agent", cortex_home=cortex_home, onchain_genesis_root="0x" + "22" * 32)
    checks = {check.name: check for check in result.checks}
    assert checks["persistent_memory"].status == "pass"
    assert checks["memory_genesis"].status == "pass"
    assert checks["memory_genesis"].authoritative is True
