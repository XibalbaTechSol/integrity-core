"""Tests for integrity_cli.bcc: canonical JSON, intended_state_hash, nonce
persistence, and BCC Commitment construction/signing (INTERFACE_CONTRACT.md
section 4.2)."""
from __future__ import annotations

import hashlib
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from integrity_cli import bcc


def test_canonical_json_bytes_is_order_independent():
    a = bcc.canonical_json_bytes({"b": 1, "a": 2})
    b = bcc.canonical_json_bytes({"a": 2, "b": 1})
    assert a == b
    assert a == b'{"a":2,"b":1}'


def test_intended_state_hash_is_sha256_of_canonical_payload():
    payload = {"to": "0xabc", "amount": 100}
    expected = "0x" + hashlib.sha256(bcc.canonical_json_bytes(payload)).hexdigest()
    assert bcc.intended_state_hash(payload) == expected
    # Same logical payload, different key order -> same hash.
    assert bcc.intended_state_hash({"amount": 100, "to": "0xabc"}) == expected


def test_next_nonce_is_monotonic_per_agent_and_persists_across_calls():
    assert bcc.next_nonce("agent-1") == 1
    assert bcc.next_nonce("agent-1") == 2
    assert bcc.next_nonce("agent-1") == 3
    # A different agent gets its own independent counter.
    assert bcc.next_nonce("agent-2") == 1

    # Persistence: a fresh read of the nonce file continues where we left off.
    state = json.loads(bcc.NONCE_STATE_FILE.read_text())
    assert state == {"agent-1": 3, "agent-2": 1}


_TEST_CHAIN_ID = 31337
_TEST_VERIFYING_CONTRACT = "0x111111111111111111111111111111111111111a"


def test_build_commitment_has_contract_pinned_field_names():
    key = Ed25519PrivateKey.generate()
    commitment = bcc.build_commitment(
        key, "did:integrity:abc", "payment", {"x": 1}, _TEST_CHAIN_ID, _TEST_VERIFYING_CONTRACT
    )
    assert set(commitment.keys()) == {
        "agent_id",
        "intent_type",
        "intended_state_hash",
        "nonce",
        "timestamp",
        # Reconciled extension fields (see bcc.build_commitment): all signed,
        # all required for the commitment to verify at bcc_middleware.
        "covered_entity_address",
        "agent_public_key",
        "chain_id",
        "verifying_contract",
        "signature",
    }
    assert commitment["chain_id"] == _TEST_CHAIN_ID
    assert commitment["verifying_contract"] == _TEST_VERIFYING_CONTRACT
    assert commitment["agent_id"] == "did:integrity:abc"
    assert commitment["intent_type"] == "payment"
    assert commitment["intended_state_hash"].startswith("0x")
    assert commitment["signature"].startswith("0x")
    assert isinstance(commitment["nonce"], int)
    assert isinstance(commitment["timestamp"], int)


def test_build_commitment_signature_verifies_against_public_key():
    key = Ed25519PrivateKey.generate()
    commitment = bcc.build_commitment(
        key, "did:integrity:abc", "data_access", {"x": 1}, _TEST_CHAIN_ID, _TEST_VERIFYING_CONTRACT
    )

    signed_fields = {k: v for k, v in commitment.items() if k != "signature"}
    signature_bytes = bytes.fromhex(commitment["signature"][2:])

    # Should not raise: the public key must verify the signature over the
    # exact same canonical bytes that were signed.
    key.public_key().verify(signature_bytes, bcc.canonical_json_bytes(signed_fields))


def test_build_commitment_signature_rejects_tampering():
    import pytest
    from cryptography.exceptions import InvalidSignature

    key = Ed25519PrivateKey.generate()
    commitment = bcc.build_commitment(
        key, "did:integrity:abc", "payment", {"x": 1}, _TEST_CHAIN_ID, _TEST_VERIFYING_CONTRACT
    )
    signed_fields = {k: v for k, v in commitment.items() if k != "signature"}
    signature_bytes = bytes.fromhex(commitment["signature"][2:])

    tampered = dict(signed_fields)
    tampered["nonce"] = signed_fields["nonce"] + 1
    with pytest.raises(InvalidSignature):
        key.public_key().verify(signature_bytes, bcc.canonical_json_bytes(tampered))
