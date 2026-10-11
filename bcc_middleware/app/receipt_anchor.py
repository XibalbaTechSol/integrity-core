"""Anchor each closed receipt epoch's signed final checkpoint root on-chain (integrity-core B4, receipts epochs).

Why
---
Receipt epochs (SDK `GateReceiptWriter` rotation) bound memory but leave nothing linking epoch N to N+1 in the files, so
deleting the newest closed epoch, or the whole directory, was undetectable. Anchoring each closed epoch's final checkpoint
root on-chain gives a verifier an external fact to check the files against:
`verify_epoch_directory(..., anchored_roots=<this gate's roots from the chain>)` reports a root that matches no epoch.

What gets anchored
------------------
Only roots of CLOSED epochs, taken from each epoch's own SIGNED final checkpoint (`GateReceiptWriter.pending_anchors`),
sent through the same signer path and dedicated evidence `StateAnchor` that the Merkle-leaf anchoring uses
(`app/anchor.py::anchor_root`, which serializes on the signer lock). The open epoch is not anchored until it closes, so
deleting only the open epoch is undetectable for up to one epoch: stated, not hidden.

Failure posture (stated per module)
-----------------------------------
* **Best-effort, never a gate.** An unreachable chain, a missing evidence-anchor address or a missing signer leaves the epoch
  pending and is retried on the next sweep. It cannot block recording a receipt or a decision: this runs off the request path.
* **A sweep stops at the first failure** (oldest first), so an outage costs one attempt per sweep, not one per epoch.
* **An unverifiable closed epoch is CRITICAL, not retried silently.** If a closed epoch's final checkpoint no longer verifies
  (tampering, truncation), that is an integrity problem an operator must see; nothing is anchored for it.
* **Anchored on-chain but not recorded** (the ledger write failed after the transaction mined) is logged and the epoch is
  anchored AGAIN on the next sweep: a duplicate root on the evidence anchor is harmless to verification (the verifier checks
  membership of a root, not its count), and silently losing the fact that it was anchored would be worse.
* **No overlap.** The periodic loop and the admin endpoint share one non-blocking lock; a second caller gets `skipped`.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

from integrity_sdk.core import ReceiptSetupError, ReceiptWriteError

from app.anchor import anchor_root
from app.config import Settings
from app.gate_receipts import BccReceipts

logger = logging.getLogger(__name__)

_sweep_lock = threading.Lock()


@dataclass(frozen=True)
class AnchorSweep:
    attempted: int = 0
    anchored: int = 0
    failed: int = 0
    skipped: bool = False
    details: list[str] = field(default_factory=list)


def anchor_pending_epochs(settings: Settings, receipts: BccReceipts) -> AnchorSweep:
    """Anchor every pending closed epoch, oldest first, stopping at the first failure. Blocking; run off the event loop."""
    if not _sweep_lock.acquire(blocking=False):
        return AnchorSweep(skipped=True, details=["another anchor sweep is already running"])
    try:
        try:
            pending = receipts.pending_anchors()
        except ReceiptSetupError as exc:
            logger.critical("a CLOSED receipt epoch does not verify, so nothing can be anchored for it: %s", exc)
            return AnchorSweep(failed=1, details=[f"closed epoch does not verify: {exc}"])
        if not pending:
            return AnchorSweep()
        address = settings.contract_address(settings.receipt_anchor_target)
        if not address:
            detail = f"no '{settings.receipt_anchor_target}' address in {settings.deployments_file}"
            logger.warning("cannot anchor %d closed receipt epoch(s): %s; they stay pending", len(pending), detail)
            return AnchorSweep(attempted=len(pending), failed=len(pending), details=[detail])

        anchored = 0
        for closure in pending:
            result = anchor_root(settings, bytes.fromhex(closure.root[2:]), contract_address=address)
            if not (result.submitted and result.tx_hash):
                logger.warning("could not anchor receipt epoch %d (%s): %s; it stays pending", closure.epoch, closure.root, result.detail)
                return AnchorSweep(attempted=anchored + 1, anchored=anchored, failed=1,
                                   details=[f"epoch {closure.epoch}: {result.detail}"])
            try:
                receipts.mark_anchored(closure, result.tx_hash)
            except ReceiptWriteError as exc:
                logger.error("receipt epoch %d IS anchored on-chain (tx %s) but recording that failed (%s); it will be anchored again next sweep",
                             closure.epoch, result.tx_hash, exc)
                return AnchorSweep(attempted=anchored + 1, anchored=anchored, failed=1,
                                   details=[f"epoch {closure.epoch}: anchored (tx {result.tx_hash}) but not recorded: {exc}"])
            anchored += 1
            logger.info("anchored receipt epoch %d (%s) tx=%s", closure.epoch, closure.root, result.tx_hash)
        return AnchorSweep(attempted=anchored, anchored=anchored)
    finally:
        _sweep_lock.release()
