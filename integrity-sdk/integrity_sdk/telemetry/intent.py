"""
Pre-execution intent capture: `invoke_intent`, the OTel counterpart to
`bcc.build_bcc_commitment` (docs/INTERFACE_CONTRACT.md §4.2).

Why this file exists — the gap it closes:

A BCC commitment (`bcc.py`) already IS this protocol's real pre-execution
intent object: an agent signs `{intent_type, intended_state_hash, nonce, ...}`
*before* acting, and `bcc_middleware` gates on it at `POST /v1/bcc/intercept`.
What was missing is the connective tissue between that commitment and this
SDK's observability layer (`telemetry/tracing.py`'s `trace_run`/`traceable`):
there was no span emitted when an intent was committed, no correlation ID
tying that commitment to the `trace_run` produced by the execution that
followed it, and no automated check for whether execution actually matched
what was committed to.

Two research passes (2026-07-11) informed this module's design:
  1. Span/schema design: reuse OTel's `gen_ai.*` execution-span conventions
     as-is (already done — see `telemetry/tracing.py`/`conventions.py`);
     intent needs a NEW, first-class span type, emitted synchronously
     *before* execution, since the whole point of a pre-execution gate is
     that it can't depend on data that hasn't happened yet.
  2. Behavioral-metrics design: plan-vs-execution comparison should be
     TIERED by cost — tier 1 (deterministic structural diff: tool name +
     normalized args) computed inline, tier 2 (semantic similarity) and
     tier 3 (LLM-judge) only escalated to on a tier-1 mismatch, sampled.
     This module implements tier 1 only; tiers 2/3 are a documented,
     deliberately-deferred follow-on (see `compare_planned_to_actual`'s
     docstring) — this codebase's own existing preference (fail-closed OPA,
     ZK proofs over trusting an opaque scorer) argues for shipping the
     deterministic tier first and treating a judge as calibration, not gate.

Deliberately NOT a replacement for anything: `bcc.build_bcc_commitment` is
still the single source of truth for commitment construction/signing/
canonicalization; this module only adds observability (a span + a
`trace_run`-shaped record riding the same pipeline `client._record_trace_run`
already drains) and an optional post-hoc adherence check around it.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .. import bcc
from ..did import Keypair
from .core import get_tracer
from .tracing import TraceRun, _current_run_id


@dataclass
class IntentDeviationResult:
    """
    Tier-1 (deterministic, structural) comparison of a committed
    `planned_action` against the `actual_action` an agent actually took.
    Intentionally simple: exact tool-name match + normalized-argument
    equality. This is the "cheap, auditable, inline-computable" tier from
    the metrics research — no embeddings, no model call, reproducible by
    anyone re-running this same function against the same two dicts.

    `adherence_score` — 1.0 both match, 0.5 tool matches but args differ,
    0.0 tool doesn't match. Deliberately coarse (three values, not a
    continuous scale) since a structural diff has no principled way to say
    "70% of the way to a match" — that nuance is exactly what tier-2/3
    (semantic similarity / LLM judge) exist to add later, not something
    this tier should fake by inventing a fractional score.
    """

    matched_tool: bool
    matched_args: bool
    adherence_score: float
    planned_action: Optional[Dict[str, Any]]
    actual_action: Optional[Dict[str, Any]]
    detail: str
    # Hash-based intent-vs-effect join (~/.claude/plans/velvet-giggling-quill.md), distinct
    # from the structural planned_action/actual_action diff above: `effect_hash` is only set
    # when the caller passes `actual_effect_payload` to `record_outcome` (below), shaped
    # comparably to whatever `intent_payload` produced the commitment's own
    # `intended_state_hash` -- this module deliberately doesn't guess that mapping itself,
    # same separation of concerns its own docstring already states for planned_action.
    effect_hash: Optional[str] = None
    intent_matches_effect: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "matched_tool": self.matched_tool,
            "matched_args": self.matched_args,
            "adherence_score": self.adherence_score,
            "planned_action": self.planned_action,
            "actual_action": self.actual_action,
            "detail": self.detail,
            "effect_hash": self.effect_hash,
            "intent_matches_effect": self.intent_matches_effect,
        }


def _normalize_args(args: Any) -> Any:
    """Best-effort structural normalization so equivalent-but-differently-
    serialized args (key order, int vs numeric-string) don't register as a
    false mismatch. Round-trips through JSON with sorted keys — cheap, no
    external dependency, matches the same canonicalization philosophy
    `bcc.py`'s `canonical_json_bytes` already uses for a different purpose."""
    try:
        return json.loads(json.dumps(args, sort_keys=True, default=str))
    except (TypeError, ValueError):
        return args


