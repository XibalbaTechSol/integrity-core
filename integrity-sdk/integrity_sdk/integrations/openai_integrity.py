"""
OpenAI integration: a drop-in `OpenAI` client subclass that transparently
wraps `chat.completions` with OTel spans + behavioral-signal telemetry
logging, covering both streaming and non-streaming calls. Real, working
glue code carried over from the old prototype (not a mocked piece),
tidied up.

PHI/PII redaction (`redact_phi`) is OFF by default here. This wrapper is
general-purpose (trading/prediction-market/capital-allocation agents have
no PHI exposure at all), and defaulting to redaction everywhere both costs
fidelity on the captured text and was judged not worth it project-wide.
**Any Integrity Health / healthcare-vertical agent MUST pass
`redact_phi=True` explicitly** when constructing `IntegrityOpenAI` — this
wrapper has no way to know an agent's `compliance_vertical` on its own
(that's registered separately, via `registration.py`/`health.py`), so
nothing here can safely default it to True only for healthcare agents.
Getting this wrong for a healthcare deployment means raw, unredacted
completion text (and prompts) leave the process — see `security/redactor.py`
for exactly what categories `redact_text()` catches when it does run
(SSNs, emails, phone numbers, credit cards, API keys/secrets, MRNs).
"""

from __future__ import annotations

import logging
import math
import time
from typing import Any, Dict, Optional

try:
    from openai import OpenAI
    from openai.resources.chat import Completions
except ImportError:
    class OpenAI:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            pass

    class Completions:  # type: ignore[no-redef]
        def __init__(self, client):
            pass

from ..client import IntegrityClient
from ..telemetry.core import get_tracer
from ..telemetry.conventions import GenAIAttributes, IntegrityAttributes, get_gen_ai_span_name
from ..telemetry.derive import lexical_stability_score, keyword_grounding_score
from ..security.redactor import redact_text

logger = logging.getLogger("integrity_sdk.integrations.openai")



def _usage_to_dict(usage):
    """Provider-reported token usage as a plain dict, copied VERBATIM.

    Nothing is synthesized: a field the provider did not report is absent, not zero -- the
    same discipline `spec/token-accounting/vectors.json` encodes on the reading side. The
    nested `*_details` objects are carried through because they are informative (cached and
    reasoning token counts), even though the reducer deliberately does NOT add them: both
    are subsets of the halves they belong to, so adding them would double-count.
    """
    if usage is None:
        return None
    out = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens", "cost_usd", "cost", "currency", "rate_source"):
        value = getattr(usage, key, None)
        if value is not None:
            out[key] = value
    for details_key in ("prompt_tokens_details", "completion_tokens_details"):
        details = getattr(usage, details_key, None)
        if details is None:
            continue
        # openai-python returns pydantic models here; fall back to __dict__ for plain objects.
        as_dict = details.model_dump() if hasattr(details, "model_dump") else getattr(details, "__dict__", None)
        if isinstance(as_dict, dict):
            filtered = {k: v for k, v in as_dict.items() if v is not None}
            if filtered:
                out[details_key] = filtered
    return out or None


