"""
LangChain integration: a callback handler that logs LLM interactions to an
`IntegrityClient` automatically. Real, working glue code (not one of the
previously-mocked pieces) — kept functionally equivalent to the old
prototype, with graceful degradation if `langchain_core` isn't installed
(this SDK doesn't want to force a LangChain dependency on every user).

PHI/PII redaction (`redact_phi`) is OFF by default here, same posture and
same reasoning as `openai_integrity.py`'s module docstring — this callback
is provider/vertical-agnostic (works with any LangChain-wrapped model, for
any agent vertical), so it can't safely infer "this needs PHI redaction" on
its own. **Any Integrity Health / healthcare-vertical agent MUST pass
`redact_phi=True`** when constructing `IntegrityLangChainCallback`.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

from ..security.redactor import redact_text

logger = logging.getLogger("integrity_sdk.integrations.langchain_callback")

try:
    from langchain_core.callbacks.base import BaseCallbackHandler
    from langchain_core.outputs import LLMResult
except ImportError:
    class BaseCallbackHandler:  # type: ignore[no-redef]
        pass

    LLMResult = Any  # type: ignore[assignment,misc]


class IntegrityLangChainCallback(BaseCallbackHandler):
    """
    Usage:
        client = IntegrityClient(agent_id="my-agent")
        callback = IntegrityLangChainCallback(client)
        llm = ChatOpenAI(callbacks=[callback])

    `redact_phi` defaults to False (see module docstring) — pass
    `redact_phi=True` for any Integrity Health / healthcare-vertical agent.
    """

    def __init__(self, integrity_client, redact_phi: bool = False):
        self.client = integrity_client
        self.redact_phi = redact_phi
        self.start_times: Dict[str, float] = {}
        # Context captured at call-start, consumed at call-end/error — a
        # real conversation-depth signal and the LLM class LangChain itself
        # reports, not fabricated additions (see on_llm_end/on_llm_error).
        self._run_context: Dict[str, Dict[str, Any]] = {}
        if not redact_phi:
            logger.warning(
                "IntegrityLangChainCallback: redact_phi=False -- prompt/completion/reasoning text is "
                "captured UNREDACTED. If this is a Integrity Health / healthcare-vertical agent, this is "
                "a real PHI exposure risk; reconstruct with redact_phi=True."
            )

    def _maybe_redact(self, text: str) -> str:
        return redact_text(text).text if self.redact_phi else text

    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any) -> None:
        run_id = str(kwargs.get("run_id", "default"))
        self.start_times[run_id] = time.time()
        self._run_context[run_id] = {
            "conversation_length": len(prompts),
            "llm_class": (serialized or {}).get("id"),
        }

    def on_chat_model_start(self, serialized: Dict[str, Any], messages: List[List[Any]], **kwargs: Any) -> None:
        run_id = str(kwargs.get("run_id", "default"))
        self.start_times[run_id] = time.time()
        self._run_context[run_id] = {
            "conversation_length": len(messages[0]) if messages else 0,
            "llm_class": (serialized or {}).get("id"),
        }

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        run_id = str(kwargs.get("run_id", "default"))
        start_time = self.start_times.pop(run_id, time.time())
        latency_ms = (time.time() - start_time) * 1000
        context = self._run_context.pop(run_id, {})

        try:
            for generation in response.generations:
                for gen in generation:
                    # Redact before this ever reaches log_telemetry — see
                    # security/redactor.py. Applies to both the completion
                    # text and any model-reported reasoning trace.
                    text_output = self._maybe_redact(gen.text)
                    reasoning_content = None
                    tool_calls: list = []
                    if hasattr(gen, "message") and hasattr(gen.message, "additional_kwargs"):
                        raw_reasoning = gen.message.additional_kwargs.get("reasoning_content")
                        if raw_reasoning:
                            reasoning_content = self._maybe_redact(raw_reasoning)
                    if hasattr(gen, "message"):
                        # Names only, deliberately -- a tool call's `args` can
                        # carry caller-supplied content (potentially sensitive
                        # for an Integrity Health agent) that hasn't been through
                        # `_maybe_redact()`, so it's never captured here. Same
                        # posture as openai_integrity.py's
                        # `_extract_tool_call_names`.
                        raw_tool_calls = getattr(gen.message, "tool_calls", None) or []
                        tool_calls = [
                            {"name": tc.get("name")} for tc in raw_tool_calls if isinstance(tc, dict) and tc.get("name")
                        ]

                    token_usage = response.llm_output.get("token_usage", {}) if response.llm_output else {}
                    model_name = (
                        response.llm_output.get("model_name", "langchain-generic")
                        if response.llm_output
                        else "langchain-generic"
                    )
                    # Some LangChain chat-model integrations (e.g. ChatOpenAI)
                    # surface the same real backend-config fingerprint
                    # openai_integrity.py reads directly from the raw
                    # response -- worth carrying through here too when
                    # present, None when the underlying provider doesn't
                    # expose it (never fabricated).
                    system_fingerprint = (
                        response.llm_output.get("system_fingerprint") if response.llm_output else None
                    )

                    self.client.log_telemetry(
                        metadata={
                            "text_output": text_output,
                            "token_usage": token_usage,
                            "model_name": model_name,
                            "system_fingerprint": system_fingerprint,
                            "llm_class": context.get("llm_class"),
                            "framework": "langchain",
                            "run_id": run_id,
                            "latency_ms": latency_ms,
                            "reasoning_content": reasoning_content,
                            "tool_calls": tool_calls,
                            "conversation_length": context.get("conversation_length"),
                        }
                    )
        except Exception as e:
            # Telemetry extraction must never crash the agent's actual run.
            logger.warning(f"[IntegrityLangChainCallback] Failed to extract telemetry: {e}")

    def on_llm_error(self, error: Exception, **kwargs: Any) -> None:
        run_id = str(kwargs.get("run_id", "default"))
        start_time = self.start_times.pop(run_id, time.time())
        latency_ms = (time.time() - start_time) * 1000
        context = self._run_context.pop(run_id, {})

        self.client.log_telemetry(
            metadata={
                "framework": "langchain",
                "llm_class": context.get("llm_class"),
                "conversation_length": context.get("conversation_length"),
                "error": str(error),
                # `type(error).__name__` gives a real exception-class
                # taxonomy for free -- LangChain re-raises many providers'
                # native exceptions unchanged, so this is honest per-provider
                # signal, not a hand-maintained mapping that could drift.
                "error_taxonomy": type(error).__name__,
                "latency_ms": latency_ms,
                "status": "failed",
            }
        )
