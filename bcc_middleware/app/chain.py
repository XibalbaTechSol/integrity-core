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


def resolve_verification_tier(agent_id: str, *, oracle_url: str) -> int:
    """
    Resolve an agent's server-verified `verification_tier` (see
    `integrity-oracle/backend/src/handlers.rs`'s `SERVER_VERIFIED_TIER` — the oracle
    computes this itself at registration; it is never client-asserted) from the
    oracle's `GET /v1/agent/{id}`, for `bcc.rego`'s `min_tier_by_intent_type` gate.

    Deliberately NOT `resolve_agent_primitives` (also a `GET /v1/agent/{id}` call):
    that function's `@lru_cache` treats its result as immutable forever, which is
    correct for primitive addresses (they can't change post-registration) but would
    be wrong here — `verification_tier` is agent-mutable state (today it's always 1
    since no Tier 2/3 verification path exists yet, but this function must not bake
    in "tier never changes" as an assumption once that path is built). No caching.

    Fails to tier 0 (the lowest/most-restrictive tier) rather than raising, on any
    lookup failure — deliberately different from `agent_id_to_address`'s hard-fail
    behavior. Tier-gated `intent_type`s correctly deny on an unresolvable tier (fail
    closed for what actually needs it), but this must not take down every other,
    non-tier-gated commitment on a transient oracle hiccup — see `main.py`, which
    calls this unconditionally on every commitment before OPA evaluation, not just
    the subset that ends up being tier-gated.
    """
    try:
        resp = httpx.get(f"{oracle_url.rstrip('/')}/v1/agent/{agent_id}", timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        tier = data.get("verification_tier")
        if not isinstance(tier, int):
            raise ValueError(f"verification_tier missing or not an int in oracle response: {data!r}")
        return tier
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("could not resolve verification_tier for agent %s from oracle %s, defaulting to tier 0: %s", agent_id, oracle_url, exc)
        return 0


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