def compare_planned_to_actual(
    planned_action: Optional[Dict[str, Any]],
    actual_action: Optional[Dict[str, Any]],
) -> IntentDeviationResult:
    """
    Tier-1 structural comparison. Expects both dicts to carry at least a
    `tool` key (the tool/function name) and an optional `args` key.

    `planned_action=None` (no plan was committed to compare against) or
    `actual_action=None` (caller never reported what actually happened)
    both return a `adherence_score=0.0` "unmatched" result rather than
    raising or silently skipping — an intent invocation with no recorded
    outcome is itself a gap worth surfacing (e.g. via
    `IntentInvocation.record_outcome` never having been called), not
    something this function should paper over as "fine".

    NOT implemented here, by design (see module docstring): tier 2
    (embedding-similarity comparison for paraphrased/equivalent-but-
    differently-worded actions) and tier 3 (sampled LLM-judge escalation
    on a tier-1 mismatch). Both are real follow-on work, not silently
    dropped scope — a tier-1 mismatch should be treated as "confirm with
    tier 2" by any caller building on this, not as a final verdict, until
    those tiers exist.
    """
    if planned_action is None or actual_action is None:
        return IntentDeviationResult(
            matched_tool=False,
            matched_args=False,
            adherence_score=0.0,
            planned_action=planned_action,
            actual_action=actual_action,
            detail="no comparison possible: planned_action or actual_action missing",
        )

    planned_tool = planned_action.get("tool")
    actual_tool = actual_action.get("tool")
    matched_tool = planned_tool is not None and planned_tool == actual_tool

    matched_args = matched_tool and _normalize_args(planned_action.get("args")) == _normalize_args(
        actual_action.get("args")
    )

    if matched_tool and matched_args:
        score, detail = 1.0, "tool and args match"
    elif matched_tool:
        score, detail = 0.5, "tool matches, args differ"
    else:
        score, detail = 0.0, f"tool mismatch: planned {planned_tool!r}, actual {actual_tool!r}"

    return IntentDeviationResult(
        matched_tool=matched_tool,
        matched_args=matched_args,
        adherence_score=score,
        planned_action=planned_action,
        actual_action=actual_action,
        detail=detail,
    )


