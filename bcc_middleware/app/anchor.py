"""
Submits a computed Merkle root to the on-chain `StateAnchor` contract.

Expected on-chain interface (documented here for `contracts/` to match):

    function anchorRoot(bytes32 root) external;

*** Anchoring is best-effort, NOT a security gate ***
Unlike OPA policy evaluation and the on-chain BAA check -- both of which
must fail CLOSED because they gate whether an action is authorized --
anchoring happens *after* a commitment has already been authorized. Its
purpose is building a tamper-evident audit trail, not deciding whether to
allow the action. So:
  - If `StateAnchor` isn't deployed yet (no address in
    deployments.local.json -- expected in dev before `contracts/` deploys),
    or the RPC/signer isn't configured, or the transaction fails, we log a
    warning and keep the batch's leaves so a later flush can retry. We do
    NOT deny or reverse the already-returned authorization -- blocking a
    real-time policy decision on L1 confirmation latency would defeat the
    point of a low-latency pre-execution gate.
  - This is a deliberate, documented asymmetry from the BAA check, not an
    oversight -- see README "Fail-closed vs. best-effort" section.
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass

from eth_account import Account
from web3.exceptions import Web3Exception

from app.chain import AgentResolutionError, get_w3, resolve_agent_primitives
from app.config import Settings
from app.merkle import BatchLeaf, merkle_root
from app.nonce_lock import send_with_managed_nonce, signer_lock

logger = logging.getLogger("bcc_middleware.anchor")

_STATE_ANCHOR_ABI = [
    {
        "inputs": [{"internalType": "bytes32", "name": "root", "type": "bytes32"}],
        "name": "anchorRoot",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]


@dataclass
class AnchorResult:
    submitted: bool
    detail: str
    tx_hash: str | None = None
    # The root actually submitted (or attempted) for this agent's sub-tree —
    # None only when we never got as far as computing one (e.g. the agent's
    # StateAnchor couldn't be resolved at all). PRODUCTION_GAPS.md §5: callers
    # used to have no way to learn the REAL per-agent root that was anchored,
    # since anchoring moved from one global root to per-agent sub-roots.
    root: bytes | None = None


def anchor_root(settings: Settings, root: bytes, *, contract_address: str | None = None) -> AnchorResult:
    """
    Signs and submits an `anchorRoot(root)` transaction. `contract_address`
    override exists for tests to target a locally-deployed mock without
    going through deployments.local.json.
    """
    address = contract_address or settings.contract_address(settings.state_anchor_contract_name)
    if not address:
        return AnchorResult(
            submitted=False,
            detail=f"no '{settings.state_anchor_contract_name}' address in {settings.deployments_file}",
        )

    if not settings.anchor_signer_private_key:
        return AnchorResult(submitted=False, detail="ANCHOR_SIGNER_PRIVATE_KEY not configured")

    w3 = get_w3(settings.rpc_url)
    if not w3.is_connected():
        return AnchorResult(submitted=False, detail=f"RPC {settings.rpc_url} is unreachable")

    try:
        account = Account.from_key(settings.anchor_signer_private_key)
        contract = w3.eth.contract(address=w3.to_checksum_address(address), abi=_STATE_ANCHOR_ABI)
        # Held for the FULL read-nonce -> sign -> broadcast -> mine sequence
        # -- see nonce_lock.py's module docstring for why a narrower lock
        # (e.g. just the nonce read) isn't enough to prevent a race with
        # app/reputation.py's chain writes when they share a signer key.
        with signer_lock(account.address):
            tx_hash, receipt = send_with_managed_nonce(
                w3,
                account,
                lambda nonce: contract.functions.anchorRoot(root).build_transaction(
                    {"from": account.address, "nonce": nonce, "chainId": settings.chain_id}
                ),
            )
    except (Web3Exception, ValueError) as exc:
        logger.warning("anchorRoot(0x%s) submission failed: %s", root.hex(), exc)
        return AnchorResult(submitted=False, detail=f"transaction submission failed: {exc}")

    if receipt.status != 1:
        return AnchorResult(submitted=False, detail=f"transaction reverted (status={receipt.status})", tx_hash=tx_hash.hex())

    return AnchorResult(submitted=True, detail="anchored", tx_hash=tx_hash.hex())


def anchor_batch_per_agent(settings: Settings, leaves: list[BatchLeaf]) -> dict[str, AnchorResult]:
    """
    Anchor a flushed batch to each agent's OWN StateAnchor, respecting the
    per-agent-primitive model (there is no longer one global StateAnchor).

    A `MerkleBatcher` accumulates approved commitments across *all* agents, so a
    flushed batch is a mix. This function splits that mix by `agent_id`, builds a
    per-agent sub-tree over just that agent's leaves, resolves that agent's own
    `StateAnchor` clone address (via the oracle — see
    chain.resolve_agent_primitives), and anchors the sub-root there. Each agent's
    StateAnchor therefore only ever accumulates that agent's own commitments — a
    genuinely per-agent, tamper-evident audit trail, which is more correct than a
    single cross-agent root anchored to some arbitrary agent's contract.

    Best-effort, exactly like the single-anchor path: an agent whose StateAnchor
    can't be resolved (unknown to the oracle, oracle down) or whose anchor tx
    fails is logged and skipped, never raised — anchoring happens *after*
    authorization and is an audit trail, not a gate. Returns a per-agent map of
    AnchorResult so the caller can log the outcome per agent.

    N transactions per flush (one per distinct agent) is the accepted cost of
    per-agent anchoring at this scale — the same tradeoff integrity-oracle makes
    for its own epoch anchoring.
    """
    results: dict[str, AnchorResult] = {}
    by_agent = {
        agent_id: list(group)
        for agent_id, group in itertools.groupby(
            sorted(leaves, key=lambda leaf: leaf.commitment.agent_id),
            key=lambda leaf: leaf.commitment.agent_id,
        )
    }

    for agent_id, agent_leaves in by_agent.items():
        try:
            primitives = resolve_agent_primitives(settings.oracle_url, agent_id)
            state_anchor_address = primitives.get("state_anchor")
        except AgentResolutionError as exc:
            logger.warning("cannot anchor batch for agent %s: %s -- retained in logs only", agent_id, exc)
            results[agent_id] = AnchorResult(submitted=False, detail=f"could not resolve StateAnchor: {exc}")
            continue
        if not state_anchor_address:
            results[agent_id] = AnchorResult(submitted=False, detail="oracle returned no state_anchor for agent")
            continue

        sub_root = merkle_root([leaf.leaf_hash for leaf in agent_leaves])
        result = anchor_root(settings, sub_root, contract_address=state_anchor_address)
        result.root = sub_root
        results[agent_id] = result
        if result.submitted:
            logger.info("anchored %d leaves for agent %s to StateAnchor %s tx=%s", len(agent_leaves), agent_id, state_anchor_address, result.tx_hash)
        else:
            logger.warning("could not anchor %d leaves for agent %s: %s -- retained in logs only", len(agent_leaves), agent_id, result.detail)

    return results
