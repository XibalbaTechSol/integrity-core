"""
AOS (Agent Observability Standard) span helpers.

Implements the 3-level span hierarchy from the AOS spec (OWASP AOS §1.2.1):

  Session/Run Span  → agent.run                (top-level, per agent invocation)
    Logical Phase   → agent.plan               (reasoning; carries agent.thought)
      Atomic Action → agent.execute_tool       (gen_ai.operation.name = 'tool_call')

Usage
-----
    from integrity_sdk.telemetry.aos_span import aos_run_span, aos_plan_span, aos_action_span, get_current_aos_context

    async def my_agent():
        async with aos_run_span("did:integrity:...", "process_order"):
            thought = "The order looks valid. I will call transfer_token next."
            async with aos_plan_span(thought):
                ctx = get_current_aos_context()
                # ctx now contains trace_id, span_id, agent_thought
                # pass ctx directly into build_bcc_commitment(...)
                async with aos_action_span("transfer_token", intent_type="payment"):
                    ...

The key integration point is `get_current_aos_context()` — it reads the
*active* OTel span context and the *most recently set* agent.thought from the
planning span, returning a dict suitable for direct injection into
`build_bcc_commitment(**ctx, ...)`. If no OTel provider is configured, it
returns an empty dict (telemetry is always best-effort, never a gate).
"""

from __future__ import annotations

import hashlib
import logging
from contextlib import contextmanager
from typing import Any, Generator

logger = logging.getLogger("integrity_sdk.telemetry.aos_span")

# AOS attribute keys (aligned with OWASP AOS + OTel GenAI semantic conventions)
_AGENT_THOUGHT_KEY = "agent.thought"
_AGENT_THOUGHT_HASH_KEY = "agent.thought_hash"
_AGENT_PHASE_KEY = "agent.phase"
_TOOL_NAME_KEY = "tool.name"
_GEN_AI_OPERATION_KEY = "gen_ai.operation.name"
_GEN_AI_SYSTEM_KEY = "gen_ai.system"
_BCC_INTENT_TYPE_KEY = "bcc.intent_type"

# Process-local store for the agent.thought set on the most recent plan span.
# This lets get_current_aos_context() retrieve agent_thought without requiring
# callers to thread it through manually. Stored as a simple module-level var
# (last-write-wins) since an agent's planning phase is inherently sequential
# within a single thread/task. For multi-agent parallelism, use contextvars.
import contextvars as _cv
_current_thought: _cv.ContextVar[str | None] = _cv.ContextVar(
    "integrity_aos_current_thought", default=None
)


def _get_tracer():
    """Return the global OTel tracer, or None if OTel is not configured."""
    try:
        from opentelemetry import trace
        from .core import get_tracer
        tracer = get_tracer("integrity_sdk.aos")
        # If the provider is the no-op default, spans are discarded anyway —
        # returning the tracer is still safe.
        return tracer, trace
    except ImportError:
        return None, None


@contextmanager
def aos_run_span(agent_id: str, run_name: str) -> Generator[Any, None, None]:
    """
    Top-level Session/Run span (AOS §1.2.1 'agent.run').

    Sets `agent.id` and `integrity.run_name` on the span. All child spans
    (plan, action) inherit this as their parent automatically via OTel
    context propagation.
    """
    tracer, trace = _get_tracer()
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span(f"agent.run:{run_name}") as span:
        span.set_attribute("agent.id", agent_id)
        span.set_attribute("integrity.run_name", run_name)
        span.set_attribute("gen_ai.operation.name", "agent_run")
        try:
            yield span
        except Exception as exc:
            from opentelemetry.trace import Status, StatusCode
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


@contextmanager
def aos_plan_span(thought: str, operation: str = "reasoning_step") -> Generator[Any, None, None]:
    """
    Logical Phase span (AOS §1.2.1 'agent.plan').

    Attaches agent.thought to the span — this is the critical AOS semantic
    convention that binds the reasoning monologue to the execution trace.
    Also stores thought in a contextvars so get_current_aos_context() can
    retrieve it for BCC commitment construction.
    """
    tracer, trace = _get_tracer()
    token = _current_thought.set(thought)
    if tracer is None:
        try:
            yield None
        finally:
            _current_thought.reset(token)
        return

    thought_hash = hashlib.sha256(thought.encode()).hexdigest()
    with tracer.start_as_current_span("agent.plan") as span:
        span.set_attribute(_AGENT_THOUGHT_KEY, thought)
        span.set_attribute(_AGENT_THOUGHT_HASH_KEY, thought_hash)
        span.set_attribute(_GEN_AI_OPERATION_KEY, operation)
        span.set_attribute(_AGENT_PHASE_KEY, "planning")
        try:
            yield span
        except Exception as exc:
            from opentelemetry.trace import Status, StatusCode
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
        finally:
            _current_thought.reset(token)


@contextmanager
def aos_action_span(tool_name: str, intent_type: str | None = None) -> Generator[Any, None, None]:
    """
    Atomic Action span (AOS §1.2.1 'agent.execute_tool').

    Represents a single tool call or API operation. The child span of the
    plan span — OTel links them automatically via context propagation.
    """
    tracer, trace = _get_tracer()
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span("agent.execute_tool") as span:
        span.set_attribute(_TOOL_NAME_KEY, tool_name)
        span.set_attribute(_GEN_AI_SYSTEM_KEY, "integrity_protocol")
        span.set_attribute(_GEN_AI_OPERATION_KEY, "tool_call")
        span.set_attribute(_AGENT_PHASE_KEY, "execution")
        if intent_type:
            span.set_attribute(_BCC_INTENT_TYPE_KEY, intent_type)
        try:
            yield span
        except Exception as exc:
            from opentelemetry.trace import Status, StatusCode
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


def get_current_aos_context() -> dict[str, str | None]:
    """
    Read the active OTel span context and the most recent agent.thought from
    the planning span, returning a dict suitable for direct injection into
    `build_bcc_commitment(**get_current_aos_context(), ...)`.

    Returns:
        {
            "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",  # 32 hex chars
            "span_id":  "00f067aa0ba902b7",                   # 16 hex chars
            "agent_thought": "the reasoning monologue...",
        }
        or empty strings / None if no active span.

    Never raises — telemetry is always best-effort, never a gate.
    """
    result: dict[str, str | None] = {
        "trace_id": None,
        "span_id": None,
        "agent_thought": _current_thought.get(),
    }
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx.is_valid:
            result["trace_id"] = format(ctx.trace_id, "032x")
            result["span_id"] = format(ctx.span_id, "016x")
    except Exception:
        # OTel not configured or import failed — return whatever we have
        pass
    return result
