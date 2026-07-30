"""
Tests for shadow (monitor-only) mode -- the enterprise-adoption on-ramp where
the gate runs the full authorization gauntlet and records every would-be
decision, but never actually blocks (see app/config.py Settings.shadow_mode and
app/main.py's shadow-aware _deny / _record_violation).

The property under test: in shadow mode, a commitment that enforcement would
DENY instead returns authorized=True / enforced=False / shadow_would_deny=True
with the would-be reason preserved, the audit trail still records it (as
decision="shadow_deny"), and the circuit breaker is NOT tripped. A commitment
that would be ALLOWED behaves normally except enforced=False.
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


def _fresh_state(monkeypatch, settings: Settings) -> None:
    """Point the app at `settings` and give it clean process-local state so the
    shared batcher/breaker/nonce singletons don't leak across tests."""
    monkeypatch.setattr(main_module, "default_settings", settings)
    monkeypatch.setattr(main_module, "batcher", MerkleBatcher(batch_size=999))
    main_module.circuit_breaker.reset()
    main_module.nonce_store.reset()
    # Audit reporting is best-effort fire-and-forget over HTTP; with no oracle
    # in this fixture it just logs a warning and never affects the decision, so
    # we don't need to stub it to assert on the response body.


def test_shadow_mode_does_not_block_a_would_be_denial(client, real_opa_server, monkeypatch):
    """A replayed nonce is a hard deny under enforcement; under shadow mode the
    same replay must return authorized=True with the would-be reason surfaced."""
    settings = Settings(opa_url=real_opa_server, merkle_batch_size=999, shadow_mode=True)
    _fresh_state(monkeypatch, settings)

    agent_id, private_key = new_agent()
    payload = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=5)

    first = client.post("/v1/bcc/intercept", json=payload).json()
    assert first["authorized"] is True
    assert first["enforced"] is False          # shadow: not gated
    assert first["shadow_would_deny"] is False  # first pass would have been allowed

    replay = client.post("/v1/bcc/intercept", json=payload).json()
    # Would be denied under enforcement -- but shadow mode does not block.
    assert replay["authorized"] is True
    assert replay["enforced"] is False
    assert replay["shadow_would_deny"] is True
    assert "BCC_NONCE_REPLAY" in replay["reason"]


def test_shadow_mode_does_not_trip_the_circuit_breaker(client, real_opa_server, monkeypatch):
    """An invalid signature is an agent-attributable violation that would trip
    the breaker under enforcement. In shadow mode we observe but never lock out,
    so repeated bad signatures must leave the breaker closed."""
    settings = Settings(
        opa_url=real_opa_server,
        merkle_batch_size=999,
        shadow_mode=True,
        circuit_breaker_violation_threshold=1,  # would lock after a single violation
    )
    _fresh_state(monkeypatch, settings)

    agent_id, private_key = new_agent()
    payload = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=1)
    payload["signature"] = "0x" + "00" * 64  # syntactically valid, cryptographically wrong

    for _ in range(3):
        body = client.post("/v1/bcc/intercept", json=payload).json()
        assert body["authorized"] is True
        assert body["shadow_would_deny"] is True
        assert "BCC_INVALID_SIGNATURE" in body["reason"]

    # Despite three violations over a threshold of 1, the agent is never locked.
    assert main_module.circuit_breaker.is_locked_out(agent_id) is False


def test_shadow_mode_reports_would_be_denials_as_shadow_deny(client, real_opa_server, monkeypatch):
    """The audit trail must still capture what would have been blocked -- that
    report ("here is what enforcement would have caught") is the whole value of
    a monitor-only rollout. We assert the decision label handed to the audit
    reporter is 'shadow_deny', not 'deny'."""
    settings = Settings(opa_url=real_opa_server, merkle_batch_size=999, shadow_mode=True)
    _fresh_state(monkeypatch, settings)

    reported: list[dict] = []
    monkeypatch.setattr(
        main_module.audit_module,
        "report_decision",
        lambda settings, **kwargs: reported.append(kwargs),
    )

    agent_id, private_key = new_agent()
    payload = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=1)
    payload["signature"] = "0x" + "00" * 64

    client.post("/v1/bcc/intercept", json=payload)

    assert reported, "a would-be denial must still be reported to the audit trail"
    decision = reported[-1]
    assert decision["decision"] == "shadow_deny"
    assert decision["reason_code"] == "BCC_INVALID_SIGNATURE"


def test_enforce_mode_still_blocks_by_default(client, real_opa_server, monkeypatch):
    """Regression guard: with shadow_mode unset (the default), a replayed nonce
    is denied exactly as before -- shadow mode must be strictly opt-in."""
    settings = Settings(opa_url=real_opa_server, merkle_batch_size=999)  # shadow_mode defaults False
    _fresh_state(monkeypatch, settings)
    assert settings.shadow_mode is False

    agent_id, private_key = new_agent()
    payload = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=9)

    assert client.post("/v1/bcc/intercept", json=payload).json()["authorized"] is True
    replay = client.post("/v1/bcc/intercept", json=payload).json()
    assert replay["authorized"] is False
    assert replay["enforced"] is True
    assert "BCC_NONCE_REPLAY" in replay["reason"]


def test_health_reports_mode(client, monkeypatch):
    monkeypatch.setattr(main_module, "default_settings", Settings(shadow_mode=True))
    assert client.get("/health").json()["mode"] == "shadow"

    monkeypatch.setattr(main_module, "default_settings", Settings(shadow_mode=False))
    assert client.get("/health").json()["mode"] == "enforce"
