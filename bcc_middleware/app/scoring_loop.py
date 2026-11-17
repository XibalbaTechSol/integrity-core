"""
Periodically posts each known agent's oracle-computed AIS to the v3 `AISRegistry` as a
checkpoint keyed by the agent's actor, and raises a `StakeVault` dispute when the oracle's own
flagged-telemetry signal crosses a threshold (owner question 3 of the v2 graph deletion plan).

An agent with no actor bound in `AgentRegistry` is skipped with `NO_ACTOR` and no transaction
(owner question 8b): both singletons key on the actor, so there is nothing to write.

This is the orchestration layer over app/reputation.py's chain-write primitives -- pure Python,
no FastAPI/asyncio here, so `run_sync_cycle` is a single, independently-testable pass over every
agent the oracle knows about. app/main.py wraps it in a periodic asyncio loop at startup (see
Settings.score_sync_interval_seconds) and also exposes a manual POST /v1/reputation/sync trigger
for ops/tests.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import httpx

from app.chain import AgentResolutionError, resolve_agent_actor, stake_vault_address
from app.config import Settings
from app.reputation import MAX_SCORE_BPS, get_available_stake, post_checkpoint, raise_dispute

logger = logging.getLogger("bcc_middleware.scoring_loop")

# In-memory per-agent dispute cooldown. Disputes only LOCK stake (see
# reputation.py) rather than moving funds, so spamming duplicates isn't
# dangerous, just noise for whoever eventually resolves them. Process-local
# state is an accepted scope limitation at this scale, same posture as
# app/nonce_store.py / app/circuit_breaker.py.
_last_disputed_at: dict[str, float] = {}

# In-memory per-agent last successfully posted (actor, score_bps). PRODUCTION_GAPS.md §5:
# without this, every cycle posted a real (gas-costing) transaction for every agent forever, even
# when the score had not moved. Keyed with the actor because a v3 actor can change (`setActor`):
# a rebound agent gets a fresh checkpoint under its new actor. A restart just means one extra
# redundant post, not a correctness problem.
_last_pushed: dict[str, tuple[str, int]] = {}


@dataclass
class AgentSyncResult:
    agent_id: str
    score_pushed: bool
    score_detail: str
    dispute_raised: bool = False
    dispute_detail: str | None = None


@dataclass
class SyncCycleResult:
    agents_seen: int = 0
    results: list[AgentSyncResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _score_bps_from_ais_response(ais: dict) -> int | None:
    """
    Convert the oracle's authoritative final AIS (0..1000) into the basis points (0..10000)
    `AISRegistry.postCheckpoint` stores: 850 -> 8500.

    Do not recompute the formula from `components`/`weights` here. The Rust oracle is the sole AIS
    implementation: its `ais` field has already used the weighted geometric mean and applied the
    identity-tier ceiling. Nothing is divided out any more: the v2 ZK boost is dropped (owner
    question 2; the verifier was `RejectAllZkVerifier`, so the boost was always 1), and the
    v2-only `onchain_base_score` / `onchain_assurance_consistent` fields described the per-agent
    v2 score clone this no longer writes.
    """
    try:
        final_ais = float(ais["ais"])
    except (KeyError, TypeError, ValueError):
        return None
    if not math.isfinite(final_ais) or final_ais < 0.0:
        return None
    # Defense in depth for the Oracle's identity ceiling. The middleware still consumes the
    # authoritative score and never rebuilds the geometric formula, but a malformed/new response
    # must not let a low-tier value reach chain.
    if "tier_ceiling" in ais:
        try:
            ceiling = float(ais["tier_ceiling"])
        except (TypeError, ValueError):
            return None
        if not math.isfinite(ceiling) or ceiling < 0.0 or final_ais > ceiling + 1e-9:
            return None
    score_bps = round(final_ais * 10)
    return score_bps if score_bps <= MAX_SCORE_BPS else None


def _flagged_ratio(volume: list[dict]) -> tuple[int, int]:
    total = sum(int(bucket.get("count", 0)) for bucket in volume)
    flagged = sum(int(bucket.get("flagged_count", 0)) for bucket in volume)
    return flagged, total


def sync_one_agent(settings: Settings, agent_id: str, *, now: float) -> AgentSyncResult:
    try:
        actor = resolve_agent_actor(settings, agent_id)
    except AgentResolutionError as exc:
        return AgentSyncResult(agent_id=agent_id, score_pushed=False, score_detail=str(exc))
    if actor is None:
        return AgentSyncResult(
            agent_id=agent_id,
            score_pushed=False,
            score_detail="NO_ACTOR: AgentRegistry binds no actor to this agent; skipped, no transaction",
        )

    ais_registry = settings.contract_address("AISRegistry")
    if not ais_registry:
        return AgentSyncResult(
            agent_id=agent_id, score_pushed=False, score_detail=f"no 'AISRegistry' address in {settings.deployments_file}"
        )

    try:
        resp = httpx.get(f"{settings.oracle_url.rstrip('/')}/v1/agent/{agent_id}/ais", timeout=5.0)
        resp.raise_for_status()
        ais = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        return AgentSyncResult(agent_id=agent_id, score_pushed=False, score_detail=f"could not fetch AIS: {exc}")

    score_bps = _score_bps_from_ais_response(ais)
    if score_bps is None:
        return AgentSyncResult(agent_id=agent_id, score_pushed=False, score_detail="AIS response missing a valid ais")

    if _last_pushed.get(agent_id) == (actor, score_bps):
        result = AgentSyncResult(
            agent_id=agent_id, score_pushed=False, score_detail=f"unchanged (score={score_bps} bps), skipped"
        )
    else:
        push_result = post_checkpoint(settings, ais_registry, actor, score_bps, int(now))
        result = AgentSyncResult(agent_id=agent_id, score_pushed=push_result.submitted, score_detail=push_result.detail)
        if push_result.submitted:
            # Only cache on a CONFIRMED submission -- a failed post must not be remembered as
            # "unchanged", or a real pending update would be skipped forever.
            _last_pushed[agent_id] = (actor, score_bps)

    if not settings.dispute_enabled:
        return result

    if now - _last_disputed_at.get(agent_id, 0.0) < settings.dispute_cooldown_seconds:
        return result

    try:
        vol_resp = httpx.get(
            f"{settings.oracle_url.rstrip('/')}/v1/agent/{agent_id}/telemetry/volume",
            params={"bucket": settings.dispute_lookback_bucket},
            timeout=5.0,
        )
        vol_resp.raise_for_status()
        volume = vol_resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("could not fetch telemetry volume for %s, skipping dispute check: %s", agent_id, exc)
        return result

    flagged, total = _flagged_ratio(volume)
    if total < settings.dispute_min_events:
        return result
    ratio = flagged / total
    if ratio < settings.dispute_flagged_ratio_threshold:
        return result

    try:
        vault = stake_vault_address(settings)
    except AgentResolutionError as exc:
        logger.warning("dispute threshold crossed for %s but the StakeVault is unresolvable: %s", agent_id, exc)
        return result

    available = get_available_stake(settings, vault, actor)
    if not available:
        return result
    amount = available * settings.dispute_stake_bps // 10_000
    if amount <= 0:
        return result

    reason = f"oracle-flagged telemetry ratio {flagged}/{total} ({ratio:.0%}) over last {settings.dispute_lookback_bucket} bucket window"
    dispute_result = raise_dispute(settings, vault, actor, amount, reason)
    result.dispute_raised = dispute_result.submitted
    result.dispute_detail = dispute_result.detail
    if dispute_result.submitted:
        _last_disputed_at[agent_id] = now
        logger.warning("raised dispute for agent %s: %s (tx=%s)", agent_id, reason, dispute_result.tx_hash)

    return result


def run_sync_cycle(settings: Settings, *, now: float) -> SyncCycleResult:
    """
    One full pass over every agent the oracle knows about. `now` is passed
    in (rather than read via time.time() internally) so dispute-cooldown
    logic stays deterministic and testable; the periodic caller in
    main.py supplies the real wall clock.
    """
    cycle = SyncCycleResult()
    try:
        resp = httpx.get(f"{settings.oracle_url.rstrip('/')}/v1/agents", timeout=10.0)
        resp.raise_for_status()
        agents = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        cycle.errors.append(f"could not list agents from oracle: {exc}")
        return cycle

    cycle.agents_seen = len(agents)
    for agent in agents:
        agent_id = agent.get("id")
        if not agent_id:
            continue
        cycle.results.append(sync_one_agent(settings, agent_id, now=now))

    return cycle
