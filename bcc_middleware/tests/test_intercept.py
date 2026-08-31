"""
HTTP-layer tests for POST /v1/bcc/intercept and GET /health, via FastAPI's
TestClient. Business-logic-level tests (fail-closed OPA, circuit breaker,
signature verification) live in their own focused test modules; this file
covers request/response wiring and one full real-OPA success path.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.config import Settings
from app.merkle import MerkleBatcher
from tests.helpers import new_agent, sign_commitment


@pytest.fixture()
def client():
    return TestClient(main_module.app)


def test_malformed_payload_is_rejected_with_422(client):
    resp = client.post("/v1/bcc/intercept", json={"agent_id": "not-even-a-did"})
    assert resp.status_code == 422


def test_bad_hash_shape_is_rejected_with_422(client):
    agent_id, private_key = new_agent()
    payload = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=1)
    payload["intended_state_hash"] = "not-a-hex-hash"
    resp = client.post("/v1/bcc/intercept", json=payload)
    assert resp.status_code == 422


def test_full_success_path_against_real_opa(client, real_opa_server, monkeypatch):
    """
    End-to-end through the actual HTTP endpoint: real signature, real
    running OPA (evaluating our actual policies/bcc.rego), no BAA gate
    (ordinary payment intent), and admission into the merkle batch.
    """
    test_settings = Settings(opa_url=real_opa_server, merkle_batch_size=999)
    monkeypatch.setattr(main_module, "default_settings", test_settings)
    # `batcher` is a process-wide singleton (batch size is an operational,
    # not per-request, parameter -- see app/main.py), so tests that care
    # about its exact state need a fresh instance rather than relying on
    # whatever other tests left pending.
    monkeypatch.setattr(main_module, "batcher", MerkleBatcher(batch_size=999))
    main_module.circuit_breaker.reset()
    main_module.nonce_store.reset()

    agent_id, private_key = new_agent()
    payload = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=1)

    resp = client.post("/v1/bcc/intercept", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["authorized"] is True
    assert body["verification_token"]
    assert body["batch_index"] == 0


def test_replayed_nonce_is_rejected_over_http(client, real_opa_server, monkeypatch):
    test_settings = Settings(opa_url=real_opa_server, merkle_batch_size=999)
    monkeypatch.setattr(main_module, "default_settings", test_settings)
    monkeypatch.setattr(main_module, "batcher", MerkleBatcher(batch_size=999))
    main_module.circuit_breaker.reset()
    main_module.nonce_store.reset()

    agent_id, private_key = new_agent()
    payload = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=7)

    first = client.post("/v1/bcc/intercept", json=payload)
    assert first.json()["authorized"] is True

    replay = client.post("/v1/bcc/intercept", json=payload)
    assert replay.json()["authorized"] is False
    assert "BCC_NONCE_REPLAY" in replay.json()["reason"]


def test_health_endpoint_reports_opa_and_chain_status(client, monkeypatch):
    dead_settings = Settings(opa_url="http://127.0.0.1:1", rpc_url="http://127.0.0.1:2")
    monkeypatch.setattr(main_module, "default_settings", dead_settings)

    resp = client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "online"
    assert body["opa_reachable"] is False
    assert body["chain_reachable"] is False


def test_intercept_aos_gating(client, real_opa_server, monkeypatch):
    test_settings = Settings(opa_url=real_opa_server, merkle_batch_size=999)
    monkeypatch.setattr(main_module, "default_settings", test_settings)
    monkeypatch.setattr(main_module, "batcher", MerkleBatcher(batch_size=999))
    main_module.circuit_breaker.reset()
    main_module.nonce_store.reset()

    agent_id, private_key = new_agent()

    # 1. Deny when trace_id/span_id/intent_rationale are missing on agent tool call
    payload_missing = sign_commitment(private_key, agent_id=agent_id, intent_type="claude_tool:Bash", nonce=1)
    resp_missing = client.post("/v1/bcc/intercept", json=payload_missing)
    assert resp_missing.status_code == 200
    assert resp_missing.json()["authorized"] is False
    assert "AOS_VIOLATION" in resp_missing.json()["reason"]

    # 2. Allow when trace_id/span_id/intent_rationale are present
    payload_valid = sign_commitment(
        private_key,
        agent_id=agent_id,
        intent_type="claude_tool:Bash",
        nonce=2,
        intent_rationale="Verifiable public intent rationale explaining the action.",
    )
    payload_valid["trace_id"] = "4bf92f3577b34da6a3ce929d0e0e4736"
    payload_valid["span_id"] = "00f067aa0ba902b7"
    payload_valid["agent_thought"] = payload_valid["intent_rationale"]
    resp_valid = client.post("/v1/bcc/intercept", json=payload_valid)
    assert resp_valid.status_code == 200
    assert resp_valid.json()["authorized"] is True
