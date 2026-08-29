from __future__ import annotations

from typing import Any, Dict

import pytest

from integrity_sdk import bcc
from integrity_sdk.client import IntegrityClient, TELEMETRY_SCHEMA_VERSION
from integrity_sdk.did import Keypair, verify_signature


class _FakeResponse:
    def __init__(self, status_ok: bool = True, status_code: int = None, payload: Dict[str, Any] = None):
        self._ok = status_ok
        self.status_code = status_code if status_code is not None else (200 if status_ok else 500)
        self._payload = payload or {}

    def raise_for_status(self):
        if not self._ok:
            import requests

            err = requests.HTTPError("simulated oracle error")
            err.response = self
            raise err

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _no_real_nonce_sync_network_calls(monkeypatch):
    """
    client.py's flush_telemetry now calls `_sync_nonce_from_oracle` (a real
    GET) before the first flush of every client instance (PRODUCTION_GAPS.md
    §3 fix). None of the tests below construct a client with `_nonce_synced`
    pre-set, and none of them care about the sync's outcome -- without this,
    every test in this file would attempt a real network call to
    localhost:8080 and eat that GET's timeout. Simulating "oracle
    unreachable" here reproduces exactly what `_sync_nonce_from_oracle`
    already does on failure (mark synced, leave `_nonce` unchanged) --
    so every existing nonce-value assertion below (1, 2, rolled back to 0,
    etc.) stays correct against this file's local-nonce-only baseline.
    Tests that specifically care about the sync behavior override this with
    their own `requests.get` patch (see the nonce-sync tests below).
    """
    import requests

    monkeypatch.setattr(
        "integrity_sdk.client.requests.get",
        lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("no oracle in this test")),
    )


@pytest.fixture
def captured_posts(monkeypatch):
    posts = []

    def _fake_post(url, json=None, timeout=None):
        posts.append({"url": url, "json": json})
        return _FakeResponse(status_ok=True)

    monkeypatch.setattr("integrity_sdk.client.requests.post", _fake_post)
    return posts


def test_log_telemetry_buffers_without_flushing(captured_posts):
    client = IntegrityClient("agent-a", auto_flush=False)
    client.log_telemetry({"text_output": "hello"})
    assert captured_posts == []  # no flush yet


def test_flush_derives_signals_and_posts(captured_posts):
    client = IntegrityClient("agent-a", oracle_url="http://oracle.test", auto_flush=False)
    client.log_telemetry({"text_output": "yes yes yes", "token_usage": {"total_tokens": 1000}})
    assert client.flush_telemetry() is True

    assert len(captured_posts) == 1
    payload = captured_posts[0]["json"]
    assert captured_posts[0]["url"] == "http://oracle.test/v1/telemetry/ingest"
    assert payload["agent_id"] == "agent-a"
    assert payload["nonce"] == 1
    assert set(payload["derived_signals"].keys()) == {"entropy", "grounding", "sacrifice", "compliance"}


def test_nonce_increments_across_flushes(captured_posts):
    client = IntegrityClient("agent-a", auto_flush=False)
    client.log_telemetry({"text_output": "a"})
    client.flush_telemetry()
    client.log_telemetry({"text_output": "b"})
    client.flush_telemetry()
    assert captured_posts[0]["json"]["nonce"] == 1
    assert captured_posts[1]["json"]["nonce"] == 2


def test_flush_with_nothing_buffered_is_noop_success(captured_posts):
    client = IntegrityClient("agent-a", auto_flush=False)
    assert client.flush_telemetry() is True
    assert captured_posts == []


def test_failed_flush_requeues_and_rolls_back_nonce(monkeypatch):
    import requests

    def _failing_post(url, json=None, timeout=None):
        raise requests.ConnectionError("oracle down")

    monkeypatch.setattr("integrity_sdk.client.requests.post", _failing_post)

    client = IntegrityClient("agent-a", auto_flush=False)
    client.log_telemetry({"text_output": "important"})
    assert client.flush_telemetry() is False
    # Nonce rolled back to 0 so the retry reuses nonce 1, not 2.
    assert client._nonce == 0
    # Entry re-queued: a subsequent successful flush should still carry it.
    posts = []
    monkeypatch.setattr(
        "integrity_sdk.client.requests.post",
        lambda url, json=None, timeout=None: posts.append(json) or _FakeResponse(True),
    )
    assert client.flush_telemetry() is True
    assert posts[0]["nonce"] == 1
    assert len([s for s in posts[0]["otel_spans"] if s["kind"] == "telemetry"]) == 1


