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
import os
import time

import base58
import respx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from httpx import Response

from app.chain import resolve_agent_primitives
from app.config import settings as default_settings
from app.schemas import BCCCommitment

# A well-formed but unregistered placeholder registry address, used as
# sign_commitment's default `verifying_contract`. Safe as a default because
# app/main.py's deployment-binding check only enforces verifying_contract
# when Settings.contract_address("XibalbaAgentRegistry") is actually
# configured -- most of this suite runs with no deployments file at all
# (see test_chain_baa_anchor.py's own "Explicit, nonexistent deployments_file"
# comment), so this value is never compared against anything for those
# tests. Tests that DO configure a registry address must pass a matching
# `verifying_contract` explicitly.
_PLACEHOLDER_VERIFYING_CONTRACT = "0x000000000000000000000000000000000000dEaD"

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
    chain_id: int | None = None,
    verifying_contract: str | None = None,
) -> dict:
    """
    Builds a fully-formed, correctly-signed BCC Commitment dict ready to
    POST to /v1/bcc/intercept, using the same canonicalization
    (app.canonical.canonical_commitment_bytes) the server verifies against.

    `chain_id` defaults to `int(os.getenv("CHAIN_ID", "31337"))` -- the exact
    same default_factory expression `Settings.chain_id` itself uses -- rather
    than the frozen `default_settings` singleton. This matters because
    `anvil_chain` (this file's own fixture) permanently overwrites
    `os.environ["CHAIN_ID"]` process-wide the first time any test uses it, so
    every `Settings()` constructed AFTER that point (the common per-test
    pattern in this suite, e.g. `Settings(opa_url=real_opa_server, ...)`)
    picks up anvil's real chain id -- but `default_settings` was already
    constructed once at process start, before that mutation, so it would
    silently keep signing commitments for a chain_id later tests' Settings
    no longer match. Reading the env var directly, at call time, tracks
    whichever `Settings()` the calling test actually built. `verifying_contract`
    defaults to a placeholder address (see module-level comment) -- neither
    default needs to be a real deployed contract, since the deployment-
    binding check is a string/int comparison against Settings, not an
    on-chain call.
    """
    if timestamp is None:
        timestamp = int(time.time() * 1000)
    if intended_state_hash is None:
        intended_state_hash = "0x" + hashlib.sha256(f"{intent_type}:{nonce}".encode()).hexdigest()
    if chain_id is None:
        chain_id = int(os.getenv("CHAIN_ID", "31337"))
    if verifying_contract is None:
        # Prefer whatever XibalbaAgentRegistry the ambient default Settings
        # actually resolves (DEPLOYMENTS_FILE, via the repo-root .env most
        # tests inherit) so a test that builds a bare `Settings(...)` with no
        # explicit deployments_file override -- the common case in this
        # suite -- gets a MATCHING verifying_contract by default, not one
        # that only happens to pass because the registry was unconfigured.
        # Falls back to the placeholder when nothing is configured at all.
        verifying_contract = default_settings.contract_address("XibalbaAgentRegistry") or _PLACEHOLDER_VERIFYING_CONTRACT

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
        "chain_id": chain_id,
        "verifying_contract": verifying_contract,
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
