"""Anchors ReceiptQueue checkpoints to the shared `ActionAnchor` singleton
(docs/EXECUTION_PLAN.md B4; v2 graph deletion slice D1, owner question 8a).

Connector-only module (`web3`/`eth_account`, same as `chain.py`): never imported from
`integrity_sdk.core` or any core-safe module.

`ActionAnchor` keys every root on `msg.sender`, so evidence anchors under the address of the
signer that submits it: one slot per anchoring service, with per-agent sub-roots as leaves.
Anchoring is a direct signed call from that EOA -- unlike an agent's vault root, which
`chain.anchor_vault_root` routes through the actor's `SovereignAgent.execute` so it lands
under the actor.

`ActionAnchor` stores only the latest root per anchorer. An older checkpoint is proved
anchored by its `RootAnchored(anchorer, epoch, root)` event; its leaf by the local Merkle
check (`core.merkle.verify_leaf`, the same sorted-pair convention `ActionAnchor.verifyLeaf`
uses on-chain).

Anchoring is best-effort evidence, not an authorization gate, mirroring
`bcc_middleware/app/anchor.py`'s documented posture: a failed submission is raised to the
caller (so `core.receipt_queue.ReceiptQueue.submit` leaves the batch pending for the next
retry) but never corrupts queue state or blocks whatever already-decided action the receipt
records.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Mapping, Sequence

from .chain import _call_with_retry, _contract, _send_signed  # intra-package reuse; see module docstring

if TYPE_CHECKING:
    from eth_account.signers.local import LocalAccount
    from web3 import Web3

    from .core.receipt_queue import ReceiptQueue


class EvidenceAnchorError(RuntimeError):
    """An anchor submission or verification could not be completed."""


def anchor_checkpoint_root(
    w3: "Web3",
    account: "LocalAccount",
    contract_address: str,
    chain_id: int,
    root: bytes,
) -> str:
    """Submits one signed `anchorRoot(root)` call. Returns the tx hash hex string.

    Raises `EvidenceAnchorError` on any submission failure (RPC unreachable, tx
    reverted) -- deliberately, so a caller driving `ReceiptQueue.submit` never
    acknowledges a checkpoint that was not actually anchored.
    """
    from web3.exceptions import Web3Exception

    contract = _contract(w3, "ActionAnchor", address=contract_address)
    try:
        receipt, tx_hash = _send_signed(
            w3, account,
            lambda nonce: contract.functions.anchorRoot(root).build_transaction(
                {"from": account.address, "nonce": nonce, "chainId": chain_id}
            ),
            action="anchor_checkpoint_root",
        )
    except Web3Exception as exc:
        raise EvidenceAnchorError(f"anchorRoot(0x{root.hex()}) submission failed: {exc}") from exc
    if receipt.status != 1:
        raise EvidenceAnchorError(f"anchorRoot(0x{root.hex()}) transaction reverted (status={receipt.status})")
    return tx_hash.hex()


def root_was_anchored(w3: "Web3", contract_address: str, anchorer: str, root: bytes) -> bool:
    """True when `anchorer` anchored `root` on this `ActionAnchor` at any epoch, read from the
    contract's own `RootAnchored(agent indexed, epoch, root)` log."""
    from web3 import Web3

    contract = _contract(w3, "ActionAnchor", address=contract_address)
    if bytes(_call_with_retry(contract.functions.latestRoot(Web3.to_checksum_address(anchorer)).call)) == bytes(root):
        return True
    events = contract.events.RootAnchored.get_logs(
        from_block=0, argument_filters={"agent": Web3.to_checksum_address(anchorer)}
    )
    return any(bytes(e["args"]["root"]) == bytes(root) for e in events)


def verify_root_anchored(
    w3: "Web3",
    contract_address: str,
    anchorer: str,
    root: bytes,
    leaf: bytes,
    proof: Sequence[bytes],
) -> bool:
    """True only if `anchorer` genuinely anchored `root` on this contract AND `leaf` is
    included under it."""
    from .core.merkle import verify_leaf

    if not verify_leaf(root, leaf, list(proof)):
        return False
    return root_was_anchored(w3, contract_address, anchorer, root)


def anchor_pending_receipts(
    queue: "ReceiptQueue",
    w3: "Web3",
    account: "LocalAccount",
    contract_address: str,
    chain_id: int,
) -> list[str]:
    """Checkpoints and anchors a `ReceiptQueue`'s pending receipts; returns the
    accepted receipt hashes (same contract as `ReceiptQueue.submit`'s `sender`).

    This is the "queued receipts anchor after recovery" half of B4: nothing here
    retries on a schedule -- a caller (a CLI command, a background loop) re-invokes
    this after whatever outage is over, and `ReceiptQueue`'s own durable
    `submitted_hashes` tracking means receipts already anchored in an earlier call
    are never re-submitted, while a failure here (this function raises, via
    `anchor_checkpoint_root`) leaves every receipt in this batch still pending for
    the next attempt -- `ReceiptQueue.submit` never acknowledges on an exception.
    """
    def _sender(pending: Sequence[Mapping[str, object]]) -> list[str]:
        from .core.receipts import receipt_hash

        checkpoint = queue.checkpoint()
        root = bytes.fromhex(checkpoint["root"][2:])
        anchor_checkpoint_root(w3, account, contract_address, chain_id, root)
        covered = queue.log.receipts[: checkpoint["tree_size"]]
        covered_hashes = {receipt_hash(r) for r in covered}
        return [receipt_hash(r) for r in pending if receipt_hash(r) in covered_hashes]

    return queue.submit(_sender)