def test_record_trace_run_rides_along_on_flush(captured_posts):
    client = IntegrityClient("agent-a", auto_flush=False)
    client._record_trace_run({"run_id": "r1", "name": "step"})
    client.flush_telemetry()
    trace_runs = [s for s in captured_posts[0]["json"]["otel_spans"] if s["kind"] == "trace_run"]
    assert trace_runs[0]["run_id"] == "r1"


def test_traceable_wraps_and_records(captured_posts):
    client = IntegrityClient("agent-a", auto_flush=False)

    @client.traceable(name="my_step", run_type="tool")
    def do_work(x: int) -> int:
        return x * 2

    assert do_work(21) == 42
    client.flush_telemetry()
    runs = [s for s in captured_posts[0]["json"]["otel_spans"] if s["kind"] == "trace_run"]
    assert any(r["name"] == "my_step" for r in runs)


def test_flush_without_keypair_sends_empty_signature_string(captured_posts):
    # Confirms the payload at least deserializes against the oracle's real
    # `signature: String` (non-nullable) field -- see flush_telemetry's
    # docstring on why `None` used to break this. An empty string still
    # fails the oracle's own signature check (real, honest 401), which is
    # correct: a client with no keypair genuinely cannot produce a valid one.
    client = IntegrityClient("agent-a", auto_flush=False)
    client.log_telemetry({"text_output": "hi"})
    client.flush_telemetry()
    assert captured_posts[0]["json"]["signature"] == ""


def test_flush_with_keypair_produces_a_real_verifiable_signature(captured_posts):
    keypair = Keypair.generate()
    client = IntegrityClient("agent-a", auto_flush=False, keypair=keypair)
    client.log_telemetry({"text_output": "hi"})
    client.flush_telemetry()

    payload = captured_posts[0]["json"]
    sig_hex = payload["signature"]
    assert sig_hex.startswith("0x")

    # The envelope version must be present AND inside the signature — outside it, it could be
    # rewritten in transit to make the oracle reinterpret the payload (INTERFACE_CONTRACT
    # §4.2a).
    assert payload["schema_version"] == TELEMETRY_SCHEMA_VERSION

    # Independently re-derive exactly what the oracle's own ingest_telemetry
    # handler reconstructs (same field set, same canonical_json_bytes
    # convention) and confirm the signature verifies against it.
    signable = {
        "schema_version": payload["schema_version"],
        "agent_id": payload["agent_id"],
        "nonce": payload["nonce"],
        "otel_spans": payload["otel_spans"],
        "derived_signals": payload["derived_signals"],
        "zk_proof": payload["zk_proof"],
    }
    assert verify_signature(
        keypair.public_bytes(),
        bcc.canonical_json_bytes(signable),
        bytes.fromhex(sig_hex[2:]),
    )

    # And prove the version is actually covered: verifying against the object WITHOUT it must
    # fail. Otherwise this test would still pass if the field were merely appended alongside
    # the signature rather than signed.
    unversioned = {k: v for k, v in signable.items() if k != "schema_version"}
    assert not verify_signature(
        keypair.public_bytes(),
        bcc.canonical_json_bytes(unversioned),
        bytes.fromhex(sig_hex[2:]),
    ), "schema_version must be part of the signed bytes, not merely present in the payload"


def test_flush_drains_custom_metrics_into_otel_spans(captured_posts):
    client = IntegrityClient("agent-a", auto_flush=False)
    client.log_telemetry({"text_output": "hi"})
    client.record_metric("integrity.intent.plan_adherence", 1.0, tags={"intent_id": "abc"})
    client.flush_telemetry()

    metrics_entries = [s for s in captured_posts[0]["json"]["otel_spans"] if s["kind"] == "custom_metrics"]
    assert len(metrics_entries) == 1
    assert metrics_entries[0]["metrics"]["integrity.intent.plan_adherence"]["value"] == 1.0


# --- invoke_intent convenience method ----------------------------------------------------


def test_invoke_intent_without_keypair_raises_clear_error():
    client = IntegrityClient("agent-a", auto_flush=False)
    with pytest.raises(RuntimeError, match="keypair"):
        with client.invoke_intent(
            intent_type="EMR_WRITE", intent_payload={},
            chain_id=31337, verifying_contract="0x111111111111111111111111111111111111111a",
        ):
            pass


def test_invoke_intent_without_nonce_store_raises_clear_error(tmp_path):
    client = IntegrityClient("agent-a", auto_flush=False, keypair=Keypair.generate())
    with pytest.raises(RuntimeError, match="bcc_nonce_store"):
        with client.invoke_intent(
            intent_type="EMR_WRITE", intent_payload={},
            chain_id=31337, verifying_contract="0x111111111111111111111111111111111111111a",
        ):
            pass


