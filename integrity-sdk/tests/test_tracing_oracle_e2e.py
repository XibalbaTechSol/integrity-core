"""
Real end-to-end test of the SDK's public tracing API
(`IntegrityClient.traceable`) against a REAL, already-running
`integrity-oracle` instance — closes a real, confirmed gap found by tracing
a real agent run: `client.traceable(...)` opens a real OTel span on every
call, but nothing ever installed a real TracerProvider/OTLP exporter before
the 2026-07-16 fix (`client.py`'s `__init__` now calls
`telemetry.core.init_telemetry` automatically), so every span this SDK's
own "recommended tracing API" ever produced was silently discarded before
it reached the oracle. See PRODUCTION_GAPS.md's writeup for the full story.

Unlike `test_registration_oracle_e2e.py`, this does NOT spin up its own
ephemeral oracle/Postgres/Redis via Docker + `cargo run` — it connects to
whatever oracle is already reachable at `ORACLE_URL`/the OTLP endpoint
derived from it (matching a developer's normal `docker-compose up` /
`make up` workflow), and skips loudly (not silently) if nothing is
listening, rather than requiring every contributor to have Docker +
`cargo` on `PATH` just to exercise this one path. Still opt-in via
`ORACLE_E2E=1`, same gate every other real-infra SDK test uses, since it
still needs a real oracle process, not a mock.
"""

from __future__ import annotations

import json
import os
import time
import uuid

import pytest
import requests

pytestmark = pytest.mark.skipif(
    os.getenv("ORACLE_E2E") != "1",
    reason="set ORACLE_E2E=1 (with a real oracle already reachable) to run",
)

ORACLE_URL = os.getenv("ORACLE_URL", "http://localhost:8080")


def _oracle_reachable() -> bool:
    try:
        requests.get(f"{ORACLE_URL}/v1/agents", timeout=2).raise_for_status()
        return True
    except requests.RequestException:
        return False


@pytest.fixture(autouse=True)
def _skip_if_oracle_unreachable():
    if not _oracle_reachable():
        pytest.skip(f"no real oracle reachable at {ORACLE_URL} — start one (e.g. `make up`) to run this test")


def _discover_trace_id_via_sse(agent_id: str, timeout_sec: float = 10.0) -> str:
    """Reads the real SSE stream (GET /v1/stream) until an OtelSpan event for
    `agent_id` arrives, exactly the mechanism ChainOfThoughtPage/
    CompareTracesPage use to discover trace_ids in the frontend (there is no
    list-spans-by-agent HTTP endpoint) -- so this test proves the same real
    discovery path a human using the dashboard relies on, not a shortcut."""
    deadline = time.time() + timeout_sec
    with requests.get(f"{ORACLE_URL}/v1/stream", stream=True, timeout=timeout_sec + 2) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines(decode_unicode=True):
            if time.time() > deadline:
                break
            if not line or not line.startswith("data:"):
                continue
            try:
                event = json.loads(line[len("data:") :].strip())
            except json.JSONDecodeError:
                continue
            if event.get("type") == "OtelSpan" and event.get("agent_id") == agent_id:
                return event["trace_id"]
    pytest.fail(f"no OtelSpan SSE event for {agent_id} observed within {timeout_sec}s")


def test_traceable_produces_a_real_nested_tree_the_oracle_can_reconstruct():
    from opentelemetry import trace

    from integrity_sdk.client import IntegrityClient

    agent_id = f"trace-e2e-{uuid.uuid4().hex[:8]}"
    client = IntegrityClient(agent_id=agent_id, oracle_url=ORACLE_URL)

    @client.traceable(name="agent_run", run_type="chain")
    def agent_run(question: str) -> str:
        return llm_call(question)

    @client.traceable(name="llm_call", run_type="llm")
    def llm_call(question: str) -> str:
        return tool_call(question)

    @client.traceable(name="tool_call", run_type="tool")
    def tool_call(question: str) -> str:
        return f"answer: {question}"

    # Start listening on the real SSE stream BEFORE tracing, in a background
    # thread, so the export below can't race ahead of the listener the way
    # it would if we started listening only after force_flush() returned.
    import threading

    discovered = {}

    def _listen():
        discovered["trace_id"] = _discover_trace_id_via_sse(agent_id, timeout_sec=15.0)

    listener = threading.Thread(target=_listen, daemon=True)
    listener.start()
    time.sleep(0.5)  # let the SSE GET actually connect before we export

    result = agent_run("what is the real trace tree pipeline")
    assert result == "answer: what is the real trace tree pipeline"

    # Force immediate export rather than waiting for BatchSpanProcessor's
    # default 5s batch timer — this test should be fast and deterministic.
    assert trace.get_tracer_provider().force_flush(timeout_millis=5000)

    listener.join(timeout=16.0)
    trace_id = discovered.get("trace_id")
    assert trace_id, "SSE listener thread never discovered a trace_id"

    tree_resp = requests.get(f"{ORACLE_URL}/v1/traces/{trace_id}", timeout=5)
    tree_resp.raise_for_status()
    tree = tree_resp.json()

    assert tree["span_count"] == 3
    assert tree["truncated"] is False
    assert len(tree["roots"]) == 1
    root = tree["roots"][0]
    assert root["agent_id"] == agent_id
    assert root["name"] == "agent_run"
    assert len(root["children"]) == 1
    assert root["children"][0]["name"] == "llm_call"
    assert len(root["children"][0]["children"]) == 1
    assert root["children"][0]["children"][0]["name"] == "tool_call"
