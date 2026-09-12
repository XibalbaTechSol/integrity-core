from __future__ import annotations

import pytest

from integrity_sdk import did


@pytest.fixture(autouse=True)
def _did_env(tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "dids"))


def test_load_or_create_did_generates_fresh_identity():
    """Regression test for a real bug: load_or_create_did previously called
    an undefined `_agent_dir` (NameError at runtime, never caught because no
    test exercised this function before)."""
    agent_did, keypair, doc = did.load_or_create_did("agent-a")
    assert agent_did.startswith("did:integrity:")
    assert doc["id"] == agent_did
    assert doc["verificationMethod"][0]["type"] == "Ed25519VerificationKey2020"


def test_load_or_create_did_is_stable_across_reloads():
    did1, _, _ = did.load_or_create_did("agent-a")
    did2, _, _ = did.load_or_create_did("agent-a")
    assert did1 == did2


def test_different_agents_get_different_dids():
    did1, _, _ = did.load_or_create_did("agent-a")
    did2, _, _ = did.load_or_create_did("agent-b")
    assert did1 != did2


def test_missing_document_is_losslessly_repaired_not_regenerated():
    """The one case that previously destroyed a key: a partial restore, an interrupted write, a
    container recreation that only mounted the key -- anything that leaves the key on disk but
    loses document.json. This must reconstruct the document from the key, not mint a new one."""
    original_did, original_keypair, _ = did.load_or_create_did("agent-a")
    agent_dir = did.agent_dir("agent-a")
    (agent_dir / "document.json").unlink()

    repaired_did, repaired_keypair, repaired_doc = did.load_or_create_did("agent-a")

    assert repaired_did == original_did
    assert repaired_keypair.private_bytes_raw() == original_keypair.private_bytes_raw()
    assert (agent_dir / "document.json").exists()
    assert repaired_doc["id"] == original_did


def test_mismatched_document_fails_closed_and_leaves_key_untouched():
    """A document that doesn't match the key is ambiguous -- either file could be the wrong
    one -- so this must raise rather than guess by regenerating the key."""
    original_did, original_keypair, _ = did.load_or_create_did("agent-a")
    agent_dir = did.agent_dir("agent-a")
    other_did, _, other_doc = did.load_or_create_did("agent-b")
    (agent_dir / "document.json").write_text(__import__("json").dumps(other_doc))

    with pytest.raises(did.IdentityInconsistentError):
        did.load_or_create_did("agent-a")

    # The private key must survive the failed call untouched -- the entire point of failing
    # closed is that a bad document must never cost you the key.
    key_bytes = (agent_dir / "private_key.pem").read_bytes()
    assert did.Keypair.from_pem(key_bytes).private_bytes_raw() == original_keypair.private_bytes_raw()


def test_missing_key_with_surviving_document_fails_closed():
    """A document with no key behind it cannot be repaired -- there is no way to reconstruct a
    private key from public data -- so this must fail rather than mint a replacement identity."""
    did.load_or_create_did("agent-a")
    agent_dir = did.agent_dir("agent-a")
    (agent_dir / "private_key.pem").unlink()

    with pytest.raises(did.IdentityInconsistentError):
        did.load_or_create_did("agent-a")


def test_attach_evm_account_adds_caip10_verification_method():
    _, _, doc = did.load_or_create_did("agent-a")
    evm_address = "0x1234567890123456789012345678901234567890"
    doc = did.attach_evm_account(doc, evm_address, chain_id=84532)

    evm_methods = [
        vm for vm in doc["verificationMethod"] if vm["type"] == "EcdsaSecp256k1RecoveryMethod2020"
    ]
    assert len(evm_methods) == 1
    assert evm_methods[0]["blockchainAccountId"] == f"eip155:84532:{evm_address}"
    assert evm_methods[0]["controller"] == doc["id"]
    # Original Ed25519 verification method must still be present — attaching
    # the EVM account extends the document, never replaces the DID key.
    assert any(vm["type"] == "Ed25519VerificationKey2020" for vm in doc["verificationMethod"])
