"""Stable offline verification facade for packs and evidence."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .packs import LoadedPack, PackError, load_pack
from .receipts import ReceiptError, verify_inclusion, verify_log, verify_receipt
from .decision_trace import DecisionTrace, DecisionTraceEvidence, DecisionTraceError, verify_trace_evidence


@dataclass(frozen=True)
class VerificationResult:
    """Machine-readable result with stable failure codes and no network dependency."""

    artifact: str
    valid: bool
    code: str
    detail: str
    identifier: str | None = None


def verify_pack_offline(
    pack_dir: str | Path,
    *,
    trusted_signers: Collection[str],
    expected_pack_hash: str | None = None,
) -> tuple[VerificationResult, LoadedPack | None]:
    try:
        pack = load_pack(pack_dir, trusted_signers=trusted_signers, expected_pack_hash=expected_pack_hash)
    except PackError as exc:
        return VerificationResult("pack", False, exc.code, str(exc)), None
    return VerificationResult("pack", True, "OK", "signed pack verified", pack.pack_hash), pack


def verify_receipt_log_offline(
    receipts: Sequence[Mapping[str, Any]],
    *,
    trusted_signers: Collection[str],
    checkpoint: Mapping[str, Any] | None = None,
) -> VerificationResult:
    try:
        verify_log(receipts, trusted_signers=trusted_signers, checkpoint=checkpoint)
    except ReceiptError as exc:
        return VerificationResult("receipt_log", False, exc.code, str(exc))
    log_id = str(receipts[0]["log_id"]) if receipts else None
    return VerificationResult("receipt_log", True, "OK", "receipt log verified offline", log_id)


def verify_receipt_inclusion_offline(
    receipt: Mapping[str, Any],
    proof: Sequence[str],
    checkpoint: Mapping[str, Any],
    *,
    trusted_signers: Collection[str],
) -> VerificationResult:
    try:
        verify_inclusion(receipt, proof, checkpoint, trusted_signers=trusted_signers)
    except ReceiptError as exc:
        return VerificationResult("receipt_inclusion", False, exc.code, str(exc))
    return VerificationResult("receipt_inclusion", True, "OK", "receipt inclusion verified offline", str(receipt["log_id"]))


def verify_decision_trace_offline(
    trace: DecisionTrace,
    evidence: DecisionTraceEvidence,
    *,
    receipt: Mapping[str, Any] | None = None,
    trusted_signers: Collection[str] = (),
) -> VerificationResult:
    """Verify trace links/root and, when supplied, the linked receipt without a network call."""
    try:
        if receipt is not None:
            verify_receipt(receipt, trusted_signers=trusted_signers)
        if not verify_trace_evidence(trace, evidence, receipt):
            raise DecisionTraceError("trace root, parent links, event count or receipt link mismatched")
    except (DecisionTraceError, ReceiptError, ValueError) as exc:
        return VerificationResult("decision_trace", False, "INVALID", str(exc), evidence.trace_id)
    return VerificationResult("decision_trace", True, "OK", "DecisionTrace and linked receipt verified offline", evidence.trace_id)
