"""
Tests for the TokenBudgetEnforcer.

Covers:
- Tier budget constants
- Under-limit allowed
- Over-limit denied with correct reason
- Tier 3 unlimited bypass
- Daily reset on day rollover
- Full HTTP integration: token_count on BCC commitment triggers budget check
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

import app.main as main_module
from app.config import Settings
from app.merkle import MerkleBatcher
from app.token_budget import TIER_BUDGETS, TokenBudgetEnforcer

from helpers import new_agent, sign_commitment


@pytest.fixture()
def client():
    return TestClient(main_module.app)


# ---------------------------------------------------------------------------
# Unit tests for TokenBudgetEnforcer
# ---------------------------------------------------------------------------

class TestTokenBudgetEnforcer:
    def setup_method(self):
        self.enforcer = TokenBudgetEnforcer()

    def test_tier_0_budget_allows_under_limit(self):
        ok, reason = self.enforcer.check_and_record("did:integrity:agent_a", tier=0, token_count=9_999)
        assert ok is True
        assert reason is None

    def test_tier_0_budget_denies_over_limit(self):
        # Spend up to the edge
        ok, _ = self.enforcer.check_and_record("did:integrity:agent_b", tier=0, token_count=9_999)
        assert ok is True
        # One more token puts it over
        ok, reason = self.enforcer.check_and_record("did:integrity:agent_b", tier=0, token_count=2)
        assert ok is False
        assert "tier 0" in reason
        assert "10,000" in reason

    def test_tier_3_unlimited_always_allows(self):
        # Tier 3 is -1 (unlimited); even enormous counts pass
        for _ in range(5):
            ok, reason = self.enforcer.check_and_record("did:integrity:sovereign", tier=3, token_count=1_000_000)
            assert ok is True
            assert reason is None

    def test_tier_1_budget_100k(self):
        ok, _ = self.enforcer.check_and_record("did:integrity:agent_c", tier=1, token_count=99_999)
        assert ok is True
        ok, reason = self.enforcer.check_and_record("did:integrity:agent_c", tier=1, token_count=2)
        assert ok is False
        assert "100,000" in reason

    def test_zero_token_count_always_allowed(self):
        ok, reason = self.enforcer.check_and_record("did:integrity:agent_d", tier=0, token_count=0)
        assert ok is True
        assert reason is None

    def test_get_daily_spend_starts_at_zero(self):
        assert self.enforcer.get_daily_spend("did:integrity:unknown") == 0

    def test_get_daily_spend_accumulates(self):
        self.enforcer.check_and_record("did:integrity:agent_e", tier=1, token_count=500)
        self.enforcer.check_and_record("did:integrity:agent_e", tier=1, token_count=300)
        assert self.enforcer.get_daily_spend("did:integrity:agent_e") == 800

    def test_daily_reset_on_new_day(self, monkeypatch):
        import app.token_budget as tb_module

        # Simulate "today"
        monkeypatch.setattr(tb_module, "_utc_day", lambda: "2024-01-01")
        self.enforcer.check_and_record("did:integrity:agent_f", tier=0, token_count=9_990)
        assert self.enforcer.get_daily_spend("did:integrity:agent_f") == 9_990

        # Simulate day rollover
        monkeypatch.setattr(tb_module, "_utc_day", lambda: "2024-01-02")
        assert self.enforcer.get_daily_spend("did:integrity:agent_f") == 0
        ok, _ = self.enforcer.check_and_record("did:integrity:agent_f", tier=0, token_count=9_999)
        assert ok is True

    def test_reset_clears_all_state(self):
        self.enforcer.check_and_record("did:integrity:agent_g", tier=0, token_count=5_000)
        self.enforcer.reset()
        assert self.enforcer.get_daily_spend("did:integrity:agent_g") == 0

    def test_tier_budgets_constants(self):
        assert TIER_BUDGETS[0] == 10_000
        assert TIER_BUDGETS[1] == 100_000
        assert TIER_BUDGETS[2] == 1_000_000
        assert TIER_BUDGETS[3] == -1


# ---------------------------------------------------------------------------
# HTTP integration test: token_count through full intercept pipeline
# ---------------------------------------------------------------------------

def test_intercept_token_budget_denied_when_over_tier0_limit(client, real_opa_server, monkeypatch):
    test_settings = Settings(opa_url=real_opa_server, merkle_batch_size=999)
    monkeypatch.setattr(main_module, "default_settings", test_settings)
    monkeypatch.setattr(main_module, "batcher", MerkleBatcher(batch_size=999))
    main_module.circuit_breaker.reset()
    main_module.nonce_store.reset()
    main_module.token_budget_enforcer.reset()

    agent_id, private_key = new_agent()

    # First call: just under tier 0 limit (no prior spend, tier 0 from oracle)
    # Since oracle is not reachable in test, verification_tier defaults to 0.
    # Budget: 10k tokens. Send 9999 — should pass.
    payload = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=1)
    payload["trace_id"] = "4bf92f3577b34da6a3ce929d0e0e4736"
    payload["span_id"] = "00f067aa0ba902b7"
    payload["agent_thought"] = "Verifiable reasoning process for this payment action."
    payload["token_count"] = 9_999

    resp = client.post("/v1/bcc/intercept", json=payload)
    assert resp.status_code == 200
    assert resp.json()["authorized"] is True

    # Second call: 5 more tokens — pushes over 10k limit
    payload2 = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=2)
    payload2["trace_id"] = "4bf92f3577b34da6a3ce929d0e0e4736"
    payload2["span_id"] = "00f067aa0ba902b7"
    payload2["agent_thought"] = "Verifiable reasoning process for this second payment action."
    payload2["token_count"] = 5

    resp2 = client.post("/v1/bcc/intercept", json=payload2)
    assert resp2.status_code == 200
    assert resp2.json()["authorized"] is False
    # The OPA declarative rule fires first (daily_token_spend is fed into OPA input)
    # — the Python-layer TokenBudgetEnforcer would also have caught it. Either
    # denial reason is a correct budget enforcement outcome.
    reason = resp2.json()["reason"]
    assert "TOKEN_BUDGET" in reason, f"Expected a TOKEN_BUDGET denial, got: {reason!r}"
