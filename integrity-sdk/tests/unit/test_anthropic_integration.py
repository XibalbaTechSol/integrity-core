"""Anthropic integration (F5) and the L1 token taxonomy.

`anthropic` is an optional dependency and is not installed in this venv, so these tests drive
the wrapper with fakes shaped like real Messages-API responses. That is the point of the
wrapper's `__getattr__` passthrough design — the instrumented surface is small enough to test
without the vendor SDK, while the untested passthrough is one line.
"""

from __future__ import annotations

import pytest

from integrity_sdk.client import IntegrityClient
from integrity_sdk.integrations.anthropic_integrity import (
    IntegrityMessagesWrapper,
    merge_stream_usage,
    usage_to_dict,
)
from integrity_sdk.telemetry.derive import entry_token_total


class _Usage:
    """Anthropic's usage object: no total_tokens, and cache counts ADDITIONAL to input."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class _TextBlock:
    type = "text"

    def __init__(self, text: str):
        self.text = text


class _ToolBlock:
    type = "tool_use"
    name = "some_tool"


class _Response:
    def __init__(self, content, usage=None, model="claude-opus-5", stop_reason="end_turn"):
        self.content = content
        self.usage = usage
        self.model = model
        self.stop_reason = stop_reason


class _FakeMessages:
    """Stands in for `client.messages`, including a non-instrumented attribute to prove the
    wrapper's passthrough works."""

    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.unrelated_attribute = "passed through"

    def create(self, **kwargs):
        if self._error:
            raise self._error
        return self._response


def _client(**kwargs) -> IntegrityClient:
    return IntegrityClient("agent-anthropic", auto_flush=False, background_flush=False, **kwargs)


# --- usage capture -----------------------------------------------------------------------


def test_usage_captures_all_four_anthropic_token_classes() -> None:
    usage = _Usage(
        input_tokens=1200,
        output_tokens=800,
        cache_creation_input_tokens=300,
        cache_read_input_tokens=15000,
    )
    assert usage_to_dict(usage) == {
        "input_tokens": 1200,
        "output_tokens": 800,
        "cache_creation_input_tokens": 300,
        "cache_read_input_tokens": 15000,
    }


def test_usage_does_not_synthesize_a_total() -> None:
    """Anthropic reports no total_tokens. Computing one here would make the reducer trust our
    arithmetic instead of summing the classes itself, hiding any disagreement."""
    out = usage_to_dict(_Usage(input_tokens=10, output_tokens=5))
    assert "total_tokens" not in out


def test_usage_omits_absent_fields_rather_than_zeroing_them() -> None:
    """A field the provider did not report is ABSENT, not zero — zero would be a claim."""
    out = usage_to_dict(_Usage(input_tokens=10, output_tokens=5))
    assert out == {"input_tokens": 10, "output_tokens": 5}
    assert usage_to_dict(None) is None


def test_captured_usage_reduces_with_cache_tokens_added() -> None:
    """End-to-end with the reducer: Anthropic cache tokens are ADDITIONAL to input_tokens,
    so all four classes sum. Getting this backwards (OpenAI's subset semantics) would
    under-count by the cache figure, which is usually the largest one."""
    usage = usage_to_dict(
        _Usage(
            input_tokens=1200,
            output_tokens=800,
            cache_creation_input_tokens=300,
            cache_read_input_tokens=15000,
        )
    )
    assert entry_token_total({"metadata": {"token_usage": usage}}) == 17300


# --- streaming ---------------------------------------------------------------------------


def test_stream_usage_merges_both_halves() -> None:
    """message_start carries input+cache, message_delta carries the final output count. A
    wrapper reading only the terminal event loses every input token."""
    start = _Usage(input_tokens=1200, cache_read_input_tokens=15000)
    delta = _Usage(output_tokens=800)
    merged = merge_stream_usage(start, delta)
    assert merged == {
        "input_tokens": 1200,
        "cache_read_input_tokens": 15000,
        "output_tokens": 800,
    }
    assert entry_token_total({"metadata": {"token_usage": merged}}) == 17000


def test_stream_usage_handles_a_missing_half() -> None:
    assert merge_stream_usage(_Usage(input_tokens=5), None) == {"input_tokens": 5}
    assert merge_stream_usage(None, None) is None


# --- wrapper behaviour -------------------------------------------------------------------


