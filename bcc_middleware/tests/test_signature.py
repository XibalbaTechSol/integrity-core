"""
Tests for app/canonical.py -- real Ed25519 signature verification, no mocks.
"""

import pytest
from pydantic import ValidationError

from app.canonical import SignatureVerificationError, verify_commitment_signature
from tests.helpers import make_commitment_model, new_agent, sign_commitment


def test_valid_signature_verifies():
    agent_id, private_key = new_agent()
    payload = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=1)
    commitment = make_commitment_model(**payload)
    verify_commitment_signature(commitment)  # must not raise


def test_tampered_field_after_signing_is_rejected():
    agent_id, private_key = new_agent()
    payload = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=1)
    payload["intent_type"] = "DISPENSE_MEDICATION"  # tampered after signing
    commitment = make_commitment_model(**payload)
    with pytest.raises(SignatureVerificationError):
        verify_commitment_signature(commitment)


def test_invocation_id_is_covered_by_the_signature():
    agent_id, private_key = new_agent()
    payload = sign_commitment(
        private_key,
        agent_id=agent_id,
        invocation_id="018f47a2-4e31-7c90-b187-8d4f82d6c921",
    )
    payload["invocation_id"] = "018f47a2-4e31-7c90-b187-8d4f82d6c922"

    with pytest.raises(SignatureVerificationError):
        verify_commitment_signature(make_commitment_model(**payload))


def test_legacy_commitment_without_invocation_id_still_verifies():
    agent_id, private_key = new_agent()
    payload = sign_commitment(private_key, agent_id=agent_id)

    commitment = make_commitment_model(**payload)
    assert commitment.invocation_id is None
    verify_commitment_signature(commitment)


@pytest.mark.parametrize(
    "invocation_id",
    [
        "not-a-uuid",
        "018F47A2-4E31-7C90-B187-8D4F82D6C921",
        "{018f47a2-4e31-7c90-b187-8d4f82d6c921}",
    ],
)
def test_invocation_id_requires_lowercase_canonical_uuid(invocation_id):
    agent_id, private_key = new_agent()
    payload = sign_commitment(
        private_key,
        agent_id=agent_id,
        invocation_id=invocation_id,
    )

    with pytest.raises(ValidationError, match="invocation_id"):
        make_commitment_model(**payload)


def test_signature_from_a_different_key_is_rejected():
    agent_id, _real_key = new_agent()
    _other_id, impostor_key = new_agent()
    # Sign with the impostor's key but claim to be `agent_id`.
    payload = sign_commitment(impostor_key, agent_id=agent_id, intent_type="payment", nonce=1)
    commitment = make_commitment_model(**payload)
    with pytest.raises(SignatureVerificationError):
        verify_commitment_signature(commitment)


def test_malformed_agent_id_fingerprint_is_rejected():
    agent_id, private_key = new_agent()
    payload = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=1)
    payload["agent_id"] = "did:integrity:deadbeef"  # too short to be a real pubkey
    commitment = make_commitment_model(**payload)
    with pytest.raises(SignatureVerificationError):
        verify_commitment_signature(commitment)
