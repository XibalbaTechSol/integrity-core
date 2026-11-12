"""
Shared web3 plumbing used by both the on-chain BAA check (baa.py) and Merkle
anchoring (anchor.py).

Both of those are genuine on-chain interactions against whatever EVM node
`RPC_URL` points at -- a local anvil instance in dev/test, per
docs/INTERFACE_CONTRACT.md §1/§2. Nothing in this module is a mock: if
`RPC_URL` is unreachable, `get_w3().is_connected()` returns False and callers
decide how to fail (closed for BAA, best-effort-logged for anchoring -- see
those modules' docstrings for why they differ).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from functools import lru_cache

import httpx
from eth_utils import to_checksum_address
from web3 import Web3

logger = logging.getLogger("bcc_middleware.chain")


class AgentResolutionError(Exception):
    """Raised when an agent's on-chain address(es) can't be resolved from the
    oracle. Callers that gate on this (baa.py) MUST treat it as a hard
    fail-closed — we cannot verify a BAA against an agent whose real on-chain
    identity we can't even resolve."""


@lru_cache(maxsize=8)
def get_w3(rpc_url: str) -> Web3:
    """
    Cached per rpc_url so we don't reopen a new HTTP provider on every
    request -- this is called on the hot path (every commitment that needs a
    BAA check).
    """
    return Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 5}))


