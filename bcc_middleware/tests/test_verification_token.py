"""
Tests for app/verification_token.py and POST /v1/bcc/verify_token
(PRODUCTION_GAPS.md §5): the old `verification_token` was
sha256(agent_id|nonce|intended_state_hash|time.time()) -- unsigned,
unpersisted, and trivially recomputable by anyone from the commitment's own
(public) fields, so it proved nothing and nothing ever checked it. The new
token is HMAC-keyed with a process-local secret and persisted so a relying
party can actually ask this service to verify one.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.config import Settings
from app.merkle import MerkleBatcher
from app import verification_token
from tests.helpers import new_agent, sign_commitment


@pytest.fixture()
def client():
    return TestClient(main_module.app)


# --- unit-level: issue_token / verify_token ------------------------------------------


def test_verify_token_accepts_a_genuinely_issued_token():
    settings = Settings()
    token = verification_token.issue_token(settings, "did:integrity:abc", 1, "0x" + "11" * 32)
    assert verification_token.verify_token(settings, token, "did:integrity:abc", 1, "0x" + "11" * 32)


def test_verify_token_rejects_an_unissued_token():
    settings = Settings()
    assert not verification_token.verify_token(settings, "0x" + "00" * 32, "did:integrity:abc", 1, "0x" + "11" * 32)


def test_verify_token_rejects_when_fields_dont_match_what_was_issued():
    """A token issued for one nonce must not verify against a different
    nonce/hash -- proves the check is bound to the specific fields, not just
    "is this token in the known-issued set"."""
    settings = Settings()
    token = verification_token.issue_token(settings, "did:integrity:abc", 1, "0x" + "11" * 32)

    assert not verification_token.verify_token(settings, token, "did:integrity:abc", 2, "0x" + "11" * 32)
    assert not verification_token.verify_token(settings, token, "did:integrity:other", 1, "0x" + "11" * 32)
    assert not verification_token.verify_token(settings, token, "did:integrity:abc", 1, "0x" + "22" * 32)


def test_token_is_not_a_bare_sha256_of_public_fields():
    """The core regression: a caller who knows only the (public) commitment
    fields must NOT be able to recompute a valid token without the secret --
    unlike the old sha256(agent_id|nonce|hash|time()) scheme."""
    import hashlib

    settings = Settings()
    agent_id, nonce, state_hash = "did:integrity:abc", 1, "0x" + "11" * 32
    token = verification_token.issue_token(settings, agent_id, nonce, state_hash)

    guessed = hashlib.sha256(f"{agent_id}|{nonce}|{state_hash}".encode()).hexdigest()
    assert token != guessed


def test_two_different_processes_secrets_disagree():
    """Different Settings() instances (simulating different process starts
    without an explicit BCC_VERIFICATION_SECRET) get different random
    secrets -- a token issued by one must not verify under another,
    confirming the secret is actually load-bearing, not a no-op."""
    settings_a = Settings()
    settings_b = Settings()
    assert settings_a.bcc_verification_secret != settings_b.bcc_verification_secret

    token = verification_token.issue_token(settings_a, "did:integrity:abc", 1, "0x" + "11" * 32)
    # verify_token first does a persisted-record lookup (module-global, so
    # this still finds the record) but the HMAC recomputation uses
    # settings_b's own secret -- must fail.
    assert not verification_token.verify_token(settings_b, token, "did:integrity:abc", 1, "0x" + "11" * 32)


# --- HTTP-level: full intercept -> verify_token round trip ---------------------------


def test_verify_token_endpoint_confirms_a_token_issued_via_real_intercept(client, real_opa_server, monkeypatch):
    test_settings = Settings(opa_url=real_opa_server, merkle_batch_size=999)
    monkeypatch.setattr(main_module, "default_settings", test_settings)
    monkeypatch.setattr(main_module, "batcher", MerkleBatcher(batch_size=999))
    main_module.circuit_breaker.reset()
    main_module.nonce_store.reset()

    agent_id, private_key = new_agent()
    payload = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=1)

    resp = client.post("/v1/bcc/intercept", json=payload)
    assert resp.status_code == 200
    token = resp.json()["verification_token"]

    verify_resp = client.post(
        "/v1/bcc/verify_token",
        json={
            "token": token,
            "agent_id": agent_id,
            "nonce": payload["nonce"],
            "intended_state_hash": payload["intended_state_hash"],
        },
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["valid"] is True


def test_verify_token_endpoint_rejects_a_forged_token(client, real_opa_server, monkeypatch):
    test_settings = Settings(opa_url=real_opa_server, merkle_batch_size=999)
    monkeypatch.setattr(main_module, "default_settings", test_settings)
    monkeypatch.setattr(main_module, "batcher", MerkleBatcher(batch_size=999))
    main_module.circuit_breaker.reset()
    main_module.nonce_store.reset()

    agent_id, private_key = new_agent()
    payload = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=1)

    verify_resp = client.post(
        "/v1/bcc/verify_token",
        json={
            "token": "0x" + "ab" * 32,  # never issued
            "agent_id": agent_id,
            "nonce": payload["nonce"],
            "intended_state_hash": payload["intended_state_hash"],
        },
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["valid"] is False