@dataclass
class IntentInvocation:
    """Handle yielded by `invoke_intent`'s `with` block. `commitment` is the
    real, signed BCC commitment — POST it to bcc_middleware's
    `/v1/bcc/intercept` yourself (this module doesn't make that call, same
    separation of concerns as `bcc.py` itself: building/signing a commitment
    and deciding when/how to submit it for gating are different concerns)."""

    commitment: Dict[str, Any]
    intent_id: str
    run: TraceRun
    _span: Any = field(repr=False, default=None)
    _client: Optional[Any] = field(repr=False, default=None)
    deviation: Optional[IntentDeviationResult] = None

    def record_outcome(
        self,
        actual_action: Optional[Dict[str, Any]] = None,
        actual_effect_payload: Optional[Dict[str, Any]] = None,
    ) -> IntentDeviationResult:
        """
        Call after the action this intent committed to has actually run (or
        been denied/aborted), passing what actually happened as
        `{"tool": ..., "args": {...}}`. Computes the tier-1 adherence score
        and attaches it to both the OTel span (if a collector is attached)
        and this invocation's `trace_run` record (so it rides along on the
        next telemetry flush regardless of collector availability — same
        dual-path pattern `tracing.trace_run` already uses).

        `actual_effect_payload`, if given, must be shaped comparably to
        whatever `intent_payload` produced this commitment's own
        `intended_state_hash` — it gets hashed the identical way
        (`bcc.hash_intent_payload`) so the two are directly comparable. This
        is the intent-vs-effect join; use `posttool_report.submit_effect_report`
        to actually record the comparison (this method only computes it).

        Safe to call at most meaningfully once; a second call overwrites
        `self.deviation` with the new result (e.g. if a caller retries).
        """
        planned_action = self.commitment.get("_planned_action")
        result = compare_planned_to_actual(planned_action, actual_action)

        if actual_effect_payload is not None:
            result.effect_hash = bcc.hash_intent_payload(actual_effect_payload)
            result.intent_matches_effect = result.effect_hash == self.commitment.get("intended_state_hash")

        self.deviation = result

        if self._span is not None:
            self._span.set_attribute("integrity.intent.plan_adherence", result.adherence_score)
            self._span.set_attribute("integrity.intent.plan_adherence_detail", result.detail)
            if result.effect_hash is not None:
                self._span.set_attribute("integrity.intent.effect_hash", result.effect_hash)
                self._span.set_attribute("integrity.intent.matches_effect", bool(result.intent_matches_effect))

        if self._client is not None:
            self._client.record_metric(
                "integrity.intent.plan_adherence",
                result.adherence_score,
                tags={"intent_id": self.intent_id, "intent_type": self.commitment.get("intent_type", "")},
            )

        return result