@lru_cache(maxsize=1024)
def resolve_agent_primitives(oracle_url: str, agent_id: str) -> dict:
    """
    Resolve an agent's 7 on-chain primitive addresses from the oracle's
    `GET /v1/agent/{id}` (the `primitives` object — snake_case keys
    `sovereign_agent`, `state_anchor`, `reputation_registry`, …). Cached per
    (oracle_url, agent_id): a registered agent's primitive addresses are
    immutable, so this hot-path lookup only hits the oracle once per agent.

    The oracle is the right resolver here (not a direct chain read) because it
    already caches the on-chain `XibalbaAgentRegistry` mapping in Postgres and
    exposes it over HTTP — bcc_middleware doesn't need its own RPC round-trip
    or contract ABI just to turn a DID into addresses. Raises
    `AgentResolutionError` on any failure (agent unknown, oracle down,
    malformed response) so gated callers fail closed.
    """
    try:
        resp = httpx.get(f"{oracle_url.rstrip('/')}/v1/agent/{agent_id}", timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise AgentResolutionError(f"could not resolve agent {agent_id} from oracle {oracle_url}: {exc}") from exc

    primitives = data.get("primitives")
    if not isinstance(primitives, dict) or not primitives.get("sovereign_agent"):
        raise AgentResolutionError(
            f"oracle returned no primitives for agent {agent_id} "
            "(agent may be registered on-chain but not yet indexed by the oracle)"
        )
    return primitives


# --- verification-tier cache --------------------------------------------------
# resolve_verification_tier runs on EVERY commitment, before OPA. Calling the oracle
# synchronously each time put a WAN hop (and any oracle cold start) on the tool-call
# path, and a 5 s timeout silently turned into tier 0. So:
#   * a value younger than _TIER_FRESH_TTL is served with no oracle call;
#   * on a TRANSIENT failure (timeout, connection error, 5xx) the last-known-good value is
#     served, but only while it is younger than _TIER_MAX_STALE -- a revoked/lowered tier
#     must not outlive that bound;
#   * an authoritative 4xx (agent unknown/gone) evicts the entry and answers tier 0 --
#     stale data is never used to contradict the oracle when it IS reachable and says no;
#   * no usable value -> tier 0, exactly as before.
_TIER_FRESH_TTL = float(os.getenv("BCC_TIER_CACHE_TTL_SECONDS", "60"))
_TIER_MAX_STALE = float(os.getenv("BCC_TIER_MAX_STALE_SECONDS", "3600"))
_clock = time.monotonic
_tier_cache: dict[tuple[str, str], tuple[int, float]] = {}
_tier_lock = threading.Lock()


def clear_tier_cache() -> None:
    with _tier_lock:
        _tier_cache.clear()


def resolve_verification_tier(agent_id: str, *, oracle_url: str) -> int:
    """
    Resolve an agent's server-verified `verification_tier` (the oracle computes it at
    registration; it is never client-asserted) from `GET /v1/agent/{id}`, for
    `bcc.rego`'s `min_tier_by_intent_type` gate.

    Not `resolve_agent_primitives` (which caches forever): tier is mutable state, so
    values expire after `_TIER_FRESH_TTL`, and the last-known-good fallback is bounded by
    `_TIER_MAX_STALE`. See the cache notes above for the exact failure semantics.

    Never raises. Falls to tier 0 (lowest/most-restrictive) when nothing usable is
    available: tier-gated intent_types then deny, while non-tier-gated commitments are
    not taken down by a transient oracle hiccup (main.py calls this unconditionally).
    """
    key = (oracle_url.rstrip("/"), agent_id)
    now = _clock()
    with _tier_lock:
        cached = _tier_cache.get(key)
    if cached is not None and now - cached[1] < _TIER_FRESH_TTL:
        return cached[0]

    try:
        resp = httpx.get(f"{key[0]}/v1/agent/{agent_id}", timeout=5.0)
        resp.raise_for_status()
        tier = resp.json().get("verification_tier")
        if not isinstance(tier, int) or isinstance(tier, bool):
            raise ValueError(f"verification_tier missing or not an int in oracle response: {tier!r}")
    except httpx.HTTPStatusError as exc:
        if 400 <= exc.response.status_code < 500:
            with _tier_lock:
                _tier_cache.pop(key, None)
            logger.warning("oracle says agent %s has no tier (HTTP %s); tier 0", agent_id, exc.response.status_code)
            return 0
        return _stale_or_zero(key, agent_id, now, cached, exc)
    except (httpx.HTTPError, ValueError) as exc:
        return _stale_or_zero(key, agent_id, now, cached, exc)

    with _tier_lock:
        _tier_cache[key] = (tier, now)
    return tier


def _stale_or_zero(key, agent_id, now, cached, exc) -> int:
    if cached is not None and now - cached[1] <= _TIER_MAX_STALE:
        logger.warning(
            "oracle unavailable resolving tier for %s (%s); serving last-known-good tier %s (%.0fs old)",
            agent_id, exc, cached[0], now - cached[1],
        )
        return cached[0]
    logger.warning("could not resolve verification_tier for agent %s from oracle %s, defaulting to tier 0: %s", agent_id, key[0], exc)
    return 0


# --- AIS control-zone cache ----------------------------------------------------
# Same shape as the verification-tier cache above, for the same reason: when the AIS zone gate is on
# (BCC_AIS_ZONE_MODE, app/ais_zone.py) this runs on the tool-call path. The differences are deliberate:
#   * there is no safe default to fall to. Tier falls to 0; a zone that cannot be read is reported as
#     None ("unavailable") and the CALLER applies BCC_AIS_ZONE_UNAVAILABLE. Answering "green" here
#     would turn an oracle outage into full permission, and answering "red" would turn it into a
#     lockout the operator did not choose;
#   * the last-known-good bound is shorter (5 minutes, not an hour): a stale green is an agent that was
#     demoted and is still executing.
_ZONE_FRESH_TTL = float(os.getenv("BCC_AIS_ZONE_CACHE_TTL_SECONDS", "60"))
_ZONE_MAX_STALE = float(os.getenv("BCC_AIS_ZONE_MAX_STALE_SECONDS", "300"))
_CONTROL_ZONES = frozenset({"green", "yellow", "red"})  # the oracle's exact vocabulary (scoring-core)
_zone_cache: dict[tuple[str, str], tuple[str, float]] = {}
_zone_lock = threading.Lock()


def clear_zone_cache() -> None:
    with _zone_lock:
        _zone_cache.clear()


def resolve_control_zone(agent_id: str, *, oracle_url: str) -> str | None:
    """
    Resolve an agent's control zone (`"green"`, `"yellow"` or `"red"`) from the oracle's
    `GET /v1/agent/{id}/ais` -> `closed_loop_reward.control_zone`, or None when it is unavailable.

    Never raises. The zone is read, never computed here: the oracle is the only scorer.

      * a value younger than `_ZONE_FRESH_TTL` is served with no oracle call;
      * on a TRANSIENT failure (timeout, connection error, 5xx) or a body this function cannot use
        (not JSON, no `closed_loop_reward.control_zone`, a string outside the vocabulary) the
        last-known-good zone is served while it is younger than `_ZONE_MAX_STALE`, else None;
      * an authoritative 4xx (unknown agent) evicts the entry and answers None: stale data never
        contradicts an oracle that is reachable and says no.

    An unrecognised zone string is never cached and never read as green.
    """
    key = (oracle_url.rstrip("/"), agent_id)
    now = _clock()
    with _zone_lock:
        cached = _zone_cache.get(key)
    if cached is not None and now - cached[1] < _ZONE_FRESH_TTL:
        return cached[0]

    try:
        resp = httpx.get(f"{key[0]}/v1/agent/{agent_id}/ais", timeout=5.0)
        resp.raise_for_status()
        body = resp.json()
        reward = body.get("closed_loop_reward") if isinstance(body, dict) else None
        zone = reward.get("control_zone") if isinstance(reward, dict) else None
        if not isinstance(zone, str) or zone not in _CONTROL_ZONES:
            raise ValueError(f"closed_loop_reward.control_zone missing or not one of green/yellow/red in oracle response: {zone!r}")
    except httpx.HTTPStatusError as exc:
        if 400 <= exc.response.status_code < 500:
            with _zone_lock:
                _zone_cache.pop(key, None)
            logger.warning("oracle has no control zone for agent %s (HTTP %s); zone unavailable", agent_id, exc.response.status_code)
            return None
        return _stale_zone_or_none(key, agent_id, now, cached, exc)
    except (httpx.HTTPError, ValueError) as exc:
        return _stale_zone_or_none(key, agent_id, now, cached, exc)

    with _zone_lock:
        _zone_cache[key] = (zone, now)
    return zone


def _stale_zone_or_none(key, agent_id, now, cached, exc) -> str | None:
    if cached is not None and now - cached[1] <= _ZONE_MAX_STALE:
        logger.warning(
            "oracle unavailable resolving control zone for %s (%s); serving last-known-good zone %s (%.0fs old)",
            agent_id, exc, cached[0], now - cached[1],
        )
        return cached[0]
    logger.warning("could not resolve control zone for agent %s from oracle %s, zone unavailable: %s", agent_id, key[0], exc)
    return None


def agent_id_to_address(agent_id: str, *, oracle_url: str) -> str:
    """
    Resolve the `businessAssociate` EVM address for the on-chain BAA check
    (app/baa.py) from a `did:integrity:<fingerprint>` DID.

    The businessAssociate is the agent's **SovereignAgent contract address** —
    NOT its EOA/wallet, and not a derivation from the DID pubkey. That's
    deliberate and load-bearing: `SmartBAAFactory.createBAA` records the
    business associate by the address that will actually request access, and
    downstream Integrity Health contracts (`EHRGate.checkAccess`, `ComplianceGate`) all
    treat the SovereignAgent *contract* as the acting agent (it's their
    `msg.sender`). So a BAA is "active for" the SovereignAgent address, and
    that is the only address `isBAAActive(coveredEntity, businessAssociate)`
    will find a match for.

    Replaces the old `keccak256(pubkey)[-20:]` placeholder, which produced an
    address matching nothing on-chain. `coveredEntity` still does NOT come
    through here — it's the commitment's `covered_entity_address` field
    (covered entities have no DID).
    """
    primitives = resolve_agent_primitives(oracle_url, agent_id)
    return to_checksum_address(primitives["sovereign_agent"])
