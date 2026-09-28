"""Decision receipts (SDK contract C4): signed, chained, checkpointed, verifiable offline.

A gate (Shield on a device, BCC in the middleware) writes one receipt per
decision into an append-only log it owns:

- **Signed** with the gate's or device's Ed25519 key, over
  ``b"integrity.receipt.v1\\x00" || JCS(body)``. The signature is the
  authenticity mechanism.
- **Chained**: ``seq`` counts from 0 and ``prev_hash`` is the keccak-256 of the
  previous signed receipt, so deleting, reordering or inserting a receipt
  breaks the chain.
- **Checkpointed**: a signed checkpoint commits to the Merkle root over the
  first ``tree_size`` receipts and the hash of the last one. A checkpoint is
  what gets anchored (B4). Holding it, a verifier detects *tail truncation*:
  a log that stops before ``tree_size`` is refused, which a bare hash chain
  cannot show. Each receipt names the latest checkpoint that preceded it.
- **Private by construction**: identifiers that could reveal a person or a
  machine (device, action) are HMAC-SHA256 values under an organization-held
  key (`hmac_identifier`). HMAC hides them from anyone without the key; it is
  not what makes the receipt authentic. Content never appears in a receipt.

Merkle leaves are ``leaf_hash("receipt", receipt_hash)`` in the protocol's one
Merkle convention (`core.merkle`), so a checkpoint root can be anchored on
`StateAnchor` and inclusion checked with its `verifyLeaf`.

Verification raises `ReceiptError` with a stable ``code``: MALFORMED,
UNSUPPORTED_VERSION, BAD_SIGNATURE, UNTRUSTED_SIGNER, LOG_MISMATCH, SEQ_GAP,
CHAIN_BROKEN, TRUNCATED, ROOT_MISMATCH, NOT_INCLUDED.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import time
from typing import Any, Collection, Dict, List, Mapping, Optional, Sequence

from ..did import Keypair, public_key_multibase
from .decision import DECISIONS, MODES
from .jcs import canonical_bytes
from .merkle import keccak256, leaf_hash, merkle_proof, merkle_root, verify_leaf
from .signing import signer_matches, verify_multibase_signature

RECEIPT_VERSION = "integrity.receipt/1"
CHECKPOINT_VERSION = "integrity.checkpoint/1"
SUPPORTED_RECEIPT_VERSIONS = frozenset({RECEIPT_VERSION})
GENESIS_PREV_HASH = "0x" + "00" * 32
_RECEIPT_DOMAIN = b"integrity.receipt.v1\x00"
_CHECKPOINT_DOMAIN = b"integrity.checkpoint.v1\x00"
_HMAC_PREFIX = "hmac-sha256:"
_MIN_HMAC_KEY_BYTES = 32

_HEX32_RE = re.compile(r"^0x[0-9a-f]{64}$")
_HMAC_RE = re.compile(r"^hmac-sha256:[0-9a-f]{64}$")
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_RECEIPT_FIELDS = frozenset({
    "receipt_version", "log_id", "seq", "prev_hash", "timestamp", "agent_did", "device_id_hmac",
    "action_hmac", "event_class", "pack_hash", "decision", "reason_code", "mode", "controls",
    "checkpoint_reference", "signer_key", "signature",
})
_CHECKPOINT_FIELDS = frozenset({
    "checkpoint_version", "log_id", "tree_size", "root", "last_receipt_hash", "timestamp", "signer_key",
    "signature",
})


class ReceiptError(Exception):
    """A receipt, log or checkpoint failed verification."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def hmac_identifier(key: bytes, domain: str, value: str | bytes) -> str:
    """Keyed, domain-separated identifier: ``hmac-sha256:<hex>``.

    Plain SHA-256 is not enough for low-entropy identifiers (a device serial, a
    patient MRN): anyone can hash every candidate. HMAC under an
    organization-held key cannot be brute-forced without the key. The domain
    (e.g. ``"device"``, ``"action"``) keeps the same value from correlating
    across fields.
    """
    if len(key) < _MIN_HMAC_KEY_BYTES:
        raise ValueError(f"HMAC key must be at least {_MIN_HMAC_KEY_BYTES} bytes")
    if not domain or "\x00" in domain:
        raise ValueError("HMAC domain must be a non-empty string without NUL")
    data = value.encode("utf-8") if isinstance(value, str) else bytes(value)
    return _HMAC_PREFIX + hmac.new(key, domain.encode("utf-8") + b"\x00" + data, hashlib.sha256).hexdigest()


