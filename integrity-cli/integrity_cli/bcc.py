"""
BCC Commitment construction and signing.

The BCC Commitment is the intent-lock object exchanged between an agent
(here, the CLI acting on a developer's behalf) and bcc_middleware's
`POST /v1/bcc/intercept` pre-execution policy gate. Field names and shape
are pinned in docs/INTERFACE_CONTRACT.md section 4.2 -- do not rename or
restructure them here, since bcc_middleware and integrity-sdk are being
built against this exact contract in parallel.

Canonicalization note: the contract requires the signature to cover "the
above fields, canonical JSON" but does not pin the exact byte
serialization. We use `json.dumps(fields, sort_keys=True,
separators=(",", ":"))` (sorted keys, no whitespace) -- the de facto
standard for "canonical JSON" in protocols like this. This is a real
integration risk called out in README.md: if bcc_middleware/integrity-sdk
canonicalize differently, signatures built here won't verify there even
though the commitment shape is otherwise correct.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

NONCE_STATE_FILE = Path.home() / ".integrity-cli" / "identity" / "nonces.json"


def canonical_json_bytes(fields: dict[str, Any]) -> bytes:
    """Deterministic JSON encoding used both for hashing the intent payload
    and for signing the commitment fields. sort_keys + no separators
    whitespace guarantees the same bytes for the same logical object
    regardless of dict insertion order."""
    return json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")


def intended_state_hash(intent_payload: dict[str, Any]) -> str:
    """sha256 of the canonical intent payload -- INTERFACE_CONTRACT.md
    section 4.2: "0x<32-byte hex, sha256 of the canonical intent payload>"."""
    digest = hashlib.sha256(canonical_json_bytes(intent_payload)).hexdigest()
    return f"0x{digest}"


def _load_nonce_state() -> dict[str, int]:
    if not NONCE_STATE_FILE.exists():
        return {}
    try:
        return json.loads(NONCE_STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def next_nonce(agent_id: str) -> int:
    """Return the next monotonic nonce for this agent and persist it.

    The contract requires a "monotonic per-agent integer" nonce but doesn't
    say who owns the counter. A CLI invocation is a fresh process every
    time, so we track the last-used nonce per agent_id in a local file
    under ~/.integrity-cli/identity/nonces.json.

    This is a best-effort, single-machine counter: if the same agent
    identity is also driven from integrity-sdk, or from a second machine,
    nonce coordination needs a server-side authority (most likely the
    Oracle) instead of a local file. Flagged in README.md as an integration
    item to confirm once bcc_middleware's actual nonce-validation behavior
    is known.
    """
    state = _load_nonce_state()
    nonce = state.get(agent_id, 0) + 1
    state[agent_id] = nonce
    NONCE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    NONCE_STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True))
    return nonce


def build_commitment(
    private_key: Ed25519PrivateKey,
    agent_id: str,
    intent_type: str,
    intent_payload: dict[str, Any],
    chain_id: int,
    verifying_contract: str,
    covered_entity_address: str | None = None,
) -> dict[str, Any]:
    """Build and sign a BCC Commitment per INTERFACE_CONTRACT.md section 4.2,
    plus the reconciled extension fields (`covered_entity_address`,
    `agent_public_key`, `chain_id`, `verifying_contract`) — see
    integrity-sdk/integrity_sdk/bcc.py and bcc_middleware/app/canonical.py,
    which this must match byte-for-byte.

    Signs over every field except `signature` itself, in the same canonical
    JSON form used for the intended_state_hash -- the signature therefore
    also authenticates the nonce, timestamp, target covered entity, and the
    agent's own public key, not just the hash.

    `agent_public_key` is REQUIRED by the reconciled middleware: this DID's
    fingerprint is sha256(pubkey), not the raw key, so the verifier can't
    recover the key from `agent_id` alone — the commitment carries it, and
    the middleware binds it by checking sha256(pubkey) == fingerprint.

    `chain_id`/`verifying_contract` are REQUIRED (docs/plans/2026-08-18-
    phase1-canonical-intent-encoding-proposal.md): without them a commitment
    signed once was valid against any chain or deployment sharing the
    signing agent's DID. `verifying_contract` is the target chain's
    `XibalbaAgentRegistry` address.
    """
    # Imported here (not at module top) purely to avoid any import-order
    # coupling between these two sibling modules; the encoder is a pure
    # function of the public key bytes.
    from .identity import _multibase_encode_pubkey

    public_bytes = private_key.public_key().public_bytes_raw()
    fields = {
        "agent_id": agent_id,
        "intent_type": intent_type,
        "intended_state_hash": intended_state_hash(intent_payload),
        "nonce": next_nonce(agent_id),
        "timestamp": int(time.time() * 1000),  # unix ms, per contract
        "covered_entity_address": covered_entity_address,
        "agent_public_key": _multibase_encode_pubkey(public_bytes),
        "chain_id": chain_id,
        "verifying_contract": verifying_contract,
    }
    signature = private_key.sign(canonical_json_bytes(fields))
    return {**fields, "signature": f"0x{signature.hex()}"}
