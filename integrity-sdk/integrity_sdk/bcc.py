"""
Behavioral Commitment Chain (BCC) commitment construction — docs/INTERFACE_CONTRACT.md §4.2.

A BCC commitment is the intent-lock object an agent produces *before* taking
an action: "I, agent X, am about to do intent Y, whose payload hashes to Z,
and I've signed this whole statement with my DID key." `bcc_middleware`
(a sibling package, built independently and in parallel) receives this exact
JSON shape at `POST /v1/bcc/intercept` and must be able to reconstruct the
same hash and verify the same signature from the raw JSON alone — so the
canonicalization rules below are not a style preference, they're part of the
wire protocol.

Canonical JSON encoding (used for BOTH the intent-payload hash and the
commitment signature):
  - `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)`
  - Keys sorted lexicographically (byte-wise ASCII order) — this is what
    `sort_keys=True` does in Python and what most other languages' "sort
    object keys" helpers do too, so it's a safe cross-language convention.
  - No inserted whitespace (`separators=(",", ":")`).
  - `ensure_ascii=True` (json's default): non-ASCII characters are escaped as
    `\\uXXXX` rather than emitted as raw UTF-8 bytes. This is REQUIRED for
    byte-for-byte reproducibility — a Rust or Go implementation using a
    different default here would produce a different byte string and a
    different hash/signature, even though the *logical* JSON is identical.
  - Integers only for `nonce` and `timestamp` — never floats. Python's `json`
    renders `1719000000000` and `1719000000000.0` differently, and other
    languages differ on trailing `.0`, so floats here would break
    cross-implementation hash agreement.

Hash function: intended_state_hash is fixed by the contract to be SHA-256
of the canonical intent payload (not a policy choice made here).
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .did import Keypair, public_key_multibase, verify_signature


def canonical_json_bytes(obj: Any) -> bytes:
    """The one and only canonicalization used across the SDK for anything
    that gets hashed or signed. See module docstring for why each flag matters."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def hash_intent_payload(intent_payload: Dict[str, Any]) -> str:
    """SHA-256 of the canonical intent payload, as `0x`-prefixed hex —
    this becomes `intended_state_hash` (§4.2)."""
    digest = hashlib.sha256(canonical_json_bytes(intent_payload)).hexdigest()
    return "0x" + digest


class NonceStore:
    """
    Persists a monotonically increasing per-agent nonce to disk so it
    survives process restarts. §4.2 requires the BCC `nonce` to be
    "monotonic per-agent" — a nonce that resets to 0 on every restart would
    let a compromised or buggy client replay an old commitment's nonce,
    which is exactly what monotonicity is meant to prevent.

    This is intentionally simple (a single JSON counter file behind a
    process-local lock) and is NOT safe for multiple processes sharing one
    agent identity concurrently — that would need a real lock file or a
    server-side nonce authority (bcc_middleware could serve this role).
    Documented here rather than silently assumed away.
    """

    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def next(self) -> int:
        with self._lock:
            current = 0
            if self._path.exists():
                try:
                    current = int(self._path.read_text().strip() or "0")
                except ValueError:
                    current = 0
            nxt = current + 1
            self._path.write_text(str(nxt))
            return nxt


