"""
Submits a computed Merkle root to the v3 `ActionAnchor` singleton, under this service's own
signer address (owner question 8a of the v2 graph deletion plan).

On-chain interface (`contracts/src/trust/ActionAnchor.sol`, called through its canonical ABI):

    function anchorRoot(bytes32 root) external returns (uint256 newEpoch);
    event RootAnchored(address indexed agent, uint256 epoch, bytes32 root);

`ActionAnchor` keys every root on `msg.sender` and keeps only the LATEST root per sender. So
the BCC has exactly one slot (its signer address), `verifyLeaf(signer, leaf, proof)` checks only
the most recent batch, and every earlier batch is verified against the root its own
`RootAnchored` event carries (the tx hash recorded with each anchored leaf locates it).

*** Anchoring is best-effort, NOT a security gate ***
Unlike OPA policy evaluation and the on-chain BAA check -- both of which
must fail CLOSED because they gate whether an action is authorized --
anchoring happens *after* a commitment has already been authorized. Its
purpose is building a tamper-evident audit trail, not deciding whether to
allow the action. So:
  - If `ActionAnchor` isn't deployed yet (no address in
    deployments.local.json -- expected in dev before `contracts/` deploys),
    or the RPC/signer isn't configured, or the transaction fails, we log a
    warning. The current in-memory batch owner does not durably retain a
    failed submission across flush or process restart. We do NOT deny or
    reverse the already-returned authorization -- blocking a
    real-time policy decision on L1 confirmation latency would defeat the
    point of a low-latency pre-execution gate.
  - This is a deliberate, documented asymmetry from the BAA check, not an
    oversight -- see README "Fail-closed vs. best-effort" section.
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass, field

from eth_account import Account
from web3.exceptions import Web3Exception

from app.chain import AgentResolutionError, get_w3, registry_contract
from app.config import Settings
from app.merkle import BatchLeaf, merkle_proof, merkle_root
from app.nonce_lock import send_with_managed_nonce, signer_lock

logger = logging.getLogger("bcc_middleware.anchor")


@dataclass
class AnchorResult:
    submitted: bool
    detail: str
    tx_hash: str | None = None
    # This agent's own sub-root (the root over just its leaves) -- None only when we never got
    # as far as computing one. PRODUCTION_GAPS.md §5: callers need the REAL per-agent root.
    root: bytes | None = None
    # The root actually anchored on-chain: the batch root over every agent's sub-root in the
    # flush (owner question 8a: per-agent sub-roots are the leaves of one batch root).
    batch_root: bytes | None = None
    # Sibling path from `root` up to `batch_root`. A leaf's proof within the agent's sub-tree
    # followed by this path verifies the leaf against `batch_root` (sorted pairs compose).
    proof: list[bytes] = field(default_factory=list)
    # The address whose ActionAnchor slot holds `batch_root`: this service's signer.
    anchorer: str | None = None


def anchor_root(settings: Settings, root: bytes, *, contract_address: str | None = None) -> AnchorResult:
    """
    Signs and submits `ActionAnchor.anchorRoot(root)` from the anchor signer, so the root lands
    under the signer's address. `contract_address` overrides the deployments-file entry (tests,
    and the receipt-epoch anchor's optional separate target).
    """
    address = contract_address or settings.contract_address(settings.protocol_evidence_anchor_contract_name)
    if not address:
        return AnchorResult(
            submitted=False,
            detail=f"no '{settings.protocol_evidence_anchor_contract_name}' address in {settings.deployments_file}",
        )

    if not settings.anchor_signer_private_key:
        return AnchorResult(submitted=False, detail="ANCHOR_SIGNER_PRIVATE_KEY not configured")

    w3 = get_w3(settings.rpc_url)
    if not w3.is_connected():
        return AnchorResult(submitted=False, detail=f"RPC {settings.rpc_url} is unreachable")

    try:
        account = Account.from_key(settings.anchor_signer_private_key)
        contract = registry_contract(settings, "ActionAnchor", address)
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
    except (AgentResolutionError, Web3Exception, ValueError) as exc:
        logger.warning("anchorRoot(0x%s) submission failed: %s", root.hex(), exc)
        return AnchorResult(submitted=False, detail=f"transaction submission failed: {exc}")

    if receipt.status != 1:
        return AnchorResult(submitted=False, detail=f"transaction reverted (status={receipt.status})", tx_hash=tx_hash.hex())

    return AnchorResult(submitted=True, detail="anchored", tx_hash=tx_hash.hex(), batch_root=root, anchorer=account.address)


def anchor_batch_per_agent(settings: Settings, leaves: list[BatchLeaf]) -> dict[str, AnchorResult]:
    """
    Anchor a flushed batch on `ActionAnchor` as ONE root under this service's signer (owner
    question 8a), built from per-agent sub-roots.

    A `MerkleBatcher` accumulates approved commitments across *all* agents, so a flushed batch
    is a mix. This function splits that mix by `agent_id`, builds a sub-tree over each agent's
    leaves (its sub-root, independently verifiable since 2026-09, PRODUCTION_GAPS.md §5), and
    then a batch tree whose leaves are those sub-roots. Only the batch root is anchored: one
    transaction per flush, where the v2 per-agent design needed one per agent.

    Each agent's result carries its sub-root, the batch root, the sub-root's proof up to the
    batch root, the tx hash and the anchorer (the signer address). A commitment leaf verifies
    with its sub-tree proof followed by that path, against the batch root: on-chain via
    `verifyLeaf(anchorer, leaf, proof)` while it is the anchorer's latest root, and afterwards
    against the root in that transaction's `RootAnchored` event (ActionAnchor keeps only the
    latest root per address).

    Best-effort, exactly like the single-anchor path: a missing anchor address, a missing signer
    or a failed tx is logged and reported per agent, never raised -- anchoring happens *after*
    authorization and is an audit trail, not a gate.
    """
    by_agent = {
        agent_id: list(group)
        for agent_id, group in itertools.groupby(
            sorted(leaves, key=lambda leaf: leaf.commitment.agent_id),
            key=lambda leaf: leaf.commitment.agent_id,
        )
    }
    if not by_agent:
        return {}

    agent_ids = list(by_agent)
    sub_roots = [merkle_root([leaf.leaf_hash for leaf in by_agent[agent_id]]) for agent_id in agent_ids]
    batch_root = merkle_root(sub_roots)
    outcome = anchor_root(settings, batch_root)

    results: dict[str, AnchorResult] = {}
    for index, agent_id in enumerate(agent_ids):
        results[agent_id] = AnchorResult(
            submitted=outcome.submitted,
            detail=outcome.detail,
            tx_hash=outcome.tx_hash,
            root=sub_roots[index],
            batch_root=batch_root,
            proof=merkle_proof(sub_roots, index),
            anchorer=outcome.anchorer,
        )
    if outcome.submitted:
        logger.info(
            "anchored %d leaves for %d agents as batch root 0x%s under %s tx=%s",
            len(leaves), len(agent_ids), batch_root.hex(), outcome.anchorer, outcome.tx_hash,
        )
    else:
        logger.warning("could not anchor %d leaves for %d agents: %s -- recorded in logs only", len(leaves), len(agent_ids), outcome.detail)
    return results