def test_invoke_intent_convenience_pulls_nonce_from_store_and_rides_along_on_flush(captured_posts, tmp_path):
    keypair = Keypair.generate()
    nonce_store = bcc.NonceStore(tmp_path / "bcc_nonce.txt")
    client = IntegrityClient("agent-a", auto_flush=False, keypair=keypair, bcc_nonce_store=nonce_store)

    with client.invoke_intent(
        intent_type="EMR_WRITE", intent_payload={"a": 1}, planned_action={"tool": "write_emr"},
        chain_id=31337, verifying_contract="0x111111111111111111111111111111111111111a",
    ) as intent:
        intent.record_outcome({"tool": "write_emr"})

    client.flush_telemetry()
    trace_runs = [s for s in captured_posts[0]["json"]["otel_spans"] if s["kind"] == "trace_run"]
    assert trace_runs[0]["run_type"] == "intent"
    assert trace_runs[0]["outputs"]["adherence_score"] == 1.0

    metrics_entries = [s for s in captured_posts[0]["json"]["otel_spans"] if s["kind"] == "custom_metrics"]
    assert metrics_entries[0]["metrics"]["integrity.intent.plan_adherence"]["value"] == 1.0


# --- nonce sync / restart-stall fix (PRODUCTION_GAPS.md §3) -----------------------------


def test_first_flush_syncs_nonce_from_oracle_before_posting(monkeypatch, captured_posts):
    monkeypatch.setattr(
        "integrity_sdk.client.requests.get", lambda *a, **k: _FakeResponse(payload={"last_nonce": 41, "oracle_registered": True})
    )
    client = IntegrityClient("agent-a", auto_flush=False)
    client.log_telemetry({"text_output": "hi"})

    assert client._nonce_synced is False
    assert client.flush_telemetry() is True

    assert client._nonce_synced is True
    # Adopted the oracle's persisted last_nonce (41) as the floor, then
    # incremented once for this flush -- not a naive 0 -> 1.
    assert client._nonce == 42
    assert captured_posts[0]["json"]["nonce"] == 42


def test_subsequent_flush_does_not_resync_nonce(monkeypatch, captured_posts):
    get_calls = []
    monkeypatch.setattr(
        "integrity_sdk.client.requests.get",
        lambda *a, **k: get_calls.append(1) or _FakeResponse(payload={"last_nonce": 5, "oracle_registered": True}),
    )
    client = IntegrityClient("agent-a", auto_flush=False)
    client.log_telemetry({"text_output": "first"})
    client.flush_telemetry()

    client.log_telemetry({"text_output": "second"})
    client.flush_telemetry()

    assert len(get_calls) == 1  # only synced once, not on every flush
    assert client._nonce == 7  # 5 -> 6 (first flush) -> 7 (second flush)


def test_409_response_resyncs_nonce_instead_of_rolling_back(monkeypatch):
    """The core regression this fix targets: a 409 means the oracle already
    consumed this nonce, so decrementing (the old behavior) would repeat the
    same 409 forever after a process restart. The fix re-syncs from the
    oracle's real last_nonce instead."""
    monkeypatch.setattr("integrity_sdk.client.requests.post", lambda *a, **k: _FakeResponse(status_ok=False, status_code=409))
    get_calls = []
    monkeypatch.setattr(
        "integrity_sdk.client.requests.get",
        lambda *a, **k: get_calls.append(1) or _FakeResponse(payload={"last_nonce": 15, "oracle_registered": True}),
    )

    client = IntegrityClient("agent-a", auto_flush=False)
    client._nonce = 10
    client._nonce_synced = True  # already synced once, so this flush won't GET first
    client.log_telemetry({"text_output": "hi"})

    assert client.flush_telemetry() is False
    assert len(get_calls) == 1  # the 409 handler explicitly re-synced
    assert client._nonce == 15  # not rolled back to 10, which would just 409 again
    assert client._nonce_synced is True


def test_non_409_failure_still_rolls_back_nonce_for_retry(monkeypatch):
    """A transient network error (not a 409) means the oracle never saw this
    nonce at all -- rolling back so the retry reuses it is still correct
    here, unlike the 409 case above."""
    monkeypatch.setattr(
        "integrity_sdk.client.requests.post",
        lambda *a, **k: (_ for _ in ()).throw(__import__("requests").ConnectionError("boom")),
    )
    get_calls = []
    monkeypatch.setattr("integrity_sdk.client.requests.get", lambda *a, **k: get_calls.append(1))

    client = IntegrityClient("agent-a", auto_flush=False)
    client._nonce = 10
    client._nonce_synced = True
    client.log_telemetry({"text_output": "hi"})

    assert client.flush_telemetry() is False
    assert get_calls == []  # non-409 failure does not trigger a re-sync
    assert client._nonce == 10  # rolled back from 11


