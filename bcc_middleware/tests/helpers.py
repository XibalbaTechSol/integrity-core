"""Test-only helpers for building validly-signed BCC Commitments.

These build commitments the same way integrity-sdk's real bcc.py does, so the
tests exercise the actual reconciled protocol: DID fingerprint = sha256(pubkey)
(NOT the raw pubkey), the pubkey carried as a self-certifying multibase
`agent_public_key`, and ensure_ascii=True canonicalization. Verified for real
cross-package agreement in the SDK↔middleware round-trip (see canonical.py).
"""

from __future__ import annotations

import hashlib
import json
import time

import base58
import respx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from httpx import Response

from app.chain import resolve_agent_primitives
from app.schemas import BCCCommitment

_MULTICODEC_ED25519_PUB = bytes([0xED, 0x01])


def _public_key_multibase(public_bytes: bytes) -> str:
    return "z" + base58.b58encode(_MULTICODEC_ED25519_PUB + public_bytes).decode("ascii")


def new_agent() -> tuple[str, Ed25519PrivateKey]:
    """Generates a fresh keypair and its did:integrity: DID, matching
    integrity-sdk's did.py: fingerprint = sha256(raw pubkey)."""
    private_key = Ed25519PrivateKey.generate()
    public_bytes = private_key.public_key().public_bytes_raw()
    agent_id = f"did:integrity:{hashlib.sha256(public_bytes).hexdigest()}"
    return agent_id, private_key


def sign_commitment(
    private_key: Ed25519PrivateKey,
    *,
    agent_id: str,
    intent_type: str = "payment",
    nonce: int = 1,
    timestamp: int | None = None,
    intended_state_hash: str | None = None,
    covered_entity_address: str | None = None,
    intent_rationale: str | None = None,
    agent_thought: str | None = None,
) -> dict:
    """
    Builds a fully-formed, correctly-signed BCC Commitment dict ready to
    POST to /v1/bcc/intercept, using the same canonicalization
    (app.canonical.canonical_commitment_bytes) the server verifies against.
    """
    if timestamp is None:
        timestamp = int(time.time() * 1000)
    if intended_state_hash is None:
        intended_state_hash = "0x" + hashlib.sha256(f"{intent_type}:{nonce}".encode()).hexdigest()

    public_bytes = private_key.public_key().public_bytes_raw()
    rationale = intent_rationale or agent_thought
    fields = {
        "agent_id": agent_id,
        "intent_type": intent_type,
        "intended_state_hash": intended_state_hash,
        "nonce": nonce,
        "timestamp": timestamp,
        # Signed over even when None -- must match
        # app.canonical.canonical_commitment_bytes exactly or every caller
        # of this helper (basically the whole test suite) would produce
        # commitments that fail signature verification.
        "covered_entity_address": covered_entity_address,
        "agent_public_key": _public_key_multibase(public_bytes),
        "intent_rationale": rationale,
    }
    message = json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    signature = private_key.sign(message)

    return {**fields, "signature": "0x" + signature.hex()}


def make_commitment_model(**kwargs) -> BCCCommitment:
    return BCCCommitment(**kwargs)


def mock_oracle_agent_resolution(
    respx_mock: respx.MockRouter,
    oracle_url: str,
    agent_id: str,
    sovereign_agent_address: str,
    *,
    state_anchor_address: str | None = None,
    slasher_address: str | None = None,
    verification_tier: int = 1,
) -> None:
    """
    Stubs the oracle's `GET /v1/agent/{id}` response that
    `app.chain.resolve_agent_primitives` (used by both the BAA check's
    businessAssociate resolution and per-agent anchoring) calls. Tests in this
    suite exercise real on-chain eth_call/eth_sendTransaction logic against a
    real anvil — a real integrity-oracle isn't part of that fixture set, so its
    one HTTP dependency is stubbed here rather than standing up the whole Rust
    service just to answer "what is this agent's SovereignAgent address" for a
    test that isn't about the oracle itself (see test_baa_health_integration.py
    for the equivalent real-Integrity-Health-contracts integration, mirrored here for the
    oracle boundary).

    `resolve_agent_primitives` is `lru_cache`d per (oracle_url, agent_id); since
    every test uses a freshly generated `agent_id`, cache entries never collide
    across tests.

    Also includes `verification_tier` (default 1, matching what every real
    registered agent gets — see `integrity-oracle`'s `SERVER_VERIFIED_TIER`) in
    the mocked response, since `app.chain.resolve_verification_tier` reads the
    same `GET /v1/agent/{id}` endpoint this helper stubs.
    """
    primitives = {
        "sovereign_agent": sovereign_agent_address,
        "state_anchor": state_anchor_address or sovereign_agent_address,
    }
    if slasher_address is not None:
        primitives["slasher"] = slasher_address

    respx_mock.get(f"{oracle_url.rstrip('/')}/v1/agent/{agent_id}").mock(
        return_value=Response(
            200,
            json={
                "id": agent_id,
                "verification_tier": verification_tier,
                "primitives": primitives,
            },
        )
    )
    resolve_agent_primitives.cache_clear()
