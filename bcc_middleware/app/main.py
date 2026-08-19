"""
BCC Middleware -- pre-execution policy gating ("Behavioral Commitment Chain").

Request flow for POST /v1/bcc/intercept, in order (see inline comments for
why each step is where it is):

  0. Schema validation (FastAPI/pydantic, via BCCCommitment).
  1. Circuit breaker check -- cheap, no I/O, so it goes first.
  1b. Deployment-binding check (chain_id + verifying_contract) -- cheap, no
      I/O, no crypto, so it runs before the actual signature check. chain_id
      is checked unconditionally (Settings.chain_id always has a value);
      verifying_contract is checked only when this deployment has a
      configured XibalbaAgentRegistry address, so a local/dev/test topology
      with no deployments file configured (common -- see
      Settings.contract_address's own "missing key is NOT an error" rule)
      isn't turned into a blanket deny. Disclosed limitation, not a silent
      downgrade -- see docs/plans/2026-08-18-phase1-canonical-intent-
      encoding-proposal.md's "Real risks".
  2. Signature verification -- if we can't trust the commitment came from
     `agent_id`, nothing downstream matters.
  3. Nonce replay check.
  4. Freshness (timestamp) check.
  4b. Active quarantine check -- denies only if the agent has stake POSITIVELY
      CONFIRMED locked under an unresolved Slasher dispute; fails OPEN (allows,
      logs a warning) if that can't be checked, since unlike step 6 this runs
      unconditionally for every request (app/quarantine.py). Closes
      PRODUCTION_GAPS.md §5's "nothing reads on-chain dispute state back into
      run_intercept" gap.
  5. OPA policy evaluation -- FAIL CLOSED if OPA is unreachable/erroring.
  6. On-chain BAA check, only if OPA flagged `requires_baa` -- FAIL CLOSED
     if we can't positively confirm an active BAA.
  7. Merkle batch admission + best-effort anchoring (not a gate -- see
     app/anchor.py).
  8. Best-effort audit reporting -- every allow AND deny decision (not just
     approved ones) is reported to the oracle's durable `audit_log` table
     (app/audit.py) so the dashboard's Audit Logs panel has a real event
     source. Never a gate; see app/audit.py's docstring for why.

Every deny path records *why* in the response `reason` field with a
consistent `SOME_CODE: detail` shape so operators/tests can pattern-match
on the failure category.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException

from app.baa import BAAStatus, check_baa_status
from app.canonical import SignatureVerificationError, verify_commitment_signature
from app.chain import resolve_verification_tier
from app.quarantine import QuarantineStatus, check_quarantine_status
from app.circuit_breaker import AgentCircuitBreaker
from app.config import Settings, settings as default_settings
from app.merkle import MerkleBatcher, leaf_hash
from app.nonce_store import NonceStore
from app.opa_client import OPAUnavailableError, evaluate as opa_evaluate
from app.token_budget import TokenBudgetEnforcer, token_budget_enforcer
from app.schemas import (
    BCCCommitment,
    BCCInterceptResponse,
    ClinicalAllowlistRequest,
    ClinicalAllowlistResponse,
    HealthResponse,
    VerifyTokenRequest,
    VerifyTokenResponse,
)
from app import anchor as anchor_module
from app import audit as audit_module
from app import opa_client
from app import scoring_loop as scoring_loop_module
from app import verification_token as verification_token_module

try:
    from opentelemetry import trace as otel_trace
    from opentelemetry.trace import Status as OtelStatus, StatusCode as OtelStatusCode
    _otel_tracer = otel_trace.get_tracer("bcc_middleware")
except ImportError:
    otel_trace = None  # type: ignore[assignment]
    _otel_tracer = None  # type: ignore[assignment]

logger = logging.getLogger("bcc_middleware")

_score_sync_task: asyncio.Task | None = None
_audit_shutdown_started = False


async def _score_sync_loop(settings: Settings) -> None:
    """
    Background loop, started at app startup: every
    `score_sync_interval_seconds`, runs one full run_sync_cycle over every
    agent the oracle knows about. Wrapped in try/except so one bad cycle
    (oracle hiccup, RPC blip) logs and retries on the next tick rather than
    killing the loop -- this is the ONLY thing that keeps agent scores
    moving on-chain at all today, so it must not silently stop running.
    """
    while True:
        try:
            result = await asyncio.to_thread(scoring_loop_module.run_sync_cycle, settings, now=time.time())
            pushed = sum(1 for r in result.results if r.score_pushed)
            disputed = sum(1 for r in result.results if r.dispute_raised)
            if result.errors:
                logger.warning("score sync cycle: %s", "; ".join(result.errors))
            else:
                logger.info(
                    "score sync cycle: %d agents seen, %d scores pushed, %d disputes raised",
                    result.agents_seen, pushed, disputed,
                )
        except Exception:
            logger.exception("score sync cycle crashed, will retry next interval")
        await asyncio.sleep(settings.score_sync_interval_seconds)


async def _drain_audit_reports(timeout: float = 10.0) -> None:
    """Drain audit tasks admitted before shutdown, with a hard deadline.

    The shutdown gate prevents new work from being admitted while this function
    drains. Re-checking the set handles tasks whose completion callbacks have not
    run yet, and cancelled/finished tasks are consumed so shutdown does not emit
    unhandled-task warnings.
    """
    deadline = asyncio.get_running_loop().time() + timeout
    while _audit_report_tasks:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            break
        await asyncio.wait(list(_audit_report_tasks), timeout=remaining)

    if _audit_report_tasks:
        pending = list(_audit_report_tasks)
        logger.warning(
            "shutdown: %d audit report(s) still in flight after %.0fs, giving up "
            "on the ASGI shutdown wait (the underlying thread may still be running)",
            len(pending),
            timeout,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        _audit_report_tasks.difference_update(pending)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _score_sync_task, _audit_shutdown_started
    _audit_shutdown_started = False
    if default_settings.score_sync_enabled:
        _score_sync_task = asyncio.create_task(_score_sync_loop(default_settings))
    yield
    if _score_sync_task is not None:
        _score_sync_task.cancel()
    _audit_shutdown_started = True
    await _drain_audit_reports()


app = FastAPI(title="BCC Middleware", version="3.0.0", lifespan=lifespan)

# Process-local state. See nonce_store.py / circuit_breaker.py docstrings
# for why in-memory is an accepted scope limitation for this service today
# (single replica dev/demo topology) rather than a correctness bug.
circuit_breaker = AgentCircuitBreaker(
    violation_threshold=default_settings.circuit_breaker_violation_threshold,
    lockout_duration_seconds=default_settings.circuit_breaker_lockout_seconds,
)
nonce_store = NonceStore()
batcher = MerkleBatcher(batch_size=default_settings.merkle_batch_size)


# Holds references to in-flight audit-report background tasks so asyncio doesn't
# garbage-collect (and silently cancel) them before the HTTP call completes --
# `asyncio.ensure_future` alone doesn't keep a task alive on its own.
_audit_report_tasks: set[asyncio.Task] = set()


def _report_decision_background(settings: Settings, *, agent_id: str | None, decision: str, reason_code: str | None = None, detail: str | None = None, intent_type: str | None = None, metadata: dict | None = None) -> None:
    if _audit_shutdown_started:
        logger.warning(
            "audit report dropped because middleware shutdown has started: agent=%s decision=%s",
            agent_id,
            decision,
        )
        return
    task = asyncio.ensure_future(
        asyncio.to_thread(
            audit_module.report_decision,
            settings,
            agent_id=agent_id,
            decision=decision,
            reason_code=reason_code,
            detail=detail,
            intent_type=intent_type,
            metadata=metadata,
        )
    )
    _audit_report_tasks.add(task)
    task.add_done_callback(_audit_report_tasks.discard)


def _record_violation(agent_id: str | None, settings: Settings) -> None:
    """Trip the circuit breaker for an agent-attributable violation -- EXCEPT in
    shadow mode, where we only observe. Locking out a well-behaved agent for a
    violation we deliberately did not enforce would defeat the purpose of a
    risk-free monitor-only rollout (see Settings.shadow_mode)."""
    if settings.shadow_mode:
        return
    if agent_id is not None:
        circuit_breaker.record_violation(agent_id)


def _deny(reason: str, *, agent_id: str | None, settings: Settings, intent_type: str | None = None) -> BCCInterceptResponse:
    # Reported in the background (not awaited) so a slow/unreachable oracle can
    # never add latency to this response -- see audit.py's module docstring for
    # why this is best-effort, same asymmetry as anchor.py's on-chain anchoring.
    code, _, detail = reason.partition(": ")
    if settings.shadow_mode:
        # Monitor-only: record the would-be denial (decision="shadow_deny" so it
        # is distinguishable from a real, enforced deny in the audit trail) but
        # do NOT block -- surface what enforcement WOULD have done and let the
        # caller proceed.
        _report_decision_background(settings, agent_id=agent_id, decision="shadow_deny", reason_code=code, detail=detail or reason, intent_type=intent_type)
        return BCCInterceptResponse(authorized=True, enforced=False, shadow_would_deny=True, reason=reason)
    _report_decision_background(settings, agent_id=agent_id, decision="deny", reason_code=code, detail=detail or reason, intent_type=intent_type)
    return BCCInterceptResponse(authorized=False, reason=reason)


def _report_anchor_events(settings: Settings, leaves: list, results: dict) -> None:
    """
    After a batch anchors, report each agent's committed leaves + its on-chain
    (root, tx_hash) to the oracle so anchored ALLOW decisions can be JOINed to
    their StateAnchor transaction at export time (evidence export, Lever 4).

    Groups the flushed leaves by agent the same way anchor_batch_per_agent does,
    and reports only agents whose anchor actually landed on-chain
    (result.submitted with a real root + tx). Best-effort throughout: this runs
    off the event loop (called from within _flush_and_anchor's to_thread worker,
    or force_flush) and never raises -- a missed report just leaves that decision
    un-linked until re-anchored, never a gate.
    """
    by_agent: dict[str, list] = {}
    for leaf in leaves:
        by_agent.setdefault(leaf.commitment.agent_id, []).append(leaf)
    for agent_id, agent_leaves in by_agent.items():
        result = results.get(agent_id)
        if result is None or not result.submitted or result.root is None or not result.tx_hash:
            continue
        audit_module.report_anchor_events(
            settings,
            agent_id=agent_id,
            leaves=[f"0x{leaf.leaf_hash.hex()}" for leaf in agent_leaves],
            root=f"0x{result.root.hex()}",
            tx_hash=result.tx_hash,
        )


def _flush_and_anchor(settings: Settings) -> None:
    """
    Flushes the pending batch (if full) and best-effort submits it on-chain.
    Anchoring failure is logged, not raised -- see app/anchor.py docstring
    for why this is intentionally not a gate on the caller's response.
    """
    if not batcher.is_full():
        return
    flushed = batcher.flush()
    if flushed is None:
        return
    _root, leaves = flushed
    # Anchor per-agent: each agent's leaves go to that agent's own StateAnchor
    # (StateAnchor is a per-agent primitive now — see anchor.anchor_batch_per_agent).
    results = anchor_module.anchor_batch_per_agent(settings, leaves)
    # Link the anchored leaves back to their decisions (evidence export). Runs
    # here, off the event loop, since _flush_and_anchor is dispatched via
    # asyncio.to_thread -- see run_intercept.
    _report_anchor_events(settings, leaves, results)


async def run_intercept(commitment: BCCCommitment, settings: Settings) -> BCCInterceptResponse:
    """
    Core interception logic, factored out of the route handler so tests can
    call it directly (and so a future non-HTTP entrypoint, e.g. a queue
    consumer, could reuse it).
    """
    agent_id = commitment.agent_id

    # Wrap the entire intercept pipeline in a single OTel span so every step
    # is traceable end-to-end. The span carries the agent's own trace_id/span_id
    # as correlation attributes (not as W3C context — bcc_middleware is a
    # standalone service, not part of the agent's distributed trace).
    _span_ctx = None
    if _otel_tracer is not None:
        _span_ctx = _otel_tracer.start_span("bcc.intercept")
        _span_ctx.set_attribute("agent.id", agent_id)
        _span_ctx.set_attribute("bcc.intent_type", commitment.intent_type)
        _span_ctx.set_attribute("bcc.nonce", commitment.nonce)
        _span_ctx.set_attribute("bcc.agent_trace_id", commitment.trace_id or "")
        _span_ctx.set_attribute("bcc.agent_span_id", commitment.span_id or "")
        _span_ctx.set_attribute("bcc.intent_rationale_length", len(commitment.intent_rationale or commitment.agent_thought or ""))
        _span_ctx.set_attribute("bcc.token_count", commitment.token_count or 0)

    def _finalize_span(decision: str, reason: str | None = None) -> None:
        if _span_ctx is None:
            return
        _span_ctx.set_attribute("bcc.decision", decision)
        if decision == "deny" and reason:
            _span_ctx.set_status(OtelStatus(OtelStatusCode.ERROR, reason))
        else:
            _span_ctx.set_status(OtelStatus(OtelStatusCode.OK))
        _span_ctx.end()

    try:
        return await _run_intercept_inner(commitment, settings, agent_id, _finalize_span)
    except Exception:
        _finalize_span("error")
        raise


async def _run_intercept_inner(
    commitment: BCCCommitment,
    settings: Settings,
    agent_id: str,
    finalize_span,
) -> BCCInterceptResponse:

    # --- 1. Circuit breaker -------------------------------------------------
    if circuit_breaker.is_locked_out(agent_id):
        remaining = int(circuit_breaker.lockout_remaining_seconds(agent_id))
        resp = _deny(f"CIRCUIT_BREAKER_OPEN: agent is locked out for {remaining}s due to prior violations", agent_id=agent_id, settings=settings, intent_type=commitment.intent_type)
        finalize_span("deny", resp.reason)
        return resp

    # --- 1b. Deployment-binding check ----------------------------------------
    # See module docstring for why this is split into an unconditional
    # chain_id check and a conditional verifying_contract check, and why
    # both run before signature verification (cheapest -- no crypto, no I/O).
    if commitment.chain_id != settings.chain_id:
        _record_violation(agent_id, settings)
        resp = _deny(
            f"BCC_CHAIN_MISMATCH: commitment signed for chain_id {commitment.chain_id}, this deployment is chain_id {settings.chain_id}",
            agent_id=agent_id, settings=settings, intent_type=commitment.intent_type,
        )
        finalize_span("deny", resp.reason)
        return resp

    configured_registry = settings.contract_address("XibalbaAgentRegistry")
    if configured_registry is not None and commitment.verifying_contract.lower() != configured_registry.lower():
        _record_violation(agent_id, settings)
        resp = _deny(
            f"BCC_VERIFYING_CONTRACT_MISMATCH: commitment names verifying_contract {commitment.verifying_contract}, this deployment's XibalbaAgentRegistry is {configured_registry}",
            agent_id=agent_id, settings=settings, intent_type=commitment.intent_type,
        )
        finalize_span("deny", resp.reason)
        return resp

    # --- 2. Signature verification ------------------------------------------
    # An invalid signature means we cannot trust `agent_id` authored this
    # commitment at all -- this DOES count as an agent-attributable
    # violation (either the agent is misbehaving, or someone is attempting
    # to forge commitments on its behalf; either way, lock it down).
    try:
        verify_commitment_signature(commitment)
    except SignatureVerificationError as exc:
        _record_violation(agent_id, settings)
        resp = _deny(f"BCC_INVALID_SIGNATURE: {exc}", agent_id=agent_id, settings=settings, intent_type=commitment.intent_type)
        finalize_span("deny", resp.reason)
        return resp

    # --- 3. Replay protection ------------------------------------------------
    if not nonce_store.check_and_record(agent_id, commitment.nonce):
        _record_violation(agent_id, settings)
        resp = _deny(f"BCC_NONCE_REPLAY: nonce {commitment.nonce} is not greater than the last accepted nonce for this agent", agent_id=agent_id, settings=settings, intent_type=commitment.intent_type)
        finalize_span("deny", resp.reason)
        return resp

    # --- 4. Freshness ----------------------------------------------------------
    age_ms = (time.time() * 1000) - commitment.timestamp
    if age_ms > settings.max_commitment_age_ms:
        _record_violation(agent_id, settings)
        resp = _deny(f"BCC_EXPIRED: commitment is {int(age_ms)}ms old, exceeds max age {settings.max_commitment_age_ms}ms", agent_id=agent_id, settings=settings, intent_type=commitment.intent_type)
        finalize_span("deny", resp.reason)
        return resp
    if age_ms < -settings.max_commitment_age_ms:
        _record_violation(agent_id, settings)
        resp = _deny("BCC_EXPIRED: commitment timestamp is implausibly far in the future", agent_id=agent_id, settings=settings, intent_type=commitment.intent_type)
        finalize_span("deny", resp.reason)
        return resp

    # --- 4b. Active quarantine check (fail-OPEN on CANNOT_VERIFY) -------------
    # An agent with stake locked under an unresolved Slasher dispute must not keep
    # transacting as if nothing happened — see app/quarantine.py's module docstring
    # for why this reads Slasher.lockedStakeOf, and why (unlike the BAA check below)
    # it fails OPEN rather than closed: this runs unconditionally for every request,
    # so failing closed on an unverifiable check would let one infra hiccup deny all
    # traffic from every agent. Only a positively confirmed QUARANTINED denies.
    quarantine_status, quarantine_detail = await asyncio.to_thread(check_quarantine_status, settings, agent_id)
    if quarantine_status is QuarantineStatus.QUARANTINED:
        _record_violation(agent_id, settings)
        resp = _deny(f"AGENT_QUARANTINED: {quarantine_detail}", agent_id=agent_id, settings=settings, intent_type=commitment.intent_type)
        finalize_span("deny", resp.reason)
        return resp
    elif quarantine_status is QuarantineStatus.CANNOT_VERIFY:
        logger.warning("quarantine check inconclusive for %s, allowing request to proceed: %s", agent_id, quarantine_detail)

    # --- 5. OPA policy evaluation (FAIL CLOSED) -------------------------------
    # verification_tier is resolved unconditionally (not just for intent_types the
    # policy happens to gate) because Rego needs it as an input field to evaluate
    # `min_tier_by_intent_type` against -- see chain.resolve_verification_tier's
    # docstring for why an unresolvable tier fails to 0 rather than failing the
    # whole request closed.
    verification_tier = await asyncio.to_thread(resolve_verification_tier, commitment.agent_id, oracle_url=settings.oracle_url)
    opa_input = {
        "agent_id": commitment.agent_id,
        "intent_type": commitment.intent_type,
        "intended_state_hash": commitment.intended_state_hash,
        "nonce": commitment.nonce,
        "timestamp": commitment.timestamp,
        "verification_tier": verification_tier,
        "trace_id": commitment.trace_id,
        "span_id": commitment.span_id,
        "intent_rationale": commitment.intent_rationale,
        "agent_thought": commitment.agent_thought,
        "token_count": commitment.token_count or 0,
        "daily_token_spend": token_budget_enforcer.get_daily_spend(agent_id),
    }
    try:
        decision = await opa_evaluate(settings, opa_input)
    except OPAUnavailableError as exc:
        # Infra failure, NOT an agent violation -- do not trip the circuit
        # breaker (see circuit_breaker.py docstring). Still deny: this is
        # the fail-closed behavior the interface contract requires.
        logger.error("OPA unavailable, failing closed: %s", exc)
        resp = _deny(f"BCC_POLICY_ENGINE_UNAVAILABLE: {exc}", agent_id=agent_id, settings=settings, intent_type=commitment.intent_type)
        finalize_span("deny", resp.reason)
        return resp

    if not decision.allow:
        _record_violation(agent_id, settings)
        reasons = "; ".join(decision.violations) or "policy denied without a specific reason"
        resp = _deny(f"OPA_REJECTION: {reasons}", agent_id=agent_id, settings=settings, intent_type=commitment.intent_type)
        finalize_span("deny", resp.reason)
        return resp

    # --- 5b. Token budget check (Python-layer enforcement) -------------------
    # OPA also has a declarative budget rule (for audit), but this layer is the
    # authoritative enforcer because it tracks cumulative daily spend in-process.
    if commitment.token_count is not None and commitment.token_count > 0:
        budget_ok, budget_reason = token_budget_enforcer.check_and_record(
            agent_id, verification_tier, commitment.token_count
        )
        if not budget_ok:
            _record_violation(agent_id, settings)
            resp = _deny(f"TOKEN_BUDGET_EXCEEDED: {budget_reason}", agent_id=agent_id, settings=settings, intent_type=commitment.intent_type)
            finalize_span("deny", resp.reason)
            return resp

    # --- 6. On-chain BAA check (FAIL CLOSED), only for healthcare-vertical intents ---
    # `commitment.covered_entity_address` (schemas.py) names WHICH covered
    # entity (hospital) this healthcare-vertical commitment is against --
    # the real on-chain isBAAActive(coveredEntity, businessAssociate) call
    # (app/baa.py) is keyed on that pair, not on the agent alone. If it's
    # unset here, check_baa_status fails closed with CANNOT_VERIFY rather
    # than guessing or skipping the check.
    if decision.requires_baa:
        status, detail = await asyncio.to_thread(check_baa_status, settings, agent_id, commitment.covered_entity_address)
        if status is not BAAStatus.ACTIVE:
            # Both "definitively inactive" and "cannot verify" deny -- an
            # unverifiable BAA must never be treated as compliant.
            _record_violation(agent_id, settings)
            code = "BAA_INACTIVE" if status is BAAStatus.INACTIVE else "BAA_CANNOT_VERIFY"
            resp = _deny(f"{code}: {detail}", agent_id=agent_id, settings=settings, intent_type=commitment.intent_type)
            finalize_span("deny", resp.reason)
            return resp

    # --- 7. Approved: admit to the merkle batch, issue a verification token ---
    batch_index = batcher.add(commitment)
    # The Merkle leaf for THIS commitment (same encoding the batcher/anchor use).
    # Recorded on the audit row so the anchor event reported once this leaf lands
    # on-chain can be JOINed back to this decision at export time (evidence
    # export, docs/design/evidence-export.md). Computed before the flush so it's
    # available regardless of whether this request triggers the flush.
    leaf_hex = f"0x{leaf_hash(commitment).hex()}"
    await asyncio.to_thread(_flush_and_anchor, settings)

    token = verification_token_module.issue_token(
        settings, commitment.agent_id, commitment.nonce, commitment.intended_state_hash
    )
    _report_decision_background(
        settings,
        agent_id=agent_id,
        decision="allow",
        detail=f"admitted to merkle batch index {batch_index}",
        intent_type=commitment.intent_type,
        metadata={"leaf": leaf_hex, "batch_index": batch_index, "verification_token": token},
    )
    # `enforced` mirrors the deployment posture even on the allow path so a
    # caller/dashboard can tell a genuinely-gated approval from a shadow-mode
    # one without inspecting server config.
    finalize_span("allow")
    return BCCInterceptResponse(authorized=True, enforced=not settings.shadow_mode, verification_token=token, batch_index=batch_index)


@app.post("/v1/bcc/intercept", response_model=BCCInterceptResponse)
async def intercept(commitment: BCCCommitment) -> BCCInterceptResponse:
    return await run_intercept(commitment, default_settings)


@app.post("/v1/reputation/sync")
async def force_score_sync() -> dict:
    """
    Operational/testing hook: run one score-sync cycle right now instead of
    waiting for the periodic loop. Not part of the interface contract; only
    exists so integration tests and operators don't have to wait
    `score_sync_interval_seconds` to observe a push.
    """
    result = await asyncio.to_thread(scoring_loop_module.run_sync_cycle, default_settings, now=time.time())
    return {
        "agents_seen": result.agents_seen,
        "errors": result.errors,
        "results": [
            {
                "agent_id": r.agent_id,
                "score_pushed": r.score_pushed,
                "score_detail": r.score_detail,
                "dispute_raised": r.dispute_raised,
                "dispute_detail": r.dispute_detail,
            }
            for r in result.results
        ],
    }


@app.post("/v1/bcc/verify_token", response_model=VerifyTokenResponse)
async def verify_token(request: VerifyTokenRequest) -> VerifyTokenResponse:
    """
    Lets a relying party (not just the agent that received the token) ask
    this service whether `token` was genuinely issued for exactly the given
    (agent_id, nonce, intended_state_hash) -- see app/verification_token.py.
    """
    valid = verification_token_module.verify_token(
        default_settings, request.token, request.agent_id, request.nonce, request.intended_state_hash
    )
    return VerifyTokenResponse(valid=valid)


@app.post("/v1/bcc/anchor/flush")
async def force_flush() -> dict:
    """
    Operational/testing hook: anchor whatever's pending right now instead of
    waiting for the batch to fill. Not part of the interface contract; only
    exists so integration tests and operators don't have to send
    `merkle_batch_size` real commitments to observe an anchoring transaction.
    """
    flushed = batcher.flush()
    if flushed is None:
        return {"flushed": False, "detail": "no pending commitments"}
    _discarded_full_batch_root, leaves = flushed
    # Per-agent anchoring: one StateAnchor tx per distinct agent in the batch.
    # NOTE: no single "root" field here anymore -- anchoring is per-agent
    # (see anchor.py), so the full-batch root above matches nothing that was
    # actually submitted on-chain. Each agent's OWN sub-root (the thing that
    # really got anchored, or attempted) is under `agents[agent_id].root`
    # instead (PRODUCTION_GAPS.md §5).
    results = anchor_module.anchor_batch_per_agent(default_settings, leaves)
    # Same decision->anchor linkage the auto-flush path records (evidence export).
    _report_anchor_events(default_settings, leaves, results)
    return {
        "flushed": True,
        "leaf_count": len(leaves),
        "agents": {
            agent_id: {
                "anchored": r.submitted,
                "detail": r.detail,
                "tx_hash": r.tx_hash,
                "root": f"0x{r.root.hex()}" if r.root is not None else None,
            }
            for agent_id, r in results.items()
        },
    }


@app.get("/v1/admin/clinical-allowlist", response_model=ClinicalAllowlistResponse)
async def get_clinical_allowlist() -> ClinicalAllowlistResponse:
    """
    Reads the runtime clinical-agent allowlist OPA data document
    (bcc.rego's `data.clinical_allowlist.agents` extension point, unioned into
    `authorized_clinical_agents` alongside the static demo set -- see
    policies/bcc.rego). This is the ONE part of policy behavior that can be
    changed without an OPA container redeploy; everything else in bcc.rego/
    general.rego requires editing the read-only-mounted .rego files and
    restarting the opa service. Returns an empty list if nothing has been set
    yet -- that's the real Rego default (`default _extra_clinical_agents :=
    []`), not a fabricated placeholder.
    """
    url = f"{default_settings.opa_url.rstrip('/')}/v1/data/clinical_allowlist/agents"
    try:
        async with httpx.AsyncClient(timeout=default_settings.opa_timeout_seconds) as client:
            resp = await client.get(url)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"OPA unreachable: {exc}") from exc
    if resp.status_code == 404:
        return ClinicalAllowlistResponse(agents=[])
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"OPA returned HTTP {resp.status_code}: {resp.text[:500]}")
    agents = resp.json().get("result", [])
    return ClinicalAllowlistResponse(agents=[str(a) for a in agents] if isinstance(agents, list) else [])


@app.put("/v1/admin/clinical-allowlist", response_model=ClinicalAllowlistResponse)
async def set_clinical_allowlist(request: ClinicalAllowlistRequest) -> ClinicalAllowlistResponse:
    """
    Full-replacement write to the same data document `get_clinical_allowlist`
    reads, via OPA's own Data API. In-memory only on OPA's side -- lost on an
    `opa` container restart, since nothing here persists it to a mounted
    file. That's an accepted limitation of this being the narrow, real
    extension point rather than general policy editing (which does require a
    redeploy) -- not silently pretended to be durable.
    """
    url = f"{default_settings.opa_url.rstrip('/')}/v1/data/clinical_allowlist/agents"
    try:
        async with httpx.AsyncClient(timeout=default_settings.opa_timeout_seconds) as client:
            resp = await client.put(url, json=request.agents)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"OPA unreachable: {exc}") from exc
    if resp.status_code not in (200, 204):
        raise HTTPException(status_code=502, detail=f"OPA returned HTTP {resp.status_code}: {resp.text[:500]}")
    return ClinicalAllowlistResponse(agents=request.agents)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    opa_ok = await opa_client.is_reachable(default_settings)
    from app.chain import get_w3

    try:
        chain_ok = get_w3(default_settings.rpc_url).is_connected()
    except Exception:  # a misconfigured RPC URL shouldn't crash the health check
        chain_ok = False
    return HealthResponse(
        status="online",
        opa_reachable=opa_ok,
        chain_reachable=chain_ok,
        pending_batch_size=batcher.pending_count,
        mode="shadow" if default_settings.shadow_mode else "enforce",
    )