# --- Default-deny: refuse to send telemetry for an oracle-confirmed-unregistered agent ---


def test_flush_refuses_to_send_when_oracle_confirms_agent_unregistered(monkeypatch):
    monkeypatch.setattr(
        "integrity_sdk.client.requests.get", lambda *a, **k: _FakeResponse(status_code=404)
    )
    posts = []
    monkeypatch.setattr(
        "integrity_sdk.client.requests.post",
        lambda url, json=None, timeout=None: posts.append(json) or _FakeResponse(True),
    )

    client = IntegrityClient("unregistered-agent", auto_flush=False)
    client.log_telemetry({"text_output": "should not leave the process"})

    assert client.flush_telemetry() is False
    assert posts == []  # the payload was never POSTed, not merely rejected server-side
    assert client._registered is False


def test_flush_requeues_and_succeeds_once_the_agent_becomes_registered(monkeypatch):
    get_responses = iter([_FakeResponse(status_code=404), _FakeResponse(payload={"last_nonce": 0, "oracle_registered": True})])
    monkeypatch.setattr("integrity_sdk.client.requests.get", lambda *a, **k: next(get_responses))
    posts = []
    monkeypatch.setattr(
        "integrity_sdk.client.requests.post",
        lambda url, json=None, timeout=None: posts.append(json) or _FakeResponse(True),
    )

    client = IntegrityClient("agent-a", auto_flush=False)
    client.log_telemetry({"text_output": "buffered before registration"})
    assert client.flush_telemetry() is False
    assert posts == []

    # A later flush re-checks (nonce sync is one-shot per client, so this simulates a
    # fresh client instance after the agent registers — the realistic restart path).
    client._nonce_synced = False
    assert client.flush_telemetry() is True
    assert len(posts) == 1
    assert len([s for s in posts[0]["otel_spans"] if s["kind"] == "telemetry"]) == 1


def test_flush_proceeds_when_registration_check_is_inconclusive(captured_posts):
    # The autouse fixture simulates an unreachable oracle (ConnectionError), which must
    # leave `_registered` at None (unknown) — telemetry stays best-effort, not gated
    # shut, on a transient failure that says nothing about registration either way.
    client = IntegrityClient("agent-a", auto_flush=False)
    client.log_telemetry({"text_output": "hi"})

    assert client.flush_telemetry() is True
    assert client._registered is None
    assert len(captured_posts) == 1


# --- OTel wiring: client.traceable()/trace_run() must actually export spans ---
#
# FIXED 2026-07-16: `client.traceable(...)` opens a real OTel span
# (get_tracer(...).start_as_current_span(...)) on every call, but nothing
# ever installed a real TracerProvider/exporter before this fix -- so
# get_tracer() silently returned OTel's default no-op tracer, and every
# span this SDK's own "recommended tracing API" ever produced was thrown
# away before it left the process, confirmed by tracing a real agent run
# end-to-end and finding zero rows in the oracle's real otel_spans table.
# `telemetry_core.init_telemetry` is mocked here (not exercised for real)
# because it's a process-global singleton (module-level `_initialized`
# guard) -- calling the real thing would leak state across every other test
# in this file/session and make assertions about call arguments impossible
# to isolate, the same reason `requests.post`/`requests.get` are mocked
# above. The real, unmocked end-to-end path (real OTel export -> real
# oracle OTLP receiver -> real otel_spans rows -> real GET /v1/traces/{id})
# is proven in PRODUCTION_GAPS.md's writeup for this fix, not by this file.


def test_construction_wires_up_real_otel_export_by_default(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "integrity_sdk.client.telemetry_core.init_telemetry",
        lambda agent_id, endpoint: calls.append((agent_id, endpoint)),
    )

    IntegrityClient("agent-a", oracle_url="http://oracle-host:8080", auto_flush=False)

    assert calls == [("agent-a", "oracle-host:4317")]


def test_otlp_endpoint_override_is_respected(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "integrity_sdk.client.telemetry_core.init_telemetry",
        lambda agent_id, endpoint: calls.append((agent_id, endpoint)),
    )

    IntegrityClient(
        "agent-a",
        oracle_url="http://oracle-host:8080",
        otlp_endpoint="collector.example.com:4317",
        auto_flush=False,
    )

    assert calls == [("agent-a", "collector.example.com:4317")]


def test_enable_otel_export_false_skips_wiring(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "integrity_sdk.client.telemetry_core.init_telemetry",
        lambda agent_id, endpoint: calls.append((agent_id, endpoint)),
    )

    IntegrityClient("agent-a", enable_otel_export=False, auto_flush=False)

    assert calls == []