class IntegrityCompletionsWrapper:
    """Wraps the OpenAI completions interface to intercept inference calls
    with OTel spans and behavioral telemetry."""

    def __init__(
        self,
        original_completions: Completions,
        integrity_client: IntegrityClient,
        redact_phi: bool = False,
    ):
        self.original_completions = original_completions
        self.integrity_client = integrity_client
        self.tracer = get_tracer("integrity_openai_wrapper")
        self.redact_phi = redact_phi
        if not redact_phi:
            logger.warning(
                "IntegrityOpenAI(agent_id=%r): redact_phi=False -- prompt/completion text is captured "
                "UNREDACTED. If this is a Integrity Health / healthcare-vertical agent, this is a real "
                "PHI exposure risk; reconstruct with redact_phi=True.",
                getattr(integrity_client, "agent_id", "?"),
            )

    def _maybe_redact(self, text: str) -> str:
        return redact_text(text).text if self.redact_phi else text

    def create(self, *args, **kwargs):
        start_time = time.time()
        requested_model = kwargs.get("model", "unknown-model")
        span_name = get_gen_ai_span_name("openai", requested_model)

        messages = kwargs.get("messages", [])
        # A real, always-available proxy for how deep into a conversation
        # this call is -- there's no session/turn-id concept at this
        # wrapper layer (the OpenAI API itself is stateless per-call), so
        # this is honestly the closest observable signal rather than a
        # fabricated session_id.
        conversation_length = len(messages)
        try:
            prompt_text = " ".join(m.get("content", "") for m in messages if isinstance(m, dict))
        except Exception:
            prompt_text = ""
        # Redact before anything downstream (span attributes, behavior
        # metrics, telemetry payload) ever touches this text — see
        # security/redactor.py. Every use of prompt/completion text below
        # this point uses the redacted version, never the raw capture.
        prompt_text = self._maybe_redact(prompt_text)

        if kwargs.get("stream", False):
            try:
                response_generator = self.original_completions.create(*args, **kwargs)
            except Exception as e:
                self._log_failed_call(e, prompt_text, requested_model, conversation_length, start_time)
                raise
            return self._stream_interceptor(response_generator, prompt_text, start_time, requested_model, conversation_length)

        with self.tracer.start_as_current_span(span_name) as span:
            span.set_attribute(GenAIAttributes.SYSTEM, "openai")
            span.set_attribute(GenAIAttributes.REQUEST_MODEL, requested_model)
            span.set_attribute(GenAIAttributes.PROMPT, prompt_text)

            try:
                response = self.original_completions.create(*args, **kwargs)
            except Exception as e:
                span.record_exception(e)
                self._log_failed_call(e, prompt_text, requested_model, conversation_length, start_time)
                raise

            try:
                completion_text = self._maybe_redact(response.choices[0].message.content or "")
                actual_model = getattr(response, "model", requested_model)

                span.set_attribute(GenAIAttributes.RESPONSE_MODEL, actual_model)
                span.set_attribute(GenAIAttributes.COMPLETION, completion_text)

                usage = getattr(response, "usage", None)
                usage_dict = _usage_to_dict(usage)
                if usage:
                    span.set_attribute(GenAIAttributes.INPUT_TOKENS, usage.prompt_tokens)
                    span.set_attribute(GenAIAttributes.OUTPUT_TOKENS, usage.completion_tokens)

                if usage_dict:
                    try:
                        from ..telemetry.llm_token_ledger import get_ledger

                        get_ledger().record_from_llm_response(
                            agent_did=getattr(self.integrity_client, "agent_id", "?"),
                            model=actual_model,
                            prompt_tokens=usage_dict.get("prompt_tokens", 0) or 0,
                            completion_tokens=usage_dict.get("completion_tokens", 0) or 0,
                            reasoning_tokens=usage_dict.get("completion_tokens_details", {}).get(
                                "reasoning_tokens", 0
                            ) or 0,
                            cache_read_tokens=usage_dict.get("prompt_tokens_details", {}).get(
                                "cached_tokens", 0
                            ) or 0,
                            finish_reason=getattr(response.choices[0], "finish_reason", None),
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("token ledger record failed for a successful call: %r", exc)

                self._calculate_and_set_behavior_metrics(
                    span,
                    prompt_text,
                    completion_text,
                    {
                        "model_requested": requested_model,
                        "model_actual": actual_model,
                        # Real fields OpenAI's response already carries and this
                        # wrapper simply wasn't reading — a backend-config
                        # fingerprint (useful for detecting a silent model/infra
                        # change between calls) and the serving tier, not
                        # fabricated additions.
                        "system_fingerprint": getattr(response, "system_fingerprint", None),
                        "service_tier": getattr(response, "service_tier", None),
                        "tool_calls": self._extract_tool_call_names(response.choices[0].message.tool_calls),
                        "conversation_length": conversation_length,
                        # Token usage must reach the telemetry METADATA, not only the OTel
                        # span attributes above. `derive.entry_token_total` reads
                        # `metadata["token_usage"]`, so recording tokens on the span alone
                        # meant a direct-OpenAI agent contributed ZERO to the sacrifice
                        # signal while a LangChain agent contributed double. See
                        # spec/token-accounting/vectors.json for how these are reduced.
                        "token_usage": _usage_to_dict(usage),
                    },
                )
            except Exception as e:
                span.record_exception(e)

            return response

    def _stream_interceptor(
        self, generator, prompt_text: str, start_time: float, requested_model: str, conversation_length: int
    ):
        span_name = get_gen_ai_span_name("openai", requested_model)
        span = self.tracer.start_span(span_name)
        span.set_attribute(GenAIAttributes.SYSTEM, "openai")
        span.set_attribute(GenAIAttributes.REQUEST_MODEL, requested_model)
        span.set_attribute(GenAIAttributes.PROMPT, prompt_text)

        collected_chunks = []
        actual_model = requested_model
        chunk_latencies = []
        last_chunk_time = start_time
        ttft = 0.0
        system_fingerprint = None
        service_tier = None
        tool_call_names: Dict[int, str] = {}  # delta index -> name, first non-null wins
        stream_error: Optional[Exception] = None

        try:
            for chunk in generator:
                now = time.time()
                chunk_latencies.append((now - last_chunk_time) * 1000)
                if not collected_chunks:
                    ttft = (now - start_time) * 1000
                last_chunk_time = now
                yield chunk
                try:
                    if chunk.choices and chunk.choices[0].delta.content:
                        collected_chunks.append(chunk.choices[0].delta.content)
                    if getattr(chunk, "model", None):
                        actual_model = chunk.model
                    if getattr(chunk, "system_fingerprint", None):
                        system_fingerprint = chunk.system_fingerprint
                    if getattr(chunk, "service_tier", None):
                        service_tier = chunk.service_tier
                    if chunk.choices and chunk.choices[0].delta.tool_calls:
                        for tc in chunk.choices[0].delta.tool_calls:
                            if tc.function and tc.function.name and tc.index not in tool_call_names:
                                tool_call_names[tc.index] = tc.function.name
                except Exception:
                    pass
        except Exception as e:
            stream_error = e
            span.record_exception(e)
            raise
        finally:
            completion_text = self._maybe_redact("".join(collected_chunks))
            total_latency_ms = (time.time() - start_time) * 1000

            jitter = 0.0
            if len(chunk_latencies) > 1:
                avg = sum(chunk_latencies[1:]) / (len(chunk_latencies) - 1)
                variance = sum((x - avg) ** 2 for x in chunk_latencies[1:]) / (len(chunk_latencies) - 1)
                jitter = math.sqrt(variance)

            span.set_attribute(GenAIAttributes.RESPONSE_MODEL, actual_model)
            span.set_attribute(GenAIAttributes.COMPLETION, completion_text)
            span.set_attribute("gen_ai.usage.ttft_ms", ttft)
            span.set_attribute("gen_ai.usage.token_jitter_ms", jitter)

            extra_metrics: Dict[str, Any] = {
                "ttft_ms": ttft,
                "token_jitter_ms": jitter,
                "tokens_per_sec": (
                    len(collected_chunks) / (total_latency_ms / 1000.0) if total_latency_ms > 0 else 0
                ),
                "model_requested": requested_model,
                "model_actual": actual_model,
                "system_fingerprint": system_fingerprint,
                "service_tier": service_tier,
                "tool_calls": [{"name": name} for name in tool_call_names.values()],
                "conversation_length": conversation_length,
            }
            # A stream that broke partway through still yields real, useful
            # signal (partial completion text, whatever model/fingerprint
            # info arrived before the break) -- logged once here rather than
            # a second, separately-shaped "failed" log, so a broken stream
            # never produces two telemetry entries for one call.
            if stream_error is not None:
                extra_metrics["status"] = "failed"
                extra_metrics["error_taxonomy"] = type(stream_error).__name__

            self._calculate_and_set_behavior_metrics(span, prompt_text, completion_text, extra_metrics)
            span.end()

    def _log_failed_call(
        self, error: Exception, prompt_text: str, requested_model: str, conversation_length: int, start_time: float
    ) -> None:
        """A call that failed before any response/stream was ever created
        (auth error, rate limit, connection refused, etc). No completion
        text exists to derive entropy/grounding from, so this logs metadata
        only -- `type(error).__name__` gives a real exception-class taxonomy
        (RateLimitError, APITimeoutError, AuthenticationError, ...) for free
        from openai-python's own exception hierarchy, not a hand-maintained
        error-code mapping that could drift from it."""
        self.integrity_client.log_telemetry(
            metadata={
                "provider": "openai",
                "sdk_integration": "openai-integrity-wrapper",
                "model_requested": requested_model,
                "conversation_length": conversation_length,
                "prompt_length_chars": len(prompt_text),
                "latency_ms": (time.time() - start_time) * 1000,
                "status": "failed",
                "error_taxonomy": type(error).__name__,
            }
        )

    @staticmethod
    def _extract_tool_call_names(tool_calls: Any) -> list:
        """Names only, deliberately -- `function.arguments` can carry
        caller-supplied content (including, for an Integrity Health/healthcare agent,
        potentially sensitive parameter values) that hasn't been through
        `redact_text()`, so it's never captured here."""
        if not tool_calls:
            return []
        names = []
        for tc in tool_calls:
            fn = getattr(tc, "function", None)
            name = getattr(fn, "name", None) if fn else None
            if name:
                names.append({"name": name})
        return names

    def _calculate_and_set_behavior_metrics(
        self, span, prompt: str, completion: str, extra_metrics: Optional[Dict] = None
    ):
        extra_metrics = extra_metrics or {}
        # Single source of truth for these two heuristics now lives in
        # telemetry/derive.py — this wrapper used to compute a cruder
        # type-token ratio (len(set(words))/len(words)) inline, which could
        # silently drift from the batch-level derivation the oracle receives.
        # Both now call the same functions.
        entropy = lexical_stability_score(completion)
        grounding = keyword_grounding_score(completion)

        if span:
            span.set_attribute(IntegrityAttributes.ENTROPY, entropy)
            span.set_attribute(IntegrityAttributes.GROUNDING, grounding)

        log_metadata: Dict[str, Any] = {
            "prompt_length_chars": len(prompt),
            "completion_length_chars": len(completion),
            # Split what used to be one conflated "provider" value
            # ("openai-integrity-wrapper", which names this wrapper, not the
            # actual model provider) into the two real things it meant.
            "provider": "openai",
            "sdk_integration": "openai-integrity-wrapper",
            "text_output": completion,
        }
        log_metadata.update(extra_metrics)

        self.integrity_client.log_telemetry(metadata=log_metadata, entropy=entropy, grounding=grounding)


class IntegrityOpenAI(OpenAI):
    """Drop-in OpenAI client wrapper with non-blocking telemetry.

    `redact_phi` defaults to False (see module docstring) — pass
    `redact_phi=True` for any Integrity Health / healthcare-vertical agent.
    """

    def __init__(
        self,
        *args,
        agent_id: str = "openai_agent_edge",
        oracle_url: str = "http://localhost:8080",
        redact_phi: bool = False,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.integrity_client = IntegrityClient(agent_id=agent_id, oracle_url=oracle_url)

        if hasattr(self, "chat") and hasattr(self.chat, "completions"):
            self.chat.completions = IntegrityCompletionsWrapper(
                original_completions=self.chat.completions,
                integrity_client=self.integrity_client,
                redact_phi=redact_phi,
            )