def build_bcc_commitment(
    *,
    agent_id: str,
    intent_type: str,
    intent_payload: Dict[str, Any],
    nonce: int,
    keypair: Keypair,
    chain_id: int,
    verifying_contract: str,
    timestamp_ms: Optional[int] = None,
    covered_entity_address: Optional[str] = None,
    token_count: Optional[int] = None,
    trace_id: Optional[str] = None,
    span_id: Optional[str] = None,
    intent_rationale: Optional[str] = None,
    agent_thought: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Construct and sign a BCC commitment (§4.2, plus the reconciled
    extension fields below):

        {agent_id, intent_type, intended_state_hash, nonce, timestamp,
         covered_entity_address, agent_public_key, chain_id,
         verifying_contract, signature}

    Field names are load-bearing (per the contract) — do not rename them.

    Fields beyond the frozen §4.2 five are signed over here, and MUST
    match `bcc_middleware/app/canonical.py` byte-for-byte or every signature
    fails verification:

      - `covered_entity_address`: the hospital an `EMR_WRITE`/clinical intent
        is against (nullable for non-healthcare intents). Signed, not just
        carried, so an attacker can't swap the target hospital on an
        otherwise-valid commitment (see schemas.py's field docstring).

      - `agent_public_key`: the agent's Ed25519 public key in the same
        multibase form as the DID document's `publicKeyMultibase` (§4.1).
        This is REQUIRED because this SDK's DID fingerprint is
        `sha256(pubkey)`, NOT the raw pubkey — so a verifier holding only the
        `agent_id` DID string cannot recover the key to check the signature.
        Carrying it here makes the commitment self-verifying: the middleware
        confirms `sha256(decoded_pubkey) == did_fingerprint` (binding the key
        to the DID, so it can't be substituted) and then verifies the
        signature against it. No external DID-resolution round-trip needed.

      - `chain_id` / `verifying_contract`: REQUIRED (docs/plans/2026-08-18-
        phase1-canonical-intent-encoding-proposal.md). Without these, a
        commitment signed once was valid, byte-for-byte, against any chain or
        any deployment of the protocol sharing the signing agent's DID.
        `chain_id` is the EVM chain ID this commitment is scoped to;
        `verifying_contract` is the `XibalbaAgentRegistry` address for that
        chain — the one address every downstream primitive in this
        architecture already resolves through. `bcc_middleware` denies a
        commitment whose `chain_id` doesn't match its own configured chain;
        it denies on a `verifying_contract` mismatch only when it has a
        configured registry address (see `bcc_middleware/app/main.py`'s
        deployment-binding check for why that second check is conditional,
        not unconditional, as a disclosed limitation rather than a silent
        downgrade).
    """
    timestamp_ms = timestamp_ms if timestamp_ms is not None else int(time.time() * 1000)
    intended_state_hash = hash_intent_payload(intent_payload)
    rationale = intent_rationale or agent_thought

    # The object that gets signed is the commitment MINUS the signature
    # field itself (you can't sign your own signature). Both sender and
    # receiver must derive this exact dict shape from the final JSON by just
    # dropping `signature` — no other field is excluded.
    unsigned = {
        "agent_id": agent_id,
        "intent_type": intent_type,
        "intended_state_hash": intended_state_hash,
        "nonce": nonce,
        "timestamp": timestamp_ms,
        "covered_entity_address": covered_entity_address,
        "agent_public_key": public_key_multibase(keypair.public_bytes()),
        "intent_rationale": rationale,
        "chain_id": chain_id,
        "verifying_contract": verifying_contract,
    }
    signature_bytes = keypair.sign(canonical_json_bytes(unsigned))

    commitment = dict(unsigned)
    commitment["signature"] = "0x" + signature_bytes.hex()

    # --- AOS Observability fields (post-signing, not part of the signed payload) ---
    # These are carried as metadata for bcc_middleware's OPA AOS gate and audit trail.
    # Auto-inject from the active OTel span if the caller didn't supply them.
    try:
        from .telemetry.aos_span import get_current_aos_context
        aos_ctx = get_current_aos_context()
    except Exception:
        aos_ctx = {}

    commitment["trace_id"] = trace_id or aos_ctx.get("trace_id")
    commitment["span_id"] = span_id or aos_ctx.get("span_id")
    commitment["agent_thought"] = rationale or aos_ctx.get("agent_thought") or aos_ctx.get("intent_rationale")
    commitment["token_count"] = token_count
    return commitment


def verify_bcc_commitment(commitment: Dict[str, Any], pubkey_bytes: bytes) -> bool:
    """
    Independently re-derive the signed payload from `commitment` and check
    the Ed25519 signature. Used by tests (and available to any caller that
    wants a local sanity check before round-tripping to bcc_middleware,
    which is the authoritative verifier in production).
    """
    sig_hex = commitment.get("signature", "")
    if not sig_hex.startswith("0x"):
        return False
    try:
        signature_bytes = bytes.fromhex(sig_hex[2:])
    except ValueError:
        return False

    # The AOS post-signing fields (trace_id, span_id, agent_thought, token_count)
    # are appended AFTER the signature is computed — they are NOT part of the
    # signed payload. The public intent_rationale is now signed, while the legacy
    # agent_thought alias remains post-signing for compatibility.
    _POST_SIGNING_FIELDS = {"signature", "trace_id", "span_id", "agent_thought", "token_count"}
    unsigned = {k: v for k, v in commitment.items() if k not in _POST_SIGNING_FIELDS}
    return verify_signature(pubkey_bytes, canonical_json_bytes(unsigned), signature_bytes)

def submit_commitment(commitment: Dict[str, Any], bcc_middleware_url: str) -> Dict[str, Any]:
    """
    Submits a signed BCC commitment to bcc_middleware's pre-execution gate and
    auto-tags the operation with OTel spans for the Fidelity vector (BCC resolution status).
    """
    import requests
    from .telemetry.core import get_tracer
    from .telemetry.conventions import EconomicAttributes

    tracer = get_tracer("integrity_sdk.bcc")
    with tracer.start_as_current_span("integrity.bcc.intercept") as span:
        intent_hash = commitment.get("intended_state_hash", "")
        if intent_hash:
            span.set_attribute(EconomicAttributes.BCC_INTENT_HASH, intent_hash)
            
        try:
            resp = requests.post(f"{bcc_middleware_url}/v1/bcc/intercept", json=commitment, timeout=10)
            resp.raise_for_status()
            result = resp.json()
            
            authorized = result.get("authorized", False)
            status = "authorized" if authorized else "denied"
            span.set_attribute(EconomicAttributes.BCC_RESOLUTION_STATUS, status)
            if not authorized:
                span.set_attribute("integrity.bcc.denial_reason", result.get("reason", "unknown"))
            return result
        except Exception as e:
            span.set_attribute(EconomicAttributes.BCC_RESOLUTION_STATUS, "error")
            span.record_exception(e)
            raise
