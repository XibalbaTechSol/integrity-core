"""
Periodically syncs each known agent's oracle-computed AIS to its on-chain
ReputationRegistry, and raises a Slasher dispute when the oracle's own
already-real flagged-telemetry signal crosses a threshold.

This is the orchestration layer over app/reputation.py's chain-write
primitives -- pure Python, no FastAPI/asyncio here, so `run_sync_cycle` is
a single, independently-testable pass over every agent the oracle knows
about. app/main.py wraps it in a periodic asyncio loop at startup (see
Settings.score_sync_interval_seconds) and also exposes a manual
POST /v1/reputation/sync trigger for ops/tests.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

from app.chain import AgentResolutionError, resolve_agent_primitives
from app.config import Settings
from app.reputation import get_available_stake, push_score, raise_dispute

logger = logging.getLogger("bcc_middleware.scoring_loop")

# In-memory per-agent dispute cooldown. Disputes only LOCK stake (see
# reputation.py) rather than moving funds, so spamming duplicates isn't
# dangerous, just noise for whoever eventually resolves them. Process-local
# state is an accepted scope limitation at this scale, same posture as
# app/nonce_store.py / app/circuit_breaker.py.
_last_disputed_at: dict[str, float] = {}

# In-memory per-agent last-successfully-pushed base score. PRODUCTION_GAPS.md
# §5: without this, `push_score` submitted a real (gas-costing) transaction
# every single cycle for every agent forever, even ones whose score hasn't
# moved between cycles -- pure waste for an idle agent. Same process-local
# scope-limitation posture as the dispute cooldown above (a restart just
# means one extra redundant push, not a correctness problem: ReputationRegistry.
# updateScore is idempotent for an unchanged value).
_last_pushed_score: dict[str, int] = {}


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


def _base_score_from_ais_response(ais: dict) -> int | None:
    """
    `ReputationRegistry.updateScore` wants the PRE-boost weighted sum (see
    that contract's own NatSpec), not the oracle's already-ZK-boosted
    `ais` field. Recomputed directly from `components`/`weights` rather
    than dividing `ais` by `zk_boost`, to avoid floating-point round-trip
    error and to keep working cleanly when zk_boost is (correctly) 1.0.
    """
    components = ais.get("components")
    weights = ais.get("weights")
    if not isinstance(components, dict) or not isinstance(weights, dict):
        return None
    try:
        total = sum(
            float(components[key]) * float(weights[key])
            for key in ("entropy", "grounding", "sacrifice", "compliance")
            if key in components and key in weights
        )
    except (TypeError, ValueError):
        return None
    return round(total)


def _flagged_ratio(volume: list[dict]) -> tuple[int, int]:
    total = sum(int(bucket.get("count", 0)) for bucket in volume)
    flagged = sum(int(bucket.get("flagged_count", 0)) for bucket in volume)
    return flagged, total


def sync_one_agent(settings: Settings, agent_id: str, *, now: float) -> AgentSyncResult:
    try:
        primitives = resolve_agent_primitives(settings.oracle_url, agent_id)
    except AgentResolutionError as exc:
        return AgentSyncResult(agent_id=agent_id, score_pushed=False, score_detail=str(exc))

    reputation_registry = primitives.get("reputation_registry")
    sovereign_agent = primitives.get("sovereign_agent")
    slasher = primitives.get("slasher")
    if not reputation_registry or not sovereign_agent:
        return AgentSyncResult(
            agent_id=agent_id,
            score_pushed=False,
            score_detail="oracle returned no reputation_registry/sovereign_agent for agent",
        )

    try:
        resp = httpx.get(f"{settings.oracle_url.rstrip('/')}/v1/agent/{agent_id}/ais", timeout=5.0)
        resp.raise_for_status()
        ais = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        return AgentSyncResult(agent_id=agent_id, score_pushed=False, score_detail=f"could not fetch AIS: {exc}")

    base_score = _base_score_from_ais_response(ais)
    if base_score is None:
        return AgentSyncResult(agent_id=agent_id, score_pushed=False, score_detail="AIS response missing components/weights")

    if _last_pushed_score.get(agent_id) == base_score:
        result = AgentSyncResult(
            agent_id=agent_id, score_pushed=False, score_detail=f"unchanged (base_score={base_score}), skipped"
        )
    else:
        push_result = push_score(settings, reputation_registry, sovereign_agent, base_score)
        result = AgentSyncResult(agent_id=agent_id, score_pushed=push_result.submitted, score_detail=push_result.detail)
        if push_result.submitted:
            # Only cache on a CONFIRMED submission -- a failed push must not
            # be remembered as "unchanged", or a real pending update would be
            # skipped forever on every subsequent cycle.
            _last_pushed_score[agent_id] = base_score

    if not slasher or not settings.dispute_enabled:
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

    available = get_available_stake(settings, slasher, sovereign_agent)
    if not available:
        return result
    amount = available * settings.dispute_stake_bps // 10_000
    if amount <= 0:
        return result

    reason = f"oracle-flagged telemetry ratio {flagged}/{total} ({ratio:.0%}) over last {settings.dispute_lookback_bucket} bucket window"
    dispute_result = raise_dispute(settings, slasher, sovereign_agent, amount, reason)
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
