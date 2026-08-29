"""
integrations/langchain_callback.py: redact_phi default/opt-in behavior, and
the operational-metadata fields (llm_class/tool-call/error-taxonomy)
added alongside it. Real `IntegrityClient(auto_flush=False)`, same
rationale as test_openai_integrity.py. `LLMResult`/`Generation` are real
langchain_core classes (constructed directly, not mocked) since
langchain-core is installed -- their message/generation shape is exactly
what a real ChatOpenAI/etc. callback invocation would produce.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

# langchain-core is an optional extra (pyproject.toml's `langchain` group) --
# skip this whole module rather than fail collection when it isn't
# installed, matching langchain_callback.py's own ImportError-tolerant
# posture.
langchain_core = pytest.importorskip("langchain_core")
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, LLMResult  # noqa: E402

from integrity_sdk.client import IntegrityClient  # noqa: E402
from integrity_sdk.integrations.langchain_callback import IntegrityLangChainCallback  # noqa: E402


def _client() -> IntegrityClient:
    return IntegrityClient(agent_id="test-langchain-agent", auto_flush=False)


def _last_metadata(client: IntegrityClient) -> dict:
    return client._batcher.queue[-1]["metadata"]


def _serialized(class_path):
    return {"id": class_path}


def _result(text: str, *, tool_calls=None, reasoning=None, model_name="gpt-4o", system_fingerprint=None) -> LLMResult:
    additional_kwargs = {"reasoning_content": reasoning} if reasoning else {}
    message = AIMessage(content=text, tool_calls=tool_calls or [], additional_kwargs=additional_kwargs)
    generation = ChatGeneration(message=message, text=text)
    llm_output = {"model_name": model_name, "token_usage": {"total_tokens": 42}}
    if system_fingerprint:
        llm_output["system_fingerprint"] = system_fingerprint
    return LLMResult(generations=[[generation]], llm_output=llm_output)


@pytest.fixture
def messages():
    return [[SimpleNamespace(content="patient SSN is 123-45-6789")]]


def test_redact_phi_defaults_to_false(messages):
    client = _client()
    cb = IntegrityLangChainCallback(client)  # redact_phi omitted -> False
    cb.on_chat_model_start(_serialized(["langchain", "chat_models", "openai", "ChatOpenAI"]), messages, run_id="r1")

    cb.on_llm_end(_result("call 555-123-4567"), run_id="r1")

    meta = _last_metadata(client)
    assert meta["text_output"] == "call 555-123-4567"  # unredacted


def test_redact_phi_true_redacts_text_and_reasoning(messages):
    client = _client()
    cb = IntegrityLangChainCallback(client, redact_phi=True)
    cb.on_chat_model_start(_serialized(["x"]), messages, run_id="r1")

    cb.on_llm_end(_result("call 555-123-4567", reasoning="their number is 555-123-4567 too"), run_id="r1")

    meta = _last_metadata(client)
    assert "555-123-4567" not in meta["text_output"]
    assert "[REDACTED:PHONE]" in meta["text_output"]
    assert "555-123-4567" not in meta["reasoning_content"]


def test_llm_class_and_conversation_length_captured(messages):
    client = _client()
    cb = IntegrityLangChainCallback(client)
    cb.on_chat_model_start(_serialized(["langchain", "chat_models", "openai", "ChatOpenAI"]), messages, run_id="r1")

    cb.on_llm_end(_result("ok", system_fingerprint="fp_real"), run_id="r1")

    meta = _last_metadata(client)
    assert meta["llm_class"] == ["langchain", "chat_models", "openai", "ChatOpenAI"]
    assert meta["conversation_length"] == 1
    assert meta["system_fingerprint"] == "fp_real"
    assert meta["model_name"] == "gpt-4o"


def test_tool_call_names_captured_without_raw_args(messages):
    client = _client()
    cb = IntegrityLangChainCallback(client)
    cb.on_chat_model_start(_serialized(["x"]), messages, run_id="r1")

    cb.on_llm_end(
        _result("ok", tool_calls=[{"name": "lookup_patient_record", "args": {"mrn": "12345"}, "id": "t1"}]),
        run_id="r1",
    )

    meta = _last_metadata(client)
    assert meta["tool_calls"] == [{"name": "lookup_patient_record"}]
    assert "12345" not in str(meta)


def test_on_llm_error_logs_error_taxonomy_and_context(messages):
    client = _client()
    cb = IntegrityLangChainCallback(client)
    cb.on_chat_model_start(_serialized(["langchain", "chat_models", "anthropic"]), messages, run_id="r1")

    cb.on_llm_error(ConnectionError("rate limited"), run_id="r1")

    meta = _last_metadata(client)
    assert meta["status"] == "failed"
    assert meta["error_taxonomy"] == "ConnectionError"
    assert meta["error"] == "rate limited"
    assert meta["llm_class"] == ["langchain", "chat_models", "anthropic"]
    assert meta["conversation_length"] == 1


def test_run_context_is_isolated_per_run_id(messages):
    client = _client()
    cb = IntegrityLangChainCallback(client)
    cb.on_chat_model_start(_serialized(["a"]), messages, run_id="r1")
    cb.on_chat_model_start(_serialized(["b"]), [[SimpleNamespace(content="x")], [SimpleNamespace(content="y")]], run_id="r2")

    cb.on_llm_end(_result("first"), run_id="r1")
    cb.on_llm_end(_result("second"), run_id="r2")

    first_meta, second_meta = (entry["metadata"] for entry in client._batcher.queue[-2:])
    assert first_meta["llm_class"] == ["a"]
    assert second_meta["llm_class"] == ["b"]
