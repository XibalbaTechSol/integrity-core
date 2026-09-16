from integrity_sdk.integrations.cortex import CortexTransport
from integrity_sdk.integrations.shield import action_context, decision_event


def test_shield_correlation_requires_exact_pair_bound_context():
    ctx = action_context(agent_id="did:a", device_id="device-a", invocation_id="inv-1", action="write_file")
    assert decision_event(ctx, decision="deny", reason="policy") == {
        **ctx, "decision": "deny", "reason": "policy", "enforcement_outcome": "deny"
    }


def test_cortex_transport_maps_envelope_without_authority_guessing(monkeypatch):
    calls = []
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"recorded": 1, "duplicates": 0}
    monkeypatch.setattr("integrity_sdk.integrations.cortex.requests.post", lambda *a, **k: calls.append((a, k)) or Response())
    result = CortexTransport("http://cortex", "bearer-secret").export([{"event_id": "e1", "agent_id": "agent-a", "session_id": "s1"}])
    assert result["recorded"] == 1
    assert calls[0][1]["headers"]["Authorization"] == "Bearer bearer-secret"
    assert calls[0][1]["json"]["events"][0]["idempotency_key"] == "e1"
