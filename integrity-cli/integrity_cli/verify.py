"""Independent offline verification for signed Integrity receipt bundles.

This module deliberately does not import ``integrity_sdk``.  The CLI and SDK
must agree on the receipt wire contract while remaining independently
installable, so the small verifier here mirrors the published C4 rules.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

import jcs
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from eth_utils import keccak

RECEIPT_VERSION = "integrity.receipt/1"
CHECKPOINT_VERSION = "integrity.checkpoint/1"
GENESIS_PREV_HASH = "0x" + "00" * 32
_RECEIPT_DOMAIN = b"integrity.receipt.v1\x00"
_CHECKPOINT_DOMAIN = b"integrity.checkpoint.v1\x00"
_HEX32 = re.compile(r"^0x[0-9a-f]{64}$")
_HMAC = re.compile(r"^hmac-sha256:[0-9a-f]{64}$")
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_RECEIPT_FIELDS = {
    "receipt_version", "log_id", "seq", "prev_hash", "timestamp", "agent_did",
    "device_id_hmac", "action_hmac", "event_class", "pack_hash", "decision",
    "reason_code", "mode", "controls", "checkpoint_reference", "signer_key", "signature",
}
_CHECKPOINT_FIELDS = {
    "checkpoint_version", "log_id", "tree_size", "root", "last_receipt_hash",
    "timestamp", "signer_key", "signature",
}


class VerifyError(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def is_hex32(value: Any) -> bool:
    return isinstance(value, str) and _HEX32.fullmatch(value) is not None


def _canonical(value: Any) -> bytes:
    return jcs.canonicalize(value)


def _body(document: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in document.items() if key != "signature"}


def _b58decode(value: str) -> bytes:
    if not value:
        return b""
    number = 0
    for char in value:
        try:
            number = number * 58 + _B58.index(char)
        except ValueError as exc:
            raise ValueError("invalid base58btc character") from exc
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return b"\x00" * (len(value) - len(value.lstrip("1"))) + raw


def _public_key(multibase: str) -> bytes:
    if not isinstance(multibase, str) or not multibase.startswith("z"):
        raise ValueError("expected z-prefixed base58btc Ed25519 key")
    raw = _b58decode(multibase[1:])
    if len(raw) != 34 or raw[:2] != b"\xed\x01":
        raise ValueError("expected an Ed25519 multicodec public key")
    return raw[2:]


def _trusted(signer: str, trusted: Sequence[str]) -> bool:
    try:
        wanted = _public_key(signer)
        return any(_public_key(candidate) == wanted for candidate in trusted)
    except ValueError:
        return False


def _verify_signature(document: Mapping[str, Any], domain: bytes, trusted: Sequence[str]) -> None:
    signer = document.get("signer_key")
    if not isinstance(signer, str) or not _trusted(signer, trusted):
        raise VerifyError("UNTRUSTED_SIGNER", "signed by a key that is not trusted")
    signature = document.get("signature")
    if not isinstance(signature, str):
        raise VerifyError("BAD_SIGNATURE", "signature is missing or not a string")
    try:
        signature_bytes = bytes.fromhex(signature.removeprefix("0x"))
        Ed25519PublicKey.from_public_bytes(_public_key(signer)).verify(
            signature_bytes, domain + _canonical(_body(document))
        )
    except (ValueError, TypeError, InvalidSignature) as exc:
        raise VerifyError("BAD_SIGNATURE", "signature does not verify") from exc


def _receipt_hash(receipt: Mapping[str, Any]) -> str:
    return "0x" + keccak(_canonical(dict(receipt))).hex()


def _leaf(receipt: Mapping[str, Any]) -> bytes:
    preimage = bytes.fromhex(_receipt_hash(receipt)[2:])
    domain = b"integrity.merkle.receipt.v2|"
    return keccak(keccak(domain + preimage))


def _hash_pair(left: bytes, right: bytes) -> bytes:
    return keccak(left + right) if left < right else keccak(right + left)


def _merkle_root(leaves: Sequence[bytes]) -> bytes:
    if not leaves:
        raise VerifyError("ROOT_MISMATCH", "cannot compute a root for an empty receipt prefix")
    level = list(leaves)
    while len(level) > 1:
        parents = [_hash_pair(level[i], level[i + 1]) for i in range(0, len(level) - 1, 2)]
        if len(level) % 2:
            parents.append(level[-1])
        level = parents
    return level[0]


def _verify_receipt(receipt: Mapping[str, Any], trusted: Sequence[str]) -> None:
    if not isinstance(receipt, Mapping) or set(receipt) != _RECEIPT_FIELDS:
        raise VerifyError("MALFORMED", "receipt fields do not match the receipt schema")
    body = _body(receipt)
    if body.get("receipt_version") != RECEIPT_VERSION:
        raise VerifyError("UNSUPPORTED_VERSION", "unsupported receipt_version")
    if not isinstance(body["seq"], int) or isinstance(body["seq"], bool) or body["seq"] < 0:
        raise VerifyError("MALFORMED", "seq must be a non-negative integer")
    if not isinstance(body["prev_hash"], str) or not _HEX32.fullmatch(body["prev_hash"]):
        raise VerifyError("MALFORMED", "prev_hash must be 0x + 64 lowercase hex")
    if not isinstance(body["timestamp"], str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", body["timestamp"]):
        raise VerifyError("MALFORMED", "timestamp must be UTC RFC 3339")
    for field in ("device_id_hmac", "action_hmac"):
        if not isinstance(body[field], str) or not _HMAC.fullmatch(body[field]):
            raise VerifyError("MALFORMED", f"{field} must be an hmac-sha256 identifier")
    for field in ("log_id", "agent_did", "event_class", "pack_hash", "reason_code", "signer_key"):
        if not isinstance(body[field], str) or not body[field]:
            raise VerifyError("MALFORMED", f"{field} must be a non-empty string")
    if body["decision"] not in {"permit", "deny", "log_only"} or body["mode"] not in {"enforce", "shadow"}:
        raise VerifyError("MALFORMED", "unknown decision or mode")
    if not isinstance(body["controls"], list) or not all(isinstance(c, str) and c for c in body["controls"]):
        raise VerifyError("MALFORMED", "controls must be a list of non-empty strings")
    reference = body["checkpoint_reference"]
    if reference is not None and (
        not isinstance(reference, dict) or set(reference) != {"tree_size", "root"}
        or not isinstance(reference["tree_size"], int) or not _HEX32.fullmatch(str(reference["root"]))
    ):
        raise VerifyError("MALFORMED", "checkpoint_reference is invalid")
    _verify_signature(receipt, _RECEIPT_DOMAIN, trusted)


def _verify_checkpoint(checkpoint: Mapping[str, Any], trusted: Sequence[str]) -> None:
    if not isinstance(checkpoint, Mapping) or set(checkpoint) != _CHECKPOINT_FIELDS:
        raise VerifyError("MALFORMED", "checkpoint fields do not match the checkpoint schema")
    if checkpoint.get("checkpoint_version") != CHECKPOINT_VERSION:
        raise VerifyError("UNSUPPORTED_VERSION", "unsupported checkpoint_version")
    if not isinstance(checkpoint["tree_size"], int) or isinstance(checkpoint["tree_size"], bool) or checkpoint["tree_size"] < 1:
        raise VerifyError("MALFORMED", "tree_size must be a positive integer")
    for field in ("root", "last_receipt_hash"):
        if not isinstance(checkpoint[field], str) or not _HEX32.fullmatch(checkpoint[field]):
            raise VerifyError("MALFORMED", f"{field} must be 0x + 64 lowercase hex")
    _verify_signature(checkpoint, _CHECKPOINT_DOMAIN, trusted)


def verify_bundle(receipts: Sequence[Mapping[str, Any]], trusted: Sequence[str], checkpoint: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return structured local verification results; raise on the first failure."""
    if not isinstance(receipts, Sequence) or isinstance(receipts, (str, bytes)):
        raise VerifyError("MALFORMED", "receipts must be a JSON array")
    log_id = receipts[0].get("log_id") if receipts else None
    previous = GENESIS_PREV_HASH
    for position, receipt in enumerate(receipts):
        _verify_receipt(receipt, trusted)
        if receipt["log_id"] != log_id:
            raise VerifyError("LOG_MISMATCH", f"receipt {position} belongs to another log")
        if receipt["seq"] != position:
            raise VerifyError("SEQ_GAP", f"expected seq {position}, found {receipt['seq']}")
        if receipt["prev_hash"] != previous:
            raise VerifyError("CHAIN_BROKEN", f"receipt {position} does not link to its predecessor")
        previous = _receipt_hash(receipt)
    if checkpoint is not None:
        _verify_checkpoint(checkpoint, trusted)
        if checkpoint["log_id"] != log_id:
            raise VerifyError("LOG_MISMATCH", "checkpoint belongs to another log")
        size = checkpoint["tree_size"]
        if len(receipts) < size:
            raise VerifyError("TRUNCATED", "checkpoint covers more receipts than supplied")
        if "0x" + _merkle_root([_leaf(r) for r in receipts[:size]]).hex() != checkpoint["root"]:
            raise VerifyError("ROOT_MISMATCH", "receipts do not reproduce checkpoint root")
        if _receipt_hash(receipts[size - 1]) != checkpoint["last_receipt_hash"]:
            raise VerifyError("ROOT_MISMATCH", "checkpoint last_receipt_hash does not match")
    return {"receipts": len(receipts), "log_id": log_id, "checkpoint": checkpoint is not None}


def verify_inclusion(receipt: Mapping[str, Any], proof: Sequence[str], checkpoint: Mapping[str, Any], trusted: Sequence[str]) -> None:
    if not isinstance(receipt, Mapping):
        raise VerifyError("MALFORMED", "proof receipt must be a JSON object")
    _verify_receipt(receipt, trusted)
    _verify_checkpoint(checkpoint, trusted)
    if receipt["log_id"] != checkpoint["log_id"] or receipt["seq"] >= checkpoint["tree_size"]:
        raise VerifyError("NOT_INCLUDED", "receipt is not covered by the checkpoint")
    try:
        computed = _leaf(receipt)
        for node in proof:
            sibling = bytes.fromhex(node.removeprefix("0x"))
            if len(sibling) != 32:
                raise ValueError
            computed = _hash_pair(computed, sibling)
    except (AttributeError, TypeError, ValueError) as exc:
        raise VerifyError("MALFORMED", "proof nodes must be 32-byte hex strings") from exc
    if computed.hex() != checkpoint["root"][2:]:
        raise VerifyError("NOT_INCLUDED", "proof does not connect receipt to checkpoint root")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise VerifyError("MALFORMED", f"cannot read JSON input {path}: {exc}") from exc
