"""
LLM Token Ledger — per-agent token generation event store.

Captures every LLM call made by an agent: token counts (prompt, completion,
reasoning, cache), the agent.thought hash (for CoT coverage tracking), finish
reason, and trace correlation IDs. Optionally persists to JSONL for durable
local storage when no oracle is reachable.

This is the single authoritative source for:
  - Per-agent token spend (for BCC commitment token_count field)
  - CoT coverage rate (% of calls with a non-null agent.thought)
  - Budget consumption reporting to bcc_middleware
  - Entropy reduction tracking (instrumented vs uninstrumented calls)

The AOS source document frames this as:
    H = -K Σ Pᵢ ln Pᵢ
Every call without agent.thought is high-entropy (P_i unknown).
Every call with agent.thought collapses P_i → 1 for that step.
CoT coverage rate is thus a direct proxy for H reduction.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class TokenEvent:
    """
    One LLM inference event captured by the SDK.

    All token fields default to 0 rather than None so arithmetic is safe
    without defensive checks at the call site.
    """
    agent_did: str
    trace_id: str | None          # W3C 32-hex trace_id (from AOS context)
    span_id: str | None           # W3C 16-hex span_id (from AOS context)
    model: str                    # e.g. "gpt-4o", "claude-3-5-sonnet-20241022"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0     # extended thinking / o-series subset of completion
    cache_read_tokens: int = 0    # Anthropic: additive. OpenAI: subset of prompt.
    cache_creation_tokens: int = 0
    thought_hash: str | None = None   # sha256(agent_thought), or None if no CoT
    thought_length: int = 0           # len(agent_thought) in chars
    finish_reason: str | None = None  # "stop" | "tool_calls" | "length" | ...
    intent_type: str | None = None    # BCC intent_type if inside a BCC action span
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    @property
    def total_tokens(self) -> int:
        """Sum of prompt + completion (the typical 'tokens used' figure)."""
        return self.prompt_tokens + self.completion_tokens

    @property
    def has_cot(self) -> bool:
        """True if this call had a non-empty agent.thought captured."""
        return self.thought_hash is not None and self.thought_length > 0


def _hash_thought(thought: str | None) -> str | None:
    if not thought:
        return None
    return hashlib.sha256(thought.encode()).hexdigest()


class LLMTokenLedger:
    """
    In-process, thread-safe store of LLM token generation events.

    Designed to work standalone (no network, no DB) with optional JSONL
    persistence for local durability. The SDK's OpenAI/Anthropic wrappers
    call `record()` automatically — callers using the raw integrations do not
    need to touch this class directly.

    Scope limitation (same as bcc_middleware's circuit_breaker.py):
    process-local only. A multi-process deployment would need a shared store
    (Redis, Postgres). Documented here rather than silently assumed away.
    """

    def __init__(self, persist_path: str | Path | None = None):
        self._events: list[TokenEvent] = []
        self._lock = threading.Lock()
        self._persist_path: Path | None = Path(persist_path) if persist_path else None
        if self._persist_path:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: TokenEvent) -> None:
        """Append an event to the in-memory ledger and optionally to JSONL."""
        with self._lock:
            self._events.append(event)
            if self._persist_path:
                try:
                    with self._persist_path.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(asdict(event)) + "\n")
                except OSError:
                    pass  # persistence is best-effort; never a gate

    def record_from_llm_response(
        self,
        *,
        agent_did: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        reasoning_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_creation_tokens: int = 0,
        finish_reason: str | None = None,
        intent_type: str | None = None,
        agent_thought: str | None = None,
    ) -> TokenEvent:
        """
        Convenience constructor that auto-captures the current AOS span context
        (trace_id, span_id, agent_thought from the active plan span) and
        records the resulting event.

        Returns the constructed TokenEvent for callers that want to attach it
        to a BCC commitment.
        """
        # Auto-capture AOS context — never raises
        try:
            from .aos_span import get_current_aos_context
            ctx = get_current_aos_context()
            trace_id = ctx.get("trace_id")
            span_id = ctx.get("span_id")
            # Use explicit agent_thought if provided, else fall back to AOS context
            thought = agent_thought or ctx.get("agent_thought")
        except Exception:
            trace_id = None
            span_id = None
            thought = agent_thought

        event = TokenEvent(
            agent_did=agent_did,
            trace_id=trace_id,
            span_id=span_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            reasoning_tokens=reasoning_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_creation_tokens=cache_creation_tokens,
            thought_hash=_hash_thought(thought),
            thought_length=len(thought) if thought else 0,
            finish_reason=finish_reason,
            intent_type=intent_type,
        )
        self.record(event)
        return event

    def events_for_agent(
        self, agent_did: str, since_ms: int | None = None
    ) -> list[TokenEvent]:
        """Return all events for an agent, optionally filtered by start timestamp."""
        with self._lock:
            evts = [e for e in self._events if e.agent_did == agent_did]
        if since_ms is not None:
            evts = [e for e in evts if e.timestamp_ms >= since_ms]
        return evts

    def total_tokens(self, agent_did: str, since_ms: int | None = None) -> int:
        """Sum of prompt + completion tokens for an agent (optionally since a timestamp)."""
        return sum(e.total_tokens for e in self.events_for_agent(agent_did, since_ms))

    def events_since(self, agent_did: str, since_ms: int) -> list[TokenEvent]:
        """Alias for events_for_agent with since_ms required."""
        return self.events_for_agent(agent_did, since_ms=since_ms)

    def cot_coverage_rate(self, agent_did: str, since_ms: int | None = None) -> float:
        """
        Ratio of events with a non-null agent.thought (0.0 – 1.0).

        This is the AOS entropy reduction metric:
          rate → 1.0 means every call's reasoning is captured (H → 0).
          rate → 0.0 means all calls are black-box (H maximized).
        """
        evts = self.events_for_agent(agent_did, since_ms)
        if not evts:
            return 0.0
        instrumented = sum(1 for e in evts if e.has_cot)
        return instrumented / len(evts)

    def to_bcc_token_count(self, agent_did: str, trace_id: str) -> int:
        """
        Sum of total_tokens for all events from a specific trace.
        Use this to populate BCCCommitment.token_count — the total LLM
        tokens consumed to produce the action being committed.
        """
        with self._lock:
            return sum(
                e.total_tokens
                for e in self._events
                if e.agent_did == agent_did and e.trace_id == trace_id
            )

    def reset(self) -> None:
        """Clear all events. Used in tests."""
        with self._lock:
            self._events.clear()


# Module-level default ledger (process-singleton)
_default_ledger = LLMTokenLedger()


def get_ledger() -> LLMTokenLedger:
    """Return the process-default LLMTokenLedger instance."""
    return _default_ledger
