"""Agent identity over HTTP: a JSON body signed with the agent's Ed25519 key.

This is the oracle's existing wire format for signed submissions (telemetry
ingest, registration): the body carries ``agent_id`` and a monotonic
``nonce``, and ``signature = "0x" + hex(Ed25519(JCS(body without signature)))``.
The oracle derives the public key from the DID it already knows and rejects a
reused nonce, so the signature authenticates the agent and the nonce blocks
replay. Centralized here so every client signs the same bytes the oracle
verifies, instead of each call site re-deriving them.

The format predates the domain-separated signatures used by packs and
receipts, and is kept byte-compatible with the deployed oracle. A future
version bump should add a domain prefix on both sides at once.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

from ..did import Keypair, verify_signature
from .jcs import canonical_bytes

SIGNATURE_FIELD = "signature"


def sign_body(keypair: Keypair, body: Mapping[str, Any]) -> Dict[str, Any]:
    """Return `body` plus its ``signature``. `body` must not already carry one."""
    if SIGNATURE_FIELD in body:
        raise ValueError("body already carries a signature field")
    return {**body, SIGNATURE_FIELD: "0x" + keypair.sign(canonical_bytes(dict(body))).hex()}


def verify_body(public_key: bytes, payload: Mapping[str, Any]) -> bool:
    """Check a signed body the way the oracle does; False on any malformation."""
    signature = payload.get(SIGNATURE_FIELD)
    if not isinstance(signature, str) or not signature.startswith("0x"):
        return False
    try:
        raw = bytes.fromhex(signature[2:])
    except ValueError:
        return False
    body = {key: value for key, value in payload.items() if key != SIGNATURE_FIELD}
    return len(raw) == 64 and verify_signature(public_key, canonical_bytes(body), raw)
