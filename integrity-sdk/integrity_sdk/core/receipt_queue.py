"""Durable local queue for signed decision receipts.

The queue is transport-neutral: a hosted service, Oracle, or anchorer can submit
the pending signed documents later. Acknowledgement is explicit and only removes
receipts from the pending view; the signed log remains on disk for audit and
offline verification.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from ..did import Keypair
from .receipts import ReceiptLog, receipt_hash


class ReceiptQueueError(ValueError):
    """The durable queue is malformed or an acknowledgement is invalid."""


class ReceiptQueue:
    """A signed receipt log with durable, retryable submission state."""

    def __init__(self, signer: Keypair, log_id: str, path: str | Path):
        self.path = Path(path)
        self._signer = signer
        if self.path.exists():
            document = self._read()
            if document.get("log_id") != log_id:
                raise ReceiptQueueError("receipt queue log_id does not match the requested log")
            try:
                self.log = ReceiptLog.resume(
                    signer,
                    log_id,
                    document["receipts"],
                    document["checkpoints"],
                )
            except Exception as exc:
                raise ReceiptQueueError(f"receipt queue failed offline verification: {exc}") from exc
            submitted = document.get("submitted_hashes", [])
            if not isinstance(submitted, list) or not all(isinstance(item, str) for item in submitted):
                raise ReceiptQueueError("submitted_hashes must be a list of receipt hashes")
            self._submitted_hashes = set(submitted)
            self._validate_submitted()
        else:
            self.log = ReceiptLog(signer, log_id)
            self._submitted_hashes: set[str] = set()

    @property
    def log_id(self) -> str:
        return self.log.log_id

    def _read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReceiptQueueError(f"unable to read receipt queue: {exc}") from exc
        if not isinstance(value, dict) or not isinstance(value.get("receipts"), list) or not isinstance(value.get("checkpoints"), list):
            raise ReceiptQueueError("receipt queue document is malformed")
        return value

    def _validate_submitted(self) -> None:
        known = {receipt_hash(receipt) for receipt in self.log.receipts}
        if not self._submitted_hashes <= known:
            raise ReceiptQueueError("submitted_hashes contains an unknown receipt")

    def _write(self) -> None:
        document = {
            "queue_version": "integrity.receipt-queue/1",
            "log_id": self.log_id,
            "receipts": self.log.receipts,
            "checkpoints": self.log.checkpoints,
            "submitted_hashes": sorted(self._submitted_hashes),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(document, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    def append(self, **kwargs: Any) -> dict[str, Any]:
        receipt = self.log.append(**kwargs)
        self._write()
        return receipt

    def checkpoint(self, **kwargs: Any) -> dict[str, Any]:
        checkpoint = self.log.checkpoint(**kwargs)
        self._write()
        return checkpoint

    def pending(self) -> list[dict[str, Any]]:
        return [receipt for receipt in self.log.receipts if receipt_hash(receipt) not in self._submitted_hashes]

    def acknowledge(self, hashes: Iterable[str]) -> None:
        requested = set(hashes)
        known = {receipt_hash(receipt) for receipt in self.log.receipts}
        if not requested <= known:
            raise ReceiptQueueError("cannot acknowledge an unknown receipt")
        self._submitted_hashes.update(requested)
        self._write()

    def submit(self, sender: Callable[[Sequence[Mapping[str, Any]]], Iterable[str]]) -> list[str]:
        """Send pending receipts through a caller-owned transport and acknowledge returned hashes."""
        pending = self.pending()
        if not pending:
            return []
        accepted = list(sender(pending))
        pending_hashes = {receipt_hash(receipt) for receipt in pending}
        if not set(accepted) <= pending_hashes:
            raise ReceiptQueueError("sender acknowledged a receipt that was not pending")
        self.acknowledge(accepted)
        return accepted
