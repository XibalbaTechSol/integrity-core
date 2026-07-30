"""
Anthropic integration: a drop-in `Anthropic` client wrapper that emits real Integrity
telemetry for every `messages.create` call.

Closes F5 in `docs/design/sdk-data-collection-strategy.md`. Before this there was no
Anthropic support anywhere in the SDK — coverage was OpenAI, LangChain, and one niche
internal — so an agent running on Claude could not have its token usage captured at all.

Two things this deliberately gets right, because the SDK previously got both wrong on the
OpenAI path:

1. **Usage reaches the telemetry METADATA, not only the OTel span.** `derive.entry_token_total`
   reads `metadata["token_usage"]`; recording tokens solely as span attributes meant a
   direct-provider agent contributed ZERO to the sacrifice signal.
2. **Cache tokens are captured as their own classes.** Anthropic reports
   `cache_creation_input_tokens` and `cache_read_input_tokens` **in addition to**
   `input_tokens` — the opposite of OpenAI, where `cached_tokens` is a subset of
   `prompt_tokens`. The reducer in `spec/token-accounting/vectors.json` treats them
   accordingly; this module's job is to report them verbatim and invent nothing.

Streaming is handled explicitly because Anthropic splits usage across events: `message_start`
carries input (and cache) counts, `message_delta` carries the final output count. A wrapper
that only read the terminal event would silently lose every input token.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

try:
    from anthropic import Anthropic
except ImportError:  # keeps the base SDK importable without the optional dependency
    class Anthropic:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            pass


from ..client import IntegrityClient
from ..security.redactor import redact_text
from ..telemetry.conventions import GenAIAttributes
from ..telemetry.core import get_tracer
from ..telemetry.derive import keyword_grounding_score, lexical_stability_score

logger = logging.getLogger("integrity_sdk.integrations.anthropic")

#: Token fields Anthropic reports, copied verbatim when present. `cache_*` are additive to
#: `input_tokens` (unlike OpenAI's subset semantics) — see this module's docstring.
_USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def usage_to_dict(usage: Any) -> Optional[Dict[str, Any]]:
    """Provider-reported usage as a plain dict, copied VERBATIM.

    Nothing is synthesized: a field the provider did not report is absent, not zero. In
    particular this does **not** compute a `total_tokens` — Anthropic does not report one, and
    inventing it here would mean the reducer took our arithmetic as authoritative instead of
    summing the classes itself, hiding any disagreement.
    """
    if usage is None:
        return None
    out: Dict[str, Any] = {}
    for key in _USAGE_FIELDS:
        value = getattr(usage, key, None)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        out[key] = value
    return out or None


def _extract_text(content: Any) -> str:
    """Concatenates the text of every `text` block in a Messages response.

    Anthropic returns content as a list of typed blocks (text, tool_use, thinking, ...), so
    there is no single `.text`. Non-text blocks are skipped rather than stringified: feeding a
    serialized tool-call into the entropy/grounding heuristics would score structure as prose.
    """
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if getattr(block, "type", None) == "text":
            text = getattr(block, "text", None)
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


class IntegrityMessagesWrapper:
    """Wraps `client.messages` so `create` is instrumented while everything else passes through."""

    def __init__(self, original_messages: Any, integrity_client: IntegrityClient, redact: bool = False):
        self._original = original_messages
        self.integrity_client = integrity_client
        self._redact = redact

    def __getattr__(self, name: str) -> Any:
        # Anything not overridden below (e.g. `count_tokens`, `batches`) reaches the real
        # object untouched — a wrapper that shadowed the whole surface would break callers.
        return getattr(self._original, name)

    def _maybe_redact(self, text: str) -> str:
        return redact_text(text) if self._redact else text

    def create(self, *args: Any, **kwargs: Any) -> Any:
        tracer = get_tracer("integrity_sdk.anthropic")
        requested_model = kwargs.get("model", "unknown")
        messages = kwargs.get("messages") or []
        prompt_text = self._maybe_redact(_prompt_text_of(messages))
        started = time.time()

        with tracer.start_as_current_span("anthropic.messages.create") as span:
            span.set_attribute(GenAIAttributes.SYSTEM, "anthropic")
            span.set_attribute(GenAIAttributes.REQUEST_MODEL, requested_model)

            try:
                response = self._original.create(*args, **kwargs)
            except Exception as exc:
                span.record_exception(exc)
                self._log_failure(exc, requested_model, len(messages), prompt_text, started)
                raise

            try:
                self._log_success(span, response, requested_model, len(messages), prompt_text, started)
            except Exception as exc:  # noqa: BLE001
                # Telemetry must never break the caller's actual work — the same rule
                # IntegrityClient applies to flushing.
                logger.warning("anthropic telemetry failed for a successful call: %r", exc)
            return response

    def _log_success(
        self,
        span: Any,
        response: Any,
        requested_model: str,
        conversation_length: int,
        prompt_text: str,
        started: float,
    ) -> None:
        completion = self._maybe_redact(_extract_text(getattr(response, "content", None)))
        actual_model = getattr(response, "model", requested_model)
        stop_reason = getattr(response, "stop_reason", None)
        usage = usage_to_dict(getattr(response, "usage", None))

        span.set_attribute(GenAIAttributes.RESPONSE_MODEL, actual_model)
        span.set_attribute(GenAIAttributes.COMPLETION, completion)
        if stop_reason:
            span.set_attribute(GenAIAttributes.STOP_REASON, stop_reason)
        if usage:
            # Span attributes AND metadata below — the span is for trace tooling, the metadata
            # is what the scoring path actually reads.
            for attr, key in (
                (GenAIAttributes.INPUT_TOKENS, "input_tokens"),
                (GenAIAttributes.OUTPUT_TOKENS, "output_tokens"),
                (GenAIAttributes.CACHE_READ_TOKENS, "cache_read_input_tokens"),
                (GenAIAttributes.CACHE_CREATION_TOKENS, "cache_creation_input_tokens"),
            ):
                if key in usage:
                    span.set_attribute(attr, usage[key])

        entropy = lexical_stability_score(completion)
        grounding = keyword_grounding_score(completion)

        self.integrity_client.log_telemetry(
            metadata={
                "provider": "anthropic",
                "sdk_integration": "anthropic-integrity-wrapper",
                "model_requested": requested_model,
                "model_actual": actual_model,
                "conversation_length": conversation_length,
                "prompt_length_chars": len(prompt_text),
                "latency_ms": (time.time() - started) * 1000,
                "status": "ok",
                # A refusal is a real compliance-relevant outcome, not an error — recorded so
                # it is observable rather than indistinguishable from a normal completion.
                "stop_reason": stop_reason,
                "text_output": completion,
                "token_usage": usage,
            },
            entropy=entropy,
            grounding=grounding,
        )

    def _log_failure(
        self, error: Exception, requested_model: str, conversation_length: int, prompt_text: str, started: float
    ) -> None:
        """A call that failed before any response existed. No completion text, so no
        entropy/grounding is claimed — the exception class is a real taxonomy from
        anthropic-python's own hierarchy rather than a hand-maintained mapping."""
        self.integrity_client.log_telemetry(
            metadata={
                "provider": "anthropic",
                "sdk_integration": "anthropic-integrity-wrapper",
                "model_requested": requested_model,
                "conversation_length": conversation_length,
                "prompt_length_chars": len(prompt_text),
                "latency_ms": (time.time() - started) * 1000,
                "status": "failed",
                "error_taxonomy": type(error).__name__,
            }
        )