def receipt_hash(receipt: Mapping[str, Any]) -> str:
    """keccak-256 of the signed receipt (body and signature): the chain link and Merkle input."""
    return "0x" + keccak256(canonical_bytes(dict(receipt))).hex()


def receipt_leaf(receipt: Mapping[str, Any]) -> bytes:
    return leaf_hash("receipt", bytes.fromhex(receipt_hash(receipt)[2:]))


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _body(document: Mapping[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in document.items() if key != "signature"}


class ReceiptLog:
    """An append-only receipt log for one gate instance, signed with that gate's key.

    Holds receipts in memory. A gate persists `receipts` (e.g. JSONL) and
    re-creates the log with `ReceiptLog.resume` after a restart.
    """

    def __init__(self, signer: Keypair, log_id: str):
        if not log_id or not isinstance(log_id, str):
            raise ValueError("log_id must be a non-empty string")
        self._signer = signer
        self._signer_key = public_key_multibase(signer.public_bytes())
        self.log_id = log_id
        self.receipts: List[Dict[str, Any]] = []
        self.checkpoints: List[Dict[str, Any]] = []

    @classmethod
    def resume(
        cls,
        signer: Keypair,
        log_id: str,
        receipts: Sequence[Mapping[str, Any]],
        checkpoints: Sequence[Mapping[str, Any]] = (),
    ) -> "ReceiptLog":
        """Re-open a persisted log after verifying it end to end with this signer's key."""
        log = cls(signer, log_id)
        trusted = [log._signer_key]
        latest = checkpoints[-1] if checkpoints else None
        verify_log(receipts, trusted_signers=trusted, checkpoint=latest)
        for checkpoint in checkpoints:
            verify_checkpoint(checkpoint, trusted_signers=trusted)
        log.receipts = [dict(r) for r in receipts]
        log.checkpoints = [dict(c) for c in checkpoints]
        return log

    @property
    def signer_key(self) -> str:
        return self._signer_key

    def _sign(self, domain: bytes, body: Dict[str, Any]) -> Dict[str, Any]:
        signature = self._signer.sign(domain + canonical_bytes(body))
        return {**body, "signature": signature.hex()}

    def append(
        self,
        *,
        agent_did: str,
        device_id_hmac: str,
        action_hmac: str,
        event_class: str,
        pack_hash: str,
        decision: str,
        reason_code: str,
        mode: str,
        controls: Sequence[str] = (),
        timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Append and return one signed receipt."""
        latest = self.checkpoints[-1] if self.checkpoints else None
        body = {
            "receipt_version": RECEIPT_VERSION,
            "log_id": self.log_id,
            "seq": len(self.receipts),
            "prev_hash": receipt_hash(self.receipts[-1]) if self.receipts else GENESIS_PREV_HASH,
            "timestamp": timestamp or _utc_now(),
            "agent_did": agent_did,
            "device_id_hmac": device_id_hmac,
            "action_hmac": action_hmac,
            "event_class": event_class,
            "pack_hash": pack_hash,
            "decision": decision,
            "reason_code": reason_code,
            "mode": mode,
            "controls": list(controls),
            "checkpoint_reference": (
                {"tree_size": latest["tree_size"], "root": latest["root"]} if latest is not None else None
            ),
            "signer_key": self._signer_key,
        }
        _check_receipt_body(body)
        receipt = self._sign(_RECEIPT_DOMAIN, body)
        self.receipts.append(receipt)
        return receipt

    def checkpoint(self, *, timestamp: Optional[str] = None) -> Dict[str, Any]:
        """Sign and return a checkpoint over every receipt so far (the value to anchor)."""
        if not self.receipts:
            raise ValueError("cannot checkpoint an empty log")
        body = {
            "checkpoint_version": CHECKPOINT_VERSION,
            "log_id": self.log_id,
            "tree_size": len(self.receipts),
            "root": "0x" + merkle_root([receipt_leaf(r) for r in self.receipts]).hex(),
            "last_receipt_hash": receipt_hash(self.receipts[-1]),
            "timestamp": timestamp or _utc_now(),
            "signer_key": self._signer_key,
        }
        checkpoint = self._sign(_CHECKPOINT_DOMAIN, body)
        self.checkpoints.append(checkpoint)
        return checkpoint

    def inclusion_proof(self, seq: int, checkpoint: Mapping[str, Any]) -> List[str]:
        """Proof that receipt `seq` is under `checkpoint`'s root."""
        size = checkpoint["tree_size"]
        if not 0 <= seq < size <= len(self.receipts):
            raise IndexError(f"receipt {seq} is not covered by a checkpoint of size {size}")
        leaves = [receipt_leaf(r) for r in self.receipts[:size]]
        return ["0x" + node.hex() for node in merkle_proof(leaves, seq)]


# ------------------------------------------------------------------ verification ---


def _check_receipt_body(body: Mapping[str, Any]) -> None:
    """Structural validation shared by `append` and verification."""
    if body.get("receipt_version") not in SUPPORTED_RECEIPT_VERSIONS:
        raise ReceiptError("UNSUPPORTED_VERSION", f"unsupported receipt_version {body.get('receipt_version')!r}")
    if set(body) != _RECEIPT_FIELDS - {"signature"}:
        raise ReceiptError("MALFORMED", "receipt fields do not match the receipt schema")
    if not isinstance(body["seq"], int) or isinstance(body["seq"], bool) or body["seq"] < 0:
        raise ReceiptError("MALFORMED", "seq must be a non-negative integer")
    if not isinstance(body["prev_hash"], str) or not _HEX32_RE.fullmatch(body["prev_hash"]):
        raise ReceiptError("MALFORMED", "prev_hash must be 0x + 64 lowercase hex")
    if not isinstance(body["timestamp"], str) or not _TIMESTAMP_RE.fullmatch(body["timestamp"]):
        raise ReceiptError("MALFORMED", "timestamp must be UTC RFC 3339 (YYYY-MM-DDTHH:MM:SSZ)")
    for field in ("device_id_hmac", "action_hmac"):
        if not isinstance(body[field], str) or not _HMAC_RE.fullmatch(body[field]):
            raise ReceiptError("MALFORMED", f"{field} must be an hmac-sha256 identifier")
    for field in ("log_id", "agent_did", "event_class", "pack_hash", "reason_code", "signer_key"):
        if not isinstance(body[field], str) or not body[field]:
            raise ReceiptError("MALFORMED", f"{field} must be a non-empty string")
    if body["decision"] not in DECISIONS:
        raise ReceiptError("MALFORMED", f"unknown decision {body['decision']!r}")
    if body["mode"] not in MODES:
        raise ReceiptError("MALFORMED", f"unknown mode {body['mode']!r}")
    if not isinstance(body["controls"], list) or not all(isinstance(c, str) and c for c in body["controls"]):
        raise ReceiptError("MALFORMED", "controls must be a list of non-empty strings")
    reference = body["checkpoint_reference"]
    if reference is not None and (
        not isinstance(reference, dict)
        or set(reference) != {"tree_size", "root"}
        or not isinstance(reference["tree_size"], int)
        or not _HEX32_RE.fullmatch(str(reference["root"]))
    ):
        raise ReceiptError("MALFORMED", "checkpoint_reference must be null or {tree_size, root}")


def _check_signature(document: Mapping[str, Any], domain: bytes, trusted_signers: Collection[str]) -> None:
    signer_key = document.get("signer_key")
    if not isinstance(signer_key, str) or not signer_matches(signer_key, trusted_signers):
        raise ReceiptError("UNTRUSTED_SIGNER", "signed by a key that is not trusted")
    signature = document.get("signature")
    if not isinstance(signature, str) or not verify_multibase_signature(
        signer_key, domain + canonical_bytes(_body(document)), signature
    ):
        raise ReceiptError("BAD_SIGNATURE", "signature does not verify")


def verify_receipt(receipt: Mapping[str, Any], *, trusted_signers: Collection[str]) -> None:
    """Verify one receipt's structure and signature (not its position in a log)."""
    if not isinstance(receipt, Mapping):
        raise ReceiptError("MALFORMED", "a receipt must be a JSON object")
    _check_receipt_body(_body(receipt))
    _check_signature(receipt, _RECEIPT_DOMAIN, trusted_signers)


def verify_checkpoint(checkpoint: Mapping[str, Any], *, trusted_signers: Collection[str]) -> None:
    """Verify a checkpoint's structure and signature."""
    if not isinstance(checkpoint, Mapping) or set(checkpoint) != _CHECKPOINT_FIELDS:
        raise ReceiptError("MALFORMED", "checkpoint fields do not match the checkpoint schema")
    if checkpoint.get("checkpoint_version") != CHECKPOINT_VERSION:
        raise ReceiptError("UNSUPPORTED_VERSION", "unsupported checkpoint_version")
    size = checkpoint["tree_size"]
    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        raise ReceiptError("MALFORMED", "tree_size must be a positive integer")
    for field in ("root", "last_receipt_hash"):
        if not isinstance(checkpoint[field], str) or not _HEX32_RE.fullmatch(checkpoint[field]):
            raise ReceiptError("MALFORMED", f"{field} must be 0x + 64 lowercase hex")
    _check_signature(checkpoint, _CHECKPOINT_DOMAIN, trusted_signers)


def verify_log(
    receipts: Sequence[Mapping[str, Any]],
    *,
    trusted_signers: Collection[str],
    checkpoint: Optional[Mapping[str, Any]] = None,
) -> None:
    """Verify a whole log: every signature, contiguous seq from 0, an unbroken chain.

    With a `checkpoint`, also require the log to reach at least its
    `tree_size` (a shorter log was truncated) and the root and last-receipt
    hash over that prefix to match exactly.
    """
    if not receipts:
        if checkpoint is not None:
            raise ReceiptError("TRUNCATED", "the log is empty but a checkpoint covers receipts")
        return
    log_id = receipts[0].get("log_id")
    previous = GENESIS_PREV_HASH
    for position, receipt in enumerate(receipts):
        verify_receipt(receipt, trusted_signers=trusted_signers)
        if receipt["log_id"] != log_id:
            raise ReceiptError("LOG_MISMATCH", f"receipt {position} belongs to log {receipt['log_id']!r}")
        if receipt["seq"] != position:
            raise ReceiptError("SEQ_GAP", f"expected seq {position}, found {receipt['seq']}")
        if receipt["prev_hash"] != previous:
            raise ReceiptError("CHAIN_BROKEN", f"receipt {position} does not link to its predecessor")
        previous = receipt_hash(receipt)

    if checkpoint is None:
        return
    verify_checkpoint(checkpoint, trusted_signers=trusted_signers)
    if checkpoint["log_id"] != log_id:
        raise ReceiptError("LOG_MISMATCH", "the checkpoint belongs to a different log")
    size = checkpoint["tree_size"]
    if len(receipts) < size:
        raise ReceiptError("TRUNCATED", f"the checkpoint covers {size} receipts but only {len(receipts)} are present")
    root = "0x" + merkle_root([receipt_leaf(r) for r in receipts[:size]]).hex()
    if root != checkpoint["root"]:
        raise ReceiptError("ROOT_MISMATCH", "the receipts do not reproduce the checkpoint root")
    if receipt_hash(receipts[size - 1]) != checkpoint["last_receipt_hash"]:
        raise ReceiptError("ROOT_MISMATCH", "the checkpoint's last receipt is not the log's receipt at tree_size")


def verify_inclusion(
    receipt: Mapping[str, Any],
    proof: Sequence[str],
    checkpoint: Mapping[str, Any],
    *,
    trusted_signers: Collection[str],
) -> None:
    """Verify one receipt against a checkpoint without the rest of the log (offline verify)."""
    verify_receipt(receipt, trusted_signers=trusted_signers)
    verify_checkpoint(checkpoint, trusted_signers=trusted_signers)
    if receipt["log_id"] != checkpoint["log_id"]:
        raise ReceiptError("LOG_MISMATCH", "the receipt and checkpoint belong to different logs")
    if receipt["seq"] >= checkpoint["tree_size"]:
        raise ReceiptError("NOT_INCLUDED", "the receipt is newer than the checkpoint")
    try:
        siblings = [bytes.fromhex(node.removeprefix("0x")) for node in proof]
    except (AttributeError, ValueError) as exc:
        raise ReceiptError("MALFORMED", "proof nodes must be hex strings") from exc
    if not verify_leaf(bytes.fromhex(checkpoint["root"][2:]), receipt_leaf(receipt), siblings):
        raise ReceiptError("NOT_INCLUDED", "the proof does not connect the receipt to the checkpoint root")
