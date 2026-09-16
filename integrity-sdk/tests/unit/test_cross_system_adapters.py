from integrity_sdk.integrations.cortex import CortexTransport
from integrity_sdk.integrations.shield import action_context, decision_event
from integrity_sdk.telemetry.transports import HttpTelemetryTransport, MCPTelemetryTransport, OTLPHttpTransport


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


def test_cortex_transport_retries_transient_failure_with_same_batch(monkeypatch):
    calls = []

    class Response:
        status_code = 503
        def raise_for_status(self):
            import requests
            if self.status_code >= 400:
                raise requests.HTTPError(response=self)
        def json(self):
            return {"recorded": 1}

    def post(*args, **kwargs):
        calls.append(kwargs["json"])
        if len(calls) < 3:
            return Response()
        Response.status_code = 200
        return Response()

    monkeypatch.setattr("integrity_sdk.integrations.cortex.requests.post", post)
    monkeypatch.setattr("integrity_sdk.integrations.cortex.time.sleep", lambda _: None)
    result = CortexTransport("http://cortex", "bearer-secret").export(
        [{"event_id": "e1", "agent_id": "agent-a", "session_id": "s1"}],
        max_attempts=3,
    )
    assert result["recorded"] == 1
    assert len(calls) == 3
    assert calls[0] == calls[-1]


def test_http_transport_is_authenticated_and_idempotent(monkeypatch):
    calls = []
    class Response:
        status_code = 200
        content = b'{}'
        def raise_for_status(self): pass
        def json(self): return {"accepted": True}
    monkeypatch.setattr("integrity_sdk.telemetry.transports.requests.post", lambda *a, **k: calls.append((a, k)) or Response())
    result = HttpTelemetryTransport("http://collector", bearer_token="bearer").export(
        [{"event_id": "e1", "event_type": "session_started"}])
    assert result["accepted"] is True
    assert calls[0][1]["headers"]["Authorization"] == "Bearer bearer"
    assert calls[0][1]["headers"]["Idempotency-Key"] == "e1"


def test_otlp_transport_emits_otlp_json_log_shape(monkeypatch):
    calls = []
    class Response:
        status_code = 200
        content = b'{}'
        def raise_for_status(self): pass
        def json(self): return {"accepted": True}
    monkeypatch.setattr("integrity_sdk.telemetry.transports.requests.post", lambda *a, **k: calls.append((a, k)) or Response())
    OTLPHttpTransport("http://collector").export([{"event_id": "e1", "event_type": "session_started", "timestamp": "2026-09-15T00:00:00Z"}])
    assert calls[0][0][0].endswith("/v1/logs")
    assert "resourceLogs" in calls[0][1]["json"]
    assert calls[0][1]["headers"]["Content-Type"] == "application/json"


def test_mcp_transport_preserves_event_ids():
    calls = []
    transport = MCPTelemetryTransport(lambda name, args: calls.append((name, args)) or {"recorded": 1})
    assert transport.export([{"event_id": "e1", "event_type": "session_started"}])["recorded"] == 1
    assert calls[0][1]["idempotency_keys"] == ["e1"]