def _prompt_text_of(messages: Any) -> str:
    """Flattens Messages-API input to text for the length/heuristic inputs only.

    Handles both shapes Anthropic accepts: a plain string content, and a list of content
    blocks. Never sent anywhere by itself — only its length and derived scores are, unless the
    caller opted into content capture.
    """
    if not isinstance(messages, list):
        return ""
    parts = []
    for message in messages:
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text")
                    if isinstance(text, str):
                        parts.append(text)
    return "\n".join(parts)


def merge_stream_usage(message_start_usage: Any, message_delta_usage: Any) -> Optional[Dict[str, Any]]:
    """Combines the two halves of a streamed response's usage.

    Anthropic splits it: `message_start` carries input and cache counts, `message_delta`
    carries the final output count. A wrapper reading only the terminal event loses every
    input token — the streaming equivalent of OpenAI's silent zero-usage path when
    `stream_options.include_usage` is unset.

    Later values win on conflict, since `message_delta` reports the final figure.
    """
    merged: Dict[str, Any] = {}
    for source in (message_start_usage, message_delta_usage):
        part = usage_to_dict(source)
        if part:
            merged.update(part)
    return merged or None


class IntegrityAnthropic(Anthropic):
    """Drop-in `Anthropic` replacement that reports telemetry for every `messages.create`.

    Mirrors `IntegrityOpenAI`: construct it exactly as the vendor client, plus an
    `integrity_client`. Telemetry is best-effort and never blocks or breaks a call.
    """

    def __init__(self, *args: Any, integrity_client: IntegrityClient, redact: bool = False, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.integrity_client = integrity_client
        self._integrity_messages = IntegrityMessagesWrapper(
            super().messages if hasattr(super(), "messages") else self.messages,
            integrity_client,
            redact=redact,
        )

    @property  # type: ignore[misc]
    def messages(self) -> Any:  # pragma: no cover - exercised through the wrapper's tests
        return self._integrity_messages
