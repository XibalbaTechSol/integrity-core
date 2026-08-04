"""
Tests for aos_span.py and llm_token_ledger.py (integrity-sdk).

Covers:
- get_current_aos_context returns empty dict when no span active
- aos_plan_span sets agent.thought on the span
- get_current_aos_context returns trace_id/span_id inside a span
- token ledger record and query
- token ledger JSONL persistence
- CoT coverage rate calculation
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.export import SimpleSpanProcessor


@pytest.fixture()
def in_memory_otel(monkeypatch):
    """
    Configure a local in-memory TracerProvider and patch aos_span._get_tracer
    to return a tracer from it, bypassing the SDK global provider restriction.
    """
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry import trace as otel_trace
    import integrity_sdk.telemetry.aos_span as aos_module

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    def _patched_get_tracer():
        return provider.get_tracer("integrity_sdk.aos_test"), otel_trace

    monkeypatch.setattr(aos_module, "_get_tracer", _patched_get_tracer)
    yield exporter
    exporter.clear()


class TestGetCurrentAosContext:
    def test_returns_empty_outside_span(self):
        from integrity_sdk.telemetry.aos_span import get_current_aos_context
        ctx = get_current_aos_context()
        assert ctx["trace_id"] is None
        assert ctx["span_id"] is None
        # agent_thought may or may not be set by prior test — just check it's a dict key
        assert "agent_thought" in ctx

    def test_returns_trace_id_inside_run_span(self, in_memory_otel):
        from integrity_sdk.telemetry.aos_span import aos_run_span, get_current_aos_context
        with aos_run_span("did:integrity:test", "test_run"):
            ctx = get_current_aos_context()
        assert ctx["trace_id"] is not None
        assert len(ctx["trace_id"]) == 32
        assert ctx["span_id"] is not None
        assert len(ctx["span_id"]) == 16

    def test_returns_agent_thought_inside_plan_span(self, in_memory_otel):
        from integrity_sdk.telemetry.aos_span import aos_run_span, aos_plan_span, get_current_aos_context
        thought = "I will execute a payment to recipient account."
        with aos_run_span("did:integrity:test", "test_run"):
            with aos_plan_span(thought):
                ctx = get_current_aos_context()
                assert ctx["agent_thought"] == thought
                assert ctx["trace_id"] is not None
                assert ctx["span_id"] is not None


class TestAosPlanSpan:
    def test_sets_agent_thought_attribute(self, in_memory_otel):
        from integrity_sdk.telemetry.aos_span import aos_run_span, aos_plan_span
        thought = "Testing that agent.thought is set on the plan span."
        with aos_run_span("did:integrity:test", "test_run"):
            with aos_plan_span(thought) as span:
                pass

        spans = in_memory_otel.get_finished_spans()
        plan_spans = [s for s in spans if s.name == "agent.plan"]
        assert len(plan_spans) == 1
        assert plan_spans[0].attributes["agent.thought"] == thought
        # Hash should also be set
        assert "agent.thought_hash" in plan_spans[0].attributes

    def test_sets_phase_attribute(self, in_memory_otel):
        from integrity_sdk.telemetry.aos_span import aos_plan_span
        with aos_plan_span("some thought") as span:
            pass
        spans = in_memory_otel.get_finished_spans()
        plan_spans = [s for s in spans if s.name == "agent.plan"]
        assert plan_spans[0].attributes["agent.phase"] == "planning"


class TestAosActionSpan:
    def test_sets_tool_name(self, in_memory_otel):
        from integrity_sdk.telemetry.aos_span import aos_action_span
        with aos_action_span("transfer_token", intent_type="payment") as span:
            pass
        spans = in_memory_otel.get_finished_spans()
        action_spans = [s for s in spans if s.name == "agent.execute_tool"]
        assert len(action_spans) == 1
        assert action_spans[0].attributes["tool.name"] == "transfer_token"
        assert action_spans[0].attributes["bcc.intent_type"] == "payment"


class TestTokenLedger:
    def setup_method(self):
        from integrity_sdk.telemetry.llm_token_ledger import LLMTokenLedger
        self.ledger = LLMTokenLedger()

    def test_record_and_total_tokens(self):
        from integrity_sdk.telemetry.llm_token_ledger import TokenEvent
        e1 = TokenEvent(agent_did="did:a", trace_id=None, span_id=None, model="gpt-4o",
                        prompt_tokens=100, completion_tokens=50)
        e2 = TokenEvent(agent_did="did:a", trace_id=None, span_id=None, model="gpt-4o",
                        prompt_tokens=200, completion_tokens=80)
        self.ledger.record(e1)
        self.ledger.record(e2)
        assert self.ledger.total_tokens("did:a") == 430  # 150 + 280

    def test_cot_coverage_rate_all_instrumented(self):
        from integrity_sdk.telemetry.llm_token_ledger import TokenEvent
        for i in range(3):
            e = TokenEvent(agent_did="did:b", trace_id=None, span_id=None, model="m",
                           thought_hash="abc123", thought_length=50)
            self.ledger.record(e)
        assert self.ledger.cot_coverage_rate("did:b") == 1.0

    def test_cot_coverage_rate_partial(self):
        from integrity_sdk.telemetry.llm_token_ledger import TokenEvent
        # 2 with thought, 1 without
        self.ledger.record(TokenEvent(agent_did="did:c", trace_id=None, span_id=None, model="m",
                                      thought_hash="abc", thought_length=10))
        self.ledger.record(TokenEvent(agent_did="did:c", trace_id=None, span_id=None, model="m",
                                      thought_hash="def", thought_length=20))
        self.ledger.record(TokenEvent(agent_did="did:c", trace_id=None, span_id=None, model="m"))
        rate = self.ledger.cot_coverage_rate("did:c")
        assert abs(rate - 2/3) < 0.01

    def test_cot_coverage_rate_empty(self):
        assert self.ledger.cot_coverage_rate("did:nobody") == 0.0

    def test_jsonl_persistence(self):
        from integrity_sdk.telemetry.llm_token_ledger import LLMTokenLedger, TokenEvent
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name

        ledger = LLMTokenLedger(persist_path=path)
        e = TokenEvent(agent_did="did:d", trace_id="abc", span_id="def", model="claude",
                       prompt_tokens=10, completion_tokens=5)
        ledger.record(e)

        with open(path) as f:
            lines = f.readlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["agent_did"] == "did:d"
        assert parsed["prompt_tokens"] == 10

    def test_to_bcc_token_count(self):
        from integrity_sdk.telemetry.llm_token_ledger import TokenEvent
        trace_id = "aabbcc"
        self.ledger.record(TokenEvent(agent_did="did:e", trace_id=trace_id, span_id=None,
                                      model="m", prompt_tokens=300, completion_tokens=100))
        self.ledger.record(TokenEvent(agent_did="did:e", trace_id=trace_id, span_id=None,
                                      model="m", prompt_tokens=50, completion_tokens=20))
        # Different trace should not be counted
        self.ledger.record(TokenEvent(agent_did="did:e", trace_id="other", span_id=None,
                                      model="m", prompt_tokens=999, completion_tokens=999))
        total = self.ledger.to_bcc_token_count("did:e", trace_id)
        assert total == 470  # 400 + 70

    def test_reset(self):
        from integrity_sdk.telemetry.llm_token_ledger import TokenEvent
        self.ledger.record(TokenEvent(agent_did="did:f", trace_id=None, span_id=None, model="m"))
        self.ledger.reset()
        assert self.ledger.total_tokens("did:f") == 0
