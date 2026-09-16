import json
from pathlib import Path

from integrity_sdk import integrity
from integrity_sdk.telemetry.envelope import TelemetryEnvelope
from integrity_sdk.telemetry.local_store import LocalEventStore
from integrity_sdk.telemetry.delivery import deliver_with_retry


def test_shipped_schema_matches_envelope_required_fields():
    schema = json.loads((Path(__file__).parents[2] / "integrity_sdk" / "schema" / "telemetry-envelope-v1.json").read_text())
    event = TelemetryEnvelope(event_type="session_started", agent_id="a").to_dict()
    assert schema["properties"]["schema_version"]["const"] == event["schema_version"]
    assert set(schema["required"]).issubset(event)


def test_envelope_is_versioned_hashed_and_redacts_nested_secrets():
    event = TelemetryEnvelope(
        event_type="prompt_received", agent_id="agent-a", did="did:integrity:test",
        payload={"prompt": "email a@b.example", "api_key": "sk-super-secret"},
    ).to_dict()
    assert event["schema_version"] == 1
    assert event["content_hash"]
    assert "a@b.example" not in json.dumps(event)
    assert "sk-super-secret" not in json.dumps(event)
    assert event["payload"]["api_key"] == "<redacted:secret-key>"


def test_local_sqlite_store_is_idempotent(tmp_path):
    store = LocalEventStore(tmp_path / "events.sqlite3", jsonl=False)
    event = TelemetryEnvelope(event_type="session_started", agent_id="a").to_dict()
    store.append(event)
    store.append(event)
    assert store._db.execute("select count(*) from events").fetchone()[0] == 1
    store.close()


def test_delivery_retries_are_bounded_and_dead_lettered():
    event = TelemetryEnvelope(event_type="session_started", agent_id="a").to_dict()
    attempts = []

    def fail(_event, key):
        attempts.append(key)
        raise RuntimeError("offline")

    receipts = deliver_with_retry(event, destination="cortex", send=fail, max_attempts=3)
    assert attempts == [event["event_id"]] * 3
    assert receipts[-1].status == "dead-lettered"
    assert receipts[-1].dead_lettered is True


def test_sqlite_delivery_receipt_is_idempotent(tmp_path):
    store = LocalEventStore(tmp_path / "events.sqlite3", jsonl=False)
    receipt = {"event_id": "e1", "destination": "cortex", "attempt": 1,
               "timestamp": "2026-09-15T00:00:00Z", "status": "acknowledged",
               "retry_state": "complete"}
    store.record_delivery(receipt)
    store.record_delivery(receipt)
    assert store._db.execute("select count(*) from delivery_attempts").fetchone()[0] == 1
    store.close()


def test_integrity_auto_loads_persistent_identity_and_writes_redacted_event(tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "did"))
    monkeypatch.setenv("INTEGRITY_LOCAL_EVENTS", str(tmp_path / "events.jsonl"))
    first = integrity.auto(agent_id="test-agent", harness="generic-python", telemetry="auto", client_kwargs={"auto_flush": False, "enable_otel_export": False})
    did = first.did
    first.start_session("session-1")
    event = first.emit("prompt_received", payload={"prompt": "call a@b.example"})
    first.close()
    second = integrity.auto(agent_id="test-agent", harness="generic-python", telemetry="disabled", client_kwargs={"auto_flush": False, "enable_otel_export": False})
    assert second.did == did
    assert event["agent_id"] == "test-agent"
    assert event["session_id"] == "session-1"
    assert "a@b.example" not in (tmp_path / "events.jsonl").read_text()
    second.close()


def test_facade_records_pair_bound_shield_denial(tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "did"))
    monkeypatch.setenv("INTEGRITY_LOCAL_EVENTS", str(tmp_path / "events.jsonl"))
    agent = integrity.auto(agent_id="shielded-agent", harness="hermes", device_id="device-1", telemetry="auto", client_kwargs={"auto_flush": False, "enable_otel_export": False})
    event = agent.record_shield_decision(invocation_id="inv-1", action="write_file", decision="deny", reason="policy")
    assert event["event_type"] == "shield_action_denied"
    assert event["payload"]["device_id"] == "device-1"
    assert event["payload"]["invocation_id"] == "inv-1"
    agent.close()


def test_one_line_facade_captures_common_lifecycle_events(tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "did"))
    event_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("INTEGRITY_LOCAL_EVENTS", str(event_path))
    agent = integrity.auto(agent_id="quickstart-agent", telemetry="jsonl",
                           client_kwargs={"auto_flush": False, "enable_otel_export": False})
    with agent.session("session-1"):
        agent.prompt("hello", metadata={"channel": "cli"})
        agent.model_request(provider="test-provider", model="test-model")
        agent.response("world")
        agent.token_usage({"input_tokens": 3, "output_tokens": 2})
        agent.tool_call("lookup", arguments={"q": "safe"})
        agent.tool_result("lookup", result={"ok": True})
    agent.close()

    events = [json.loads(line) for line in event_path.read_text().splitlines()]
    types = [event["event_type"] for event in events]
    assert types.count("session_started") == 1
    assert types.count("session_ended") == 1
    assert {"prompt_received", "model_request_started", "model_response_received",
            "token_usage_recorded", "tool_call_started", "tool_result_received"}.issubset(types)
    assert all(event["agent_id"] == "quickstart-agent" for event in events)


def test_facade_rejects_ambiguous_modes(tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "did"))
    monkeypatch.setenv("INTEGRITY_LOCAL_EVENTS", str(tmp_path / "events.jsonl"))
    for kwargs, message in [
        ({"memory": "sometimes"}, "memory"),
        ({"telemetry": "sometimes"}, "telemetry"),
        ({"identity": "ephemeral"}, "identity"),
    ]:
        try:
            integrity.init(agent_id="invalid-mode", client_kwargs={"auto_flush": False}, **kwargs)
        except ValueError as exc:
            assert message in str(exc)
        else:
            raise AssertionError("invalid SDK mode was accepted")


def test_sqlite_mode_is_selected_by_explicit_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "did"))
    db_path = tmp_path / "events.sqlite3"
    monkeypatch.setenv("INTEGRITY_LOCAL_EVENTS", str(db_path))
    agent = integrity.init(agent_id="sqlite-agent", telemetry="sqlite",
                           client_kwargs={"auto_flush": False, "enable_otel_export": False})
    agent.emit("agent_initialized")
    assert agent.store is not None
    assert agent.store._db.execute("select count(*) from events").fetchone()[0] == 1
    agent.close()