class invoke_intent:
    """
    `with invoke_intent(intent_type="EMR_WRITE", intent_payload={...}, keypair=kp,
    nonce=n, agent_id=did, chain_id=84532, verifying_contract="0x...XibalbaAgentRegistry",
    planned_action={"tool": "write_emr", "args": {...}},
    goal="update patient record", policy_scope=["phi:write"]) as intent:
        decision = post_to_bcc_middleware(intent.commitment)  # your own call
        if decision.authorized:
            result = actually_call_write_emr(...)
            intent.record_outcome({"tool": "write_emr", "args": {...}})

    Builds and signs the real BCC commitment via `bcc.build_bcc_commitment`
    (unchanged, single source of truth), opens a `integrity.invoke_intent`
    OTel span BEFORE the block body runs (temporally prior to any execution
    span the body itself produces via `@client.traceable`, which will nest
    correctly underneath it — same `_current_run_id` contextvar
    `tracing.trace_run` already uses), and — if `client` is given — records a
    `trace_run`-shaped entry so this intent invocation rides along on the
    next `flush_telemetry` the same way a `traceable`-wrapped execution does.

    `intent_id` is the commitment's own `intended_state_hash` — deliberately
    reused rather than minting a second, parallel ID: it's already a unique,
    content-addressed identifier for exactly this intent, and reusing it
    means a trace backend and bcc_middleware's own logs can be correlated by
    the same value without this SDK inventing a second ID space.

    `goal`/`plan`/`reasoning` are opt-in, free-text observability fields —
    NOT part of the signed BCC commitment (adding them there would change
    `intended_state_hash`'s meaning and break wire compatibility with
    bcc_middleware's independent canonicalization). They're span attributes
    only, exactly like `gen_ai.input.messages` content-capture elsewhere in
    this SDK's conventions is opt-in and separate from what's cryptographically
    committed to.
    """

    def __init__(
        self,
        *,
        intent_type: str,
        intent_payload: Dict[str, Any],
        keypair: Keypair,
        nonce: int,
        agent_id: str,
        chain_id: int,
        verifying_contract: str,
        goal: Optional[str] = None,
        plan: Optional[List[str]] = None,
        planned_action: Optional[Dict[str, Any]] = None,
        policy_scope: Optional[List[str]] = None,
        reasoning: Optional[str] = None,
        timestamp_ms: Optional[int] = None,
        covered_entity_address: Optional[str] = None,
        client: Optional[Any] = None,
    ):
        self._client = client
        self._planned_action = planned_action
        self.commitment = bcc.build_bcc_commitment(
            agent_id=agent_id,
            intent_type=intent_type,
            intent_payload=intent_payload,
            nonce=nonce,
            keypair=keypair,
            chain_id=chain_id,
            verifying_contract=verifying_contract,
            timestamp_ms=timestamp_ms,
            covered_entity_address=covered_entity_address,
        )
        # Carried on the commitment dict under a `_`-prefixed key so
        # `record_outcome` can find it without a second parameter threaded
        # through the caller's code — NOT part of the signed payload (see
        # class docstring); stripped before anything sends this dict
        # anywhere that expects the frozen §4.2 shape byte-for-byte (callers
        # posting to bcc_middleware should already only be sending the
        # signed fields; this key existing alongside them in the same dict
        # is a local convenience, not a wire-protocol addition).
        self.commitment["_planned_action"] = planned_action

        self.intent_id = self.commitment["intended_state_hash"]
        parent_id = _current_run_id.get()
        self.run = TraceRun(
            name=f"invoke_intent:{intent_type}",
            run_type="intent",
            parent_run_id=parent_id,
            inputs={
                "intent_type": intent_type,
                "intent_id": self.intent_id,
                "goal": goal,
                "plan": plan,
                "planned_action": planned_action,
                "policy_scope": policy_scope,
                "reasoning": reasoning,
            },
        )
        self._goal = goal
        self._plan = plan
        self._policy_scope = policy_scope
        self._reasoning = reasoning
        self._token = None
        self._span_cm = None
        self._span = None
        self._invocation: Optional[IntentInvocation] = None

    def __enter__(self) -> IntentInvocation:
        self._token = _current_run_id.set(self.run.run_id)
        tracer = get_tracer("integrity_sdk.intent")
        self._span_cm = tracer.start_as_current_span("integrity.invoke_intent")
        self._span = self._span_cm.__enter__()
        self._span.set_attribute("integrity.intent.id", self.intent_id)
        self._span.set_attribute("integrity.intent.type", self.commitment["intent_type"])
        self._span.set_attribute("integrity.run_id", self.run.run_id)
        if self.run.parent_run_id:
            self._span.set_attribute("integrity.parent_run_id", self.run.parent_run_id)
        if self._goal:
            self._span.set_attribute("integrity.intent.goal", self._goal)
        if self._plan:
            self._span.set_attribute("integrity.intent.plan", json.dumps(self._plan))
        if self._policy_scope:
            self._span.set_attribute("integrity.intent.policy_scope", self._policy_scope)
        if self._reasoning:
            self._span.set_attribute("integrity.intent.reasoning", self._reasoning)
        if self._planned_action:
            self._span.set_attribute("integrity.intent.planned_action", json.dumps(self._planned_action, default=str))

        self._invocation = IntentInvocation(
            commitment=self.commitment,
            intent_id=self.intent_id,
            run=self.run,
            _span=self._span,
            _client=self._client,
        )
        return self._invocation

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.run.end_time = time.time()
        if self._invocation is not None and self._invocation.deviation is not None:
            self.run.set_outputs(self._invocation.deviation.to_dict())
        if exc_val is not None:
            self.run.error = f"{exc_type.__name__}: {exc_val}"
            if self._span is not None:
                self._span.record_exception(exc_val)
                self._span.set_attribute("integrity.run_error", self.run.error)

        if self._span_cm is not None:
            self._span_cm.__exit__(exc_type, exc_val, exc_tb)
        if self._token is not None:
            _current_run_id.reset(self._token)

        if self._client is not None:
            self._client._record_trace_run(self.run.to_dict())

        # Never swallow the caller's exception -- an intent invocation
        # observing an error is not the same as authorizing one.
        return False