def test_create_logs_token_usage_into_metadata_not_only_the_span(captured_posts) -> None:
    """The F1 lesson applied up front: derive reads metadata["token_usage"], so recording
    tokens only as span attributes would contribute ZERO to the sacrifice signal."""
    client = _client()
    response = _Response(
        content=[_TextBlock("The retrieved document states the balance is 42.")],
        usage=_Usage(input_tokens=1200, output_tokens=800, cache_read_input_tokens=15000),
    )
    wrapper = IntegrityMessagesWrapper(_FakeMessages(response), client)

    wrapper.create(model="claude-opus-5", messages=[{"role": "user", "content": "hi"}])
    client.flush_telemetry()

    entry = [s for s in captured_posts[0]["json"]["otel_spans"] if s.get("kind") == "telemetry"][0]
    usage = entry["metadata"]["token_usage"]
    assert usage["cache_read_input_tokens"] == 15000
    assert entry_token_total({"metadata": entry["metadata"]}) == 17000
    assert entry["metadata"]["stop_reason"] == "end_turn"
    assert entry["metadata"]["provider"] == "anthropic"


def test_non_text_blocks_are_not_scored_as_prose(captured_posts) -> None:
    """Content is a list of typed blocks. Stringifying a tool_use block would feed structure
    into the entropy/grounding heuristics as if it were language."""
    client = _client()
    response = _Response(content=[_TextBlock("hello there"), _ToolBlock()], usage=_Usage(input_tokens=1, output_tokens=1))
    wrapper = IntegrityMessagesWrapper(_FakeMessages(response), client)

    wrapper.create(model="claude-opus-5", messages=[{"role": "user", "content": "hi"}])
    client.flush_telemetry()

    entry = [s for s in captured_posts[0]["json"]["otel_spans"] if s.get("kind") == "telemetry"][0]
    assert entry["metadata"]["text_output"] == "hello there"


def test_failed_call_logs_taxonomy_and_reraises(captured_posts) -> None:
    client = _client()
    wrapper = IntegrityMessagesWrapper(_FakeMessages(error=TimeoutError("upstream timed out")), client)

    with pytest.raises(TimeoutError):
        wrapper.create(model="claude-opus-5", messages=[{"role": "user", "content": "hi"}])
    client.flush_telemetry()

    entry = [s for s in captured_posts[0]["json"]["otel_spans"] if s.get("kind") == "telemetry"][0]
    assert entry["metadata"]["status"] == "failed"
    assert entry["metadata"]["error_taxonomy"] == "TimeoutError"
    # No completion existed, so no entropy/grounding may be claimed for it.
    assert "entropy" not in entry


def test_telemetry_failure_never_breaks_the_call() -> None:
    """A telemetry bug must not take down the agent's actual work."""

    class _Exploding(IntegrityClient):
        def log_telemetry(self, *a, **k):
            raise RuntimeError("telemetry is broken")

    client = _Exploding("agent-boom", auto_flush=False, background_flush=False)
    response = _Response(content=[_TextBlock("fine")], usage=_Usage(input_tokens=1, output_tokens=1))
    wrapper = IntegrityMessagesWrapper(_FakeMessages(response), client)

    assert wrapper.create(model="claude-opus-5", messages=[]) is response


def test_unwrapped_attributes_pass_through() -> None:
    client = _client()
    wrapper = IntegrityMessagesWrapper(_FakeMessages(_Response(content=[])), client)
    assert wrapper.unrelated_attribute == "passed through"


def test_create_records_a_token_ledger_event(captured_posts) -> None:
    """The wrapper must feed the LLM token ledger, not only span attributes/telemetry
    metadata — otherwise a direct-Anthropic agent's token spend is invisible to the
    per-agent budget/BCC token_count path (llm_token_ledger.py)."""
    from integrity_sdk.telemetry.llm_token_ledger import get_ledger

    get_ledger().reset()
    client = _client()
    response = _Response(
        content=[_TextBlock("42")],
        usage=_Usage(input_tokens=100, output_tokens=50, cache_read_input_tokens=10),
        stop_reason="end_turn",
    )
    wrapper = IntegrityMessagesWrapper(_FakeMessages(response), client)

    wrapper.create(model="claude-opus-5", messages=[{"role": "user", "content": "hi"}])

    events = get_ledger().events_for_agent(client.agent_id)
    assert len(events) == 1
    assert events[0].prompt_tokens == 100
    assert events[0].completion_tokens == 50
    assert events[0].cache_read_tokens == 10
    assert events[0].finish_reason == "end_turn"
    get_ledger().reset()
