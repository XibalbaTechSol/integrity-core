"""Anchors ReceiptQueue checkpoints to the dedicated protocol evidence `StateAnchor`
(docs/EXECUTION_PLAN.md B4; `contracts/script/DeployProtocolEvidenceAnchor.s.sol`).

Connector-only module (`web3`/`eth_account`, same as `chain.py`): never imported from
`integrity_sdk.core` or any core-safe module.

This contract's admin is a raw EOA (the protocol operator), not a `SovereignAgent`
contract, unlike a per-agent memory `StateAnchor` -- so anchoring here is a direct
signed call, never routed through `SovereignAgent.execute` the way `chain.py`'s
`anchor_vault_root`/`anchor_genesis_root` are. Anchoring is best-effort evidence, not
an authorization gate, mirroring `bcc_middleware/app/anchor.py`'s documented posture:
a failed submission is raised to the caller (so `core.receipt_queue.ReceiptQueue.submit`
leaves the batch pending for the next retry) but never corrupts queue state or blocks
whatever already-decided action the receipt records.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Mapping, Sequence

from .chain import _contract, _send_signed  # intra-package reuse; see module docstring

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

    contract = _contract(w3, "StateAnchor", address=contract_address)
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


def verify_root_anchored(
    w3: "Web3",
    contract_address: str,
    root: bytes,
    leaf: bytes,
    proof: Sequence[bytes],
) -> bool:
    """Read-only `StateAnchor.verifyLeaf(root, leaf, proof)` -- true only if `root`
    was genuinely anchored by this contract AND `leaf` is included under it."""
    contract = _contract(w3, "StateAnchor", address=contract_address)
    return bool(contract.functions.verifyLeaf(root, leaf, list(proof)).call())


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
