"""
integrations/openai_integrity.py: redact_phi default/opt-in behavior, and
the operational-metadata fields (model/tool-call/error signals) added
alongside it. Uses a REAL `IntegrityClient` with `auto_flush=False` (so
`log_telemetry` just appends to its real in-memory batcher, no network
call) rather than a mock of the SDK's own class -- and realistic
`SimpleNamespace` stand-ins for the openai SDK's response/chunk objects,
matching the real `ChatCompletion`/`ChatCompletionChunk` field shapes
(verified against the installed `openai` package), since hitting the real
OpenAI API isn't feasible in a test run.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from integrity_sdk.client import IntegrityClient
from integrity_sdk.integrations.openai_integrity import IntegrityCompletionsWrapper


def _client() -> IntegrityClient:
    return IntegrityClient(agent_id="test-openai-agent", auto_flush=False)


def _last_metadata(client: IntegrityClient) -> dict:
    return client._batcher.queue[-1]["metadata"]


class _FakeCompletions:
    def __init__(self, response=None, stream_chunks=None, error=None):
        self._response = response
        self._stream_chunks = stream_chunks
        self._error = error

    def create(self, *args, **kwargs):
        if self._error is not None:
            raise self._error
        if kwargs.get("stream"):
            return iter(self._stream_chunks)
        return self._response


def _fake_response(content: str, *, tool_calls=None) -> SimpleNamespace:
    message = SimpleNamespace(content=content, tool_calls=tool_calls or [])
    return SimpleNamespace(
        model="gpt-4o-2024-08-06",
        system_fingerprint="fp_real123",
        service_tier="default",
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )


def _fake_tool_call(name: str) -> SimpleNamespace:
    return SimpleNamespace(function=SimpleNamespace(name=name, arguments='{"secret": "value"}'))


@pytest.fixture
def messages():
    return [{"role": "user", "content": "My SSN is 123-45-6789, please help."}]


def test_redact_phi_defaults_to_false_and_leaves_text_raw(messages):
    client = _client()
    completions = _FakeCompletions(response=_fake_response("call me at 555-123-4567"))
    wrapper = IntegrityCompletionsWrapper(completions, client)  # redact_phi omitted -> False

    wrapper.create(model="gpt-4o", messages=messages)

    meta = _last_metadata(client)
    assert meta["text_output"] == "call me at 555-123-4567"  # unredacted


def test_redact_phi_true_redacts_prompt_and_completion(messages):
    client = _client()
    completions = _FakeCompletions(response=_fake_response("call me at 555-123-4567"))
    wrapper = IntegrityCompletionsWrapper(completions, client, redact_phi=True)

    wrapper.create(model="gpt-4o", messages=messages)

    meta = _last_metadata(client)
    assert "555-123-4567" not in meta["text_output"]
    assert "[REDACTED:PHONE]" in meta["text_output"]


def test_real_model_and_provider_fields_are_captured(messages):
    client = _client()
    completions = _FakeCompletions(response=_fake_response("ok"))
    wrapper = IntegrityCompletionsWrapper(completions, client)

    wrapper.create(model="gpt-4o", messages=messages)

    meta = _last_metadata(client)
    assert meta["provider"] == "openai"
    assert meta["sdk_integration"] == "openai-integrity-wrapper"
    assert meta["model_requested"] == "gpt-4o"
    assert meta["model_actual"] == "gpt-4o-2024-08-06"
    assert meta["system_fingerprint"] == "fp_real123"
    assert meta["service_tier"] == "default"
    assert meta["conversation_length"] == 1


def test_tool_call_names_captured_without_raw_arguments(messages):
    client = _client()
    completions = _FakeCompletions(
        response=_fake_response("ok", tool_calls=[_fake_tool_call("lookup_patient_record")])
    )
    wrapper = IntegrityCompletionsWrapper(completions, client)

    wrapper.create(model="gpt-4o", messages=messages)

    meta = _last_metadata(client)
    assert meta["tool_calls"] == [{"name": "lookup_patient_record"}]
    # The raw JSON args string must never appear anywhere in what got logged.
    assert '"secret": "value"' not in str(meta)


def test_create_records_a_token_ledger_event(messages):
    """The wrapper must feed the LLM token ledger, not only telemetry metadata — otherwise
    a direct-OpenAI agent's token spend is invisible to the per-agent budget/BCC token_count
    path (llm_token_ledger.py)."""
    from integrity_sdk.telemetry.llm_token_ledger import get_ledger

    get_ledger().reset()
    client = _client()
    completions = _FakeCompletions(response=_fake_response("ok"))
    wrapper = IntegrityCompletionsWrapper(completions, client)

    wrapper.create(model="gpt-4o", messages=messages)

    events = get_ledger().events_for_agent(client.agent_id)
    assert len(events) == 1
    assert events[0].prompt_tokens == 10
    assert events[0].completion_tokens == 5
    assert events[0].model == "gpt-4o-2024-08-06"
    get_ledger().reset()


def test_failed_call_before_response_logs_error_taxonomy(messages):
    client = _client()
    completions = _FakeCompletions(error=ConnectionError("boom"))
    wrapper = IntegrityCompletionsWrapper(completions, client)

    with pytest.raises(ConnectionError):
        wrapper.create(model="gpt-4o", messages=messages)

    meta = _last_metadata(client)
    assert meta["status"] == "failed"
    assert meta["error_taxonomy"] == "ConnectionError"
    assert meta["model_requested"] == "gpt-4o"


def test_streaming_captures_model_and_tool_calls(messages):
    client = _client()
    chunk1 = SimpleNamespace(
        model="gpt-4o-2024-08-06",
        system_fingerprint="fp_stream1",
        service_tier="default",
        choices=[SimpleNamespace(delta=SimpleNamespace(content="Hel", tool_calls=None))],
    )
    tool_call_delta = SimpleNamespace(index=0, function=SimpleNamespace(name="search_web", arguments=""))
    chunk2 = SimpleNamespace(
        model="gpt-4o-2024-08-06",
        system_fingerprint=None,
        service_tier=None,
        choices=[SimpleNamespace(delta=SimpleNamespace(content="lo", tool_calls=[tool_call_delta]))],
    )
    completions = _FakeCompletions(stream_chunks=[chunk1, chunk2])
    wrapper = IntegrityCompletionsWrapper(completions, client)

    list(wrapper.create(model="gpt-4o", messages=messages, stream=True))

    meta = _last_metadata(client)
    assert meta["text_output"] == "Hello"
    assert meta["model_actual"] == "gpt-4o-2024-08-06"
    assert meta["system_fingerprint"] == "fp_stream1"
    assert meta["tool_calls"] == [{"name": "search_web"}]


def test_streaming_failure_logs_once_with_failed_status(messages):
    client = _client()

    def _broken_generator():
        yield SimpleNamespace(
            model="gpt-4o",
            system_fingerprint=None,
            service_tier=None,
            choices=[SimpleNamespace(delta=SimpleNamespace(content="partial", tool_calls=None))],
        )
        raise RuntimeError("stream dropped")

    completions = _FakeCompletions(stream_chunks=None)
    wrapper = IntegrityCompletionsWrapper(completions, client)

    with pytest.raises(RuntimeError):
        list(wrapper._stream_interceptor(_broken_generator(), "prompt", 0.0, "gpt-4o", 1))

    assert len(client._batcher.queue) == 1  # exactly one entry, not two
    meta = _last_metadata(client)
    assert meta["status"] == "failed"
    assert meta["error_taxonomy"] == "RuntimeError"
    assert meta["text_output"] == "partial"  # partial signal preserved
