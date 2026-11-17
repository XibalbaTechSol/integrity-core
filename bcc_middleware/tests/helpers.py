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

from app.chain import clear_actor_cache
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
    invocation_id: str | None = None,
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
    if invocation_id is not None:
        fields["invocation_id"] = invocation_id
    message = json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    signature = private_key.sign(message)

    return {**fields, "signature": "0x" + signature.hex()}


def make_commitment_model(**kwargs) -> BCCCommitment:
    return BCCCommitment(**kwargs)


def mock_oracle_agent(
    respx_mock: respx.MockRouter,
    oracle_url: str,
    agent_id: str,
    *,
    verification_tier: int = 1,
) -> None:
    """
    Stubs the oracle's `GET /v1/agent/{id}` in the shape registration v3 PR 4.6 leaves it: an
    id and a server-verified `verification_tier` (default 1, what every registered agent gets;
    see `integrity-oracle`'s `SERVER_VERIFIED_TIER`), and NO `primitives` object. Nothing in the
    middleware resolves on-chain addresses through the oracle any more; that is `bind_actor`.
    """
    respx_mock.get(f"{oracle_url.rstrip('/')}/v1/agent/{agent_id}").mock(
        return_value=Response(200, json={"id": agent_id, "verification_tier": verification_tier})
    )


def send_tx(anvil_chain: dict, fn) -> dict:
    """Signs and mines `fn` (a bound contract call) from the anvil dev signer; asserts success."""
    from eth_account import Account

    w3 = anvil_chain["w3"]
    account = Account.from_key(anvil_chain["signer_private_key"])
    tx = fn.build_transaction(
        {"from": account.address, "nonce": w3.eth.get_transaction_count(account.address), "chainId": anvil_chain["chain_id"]}
    )
    receipt = w3.eth.wait_for_transaction_receipt(
        w3.eth.send_raw_transaction(account.sign_transaction(tx).raw_transaction), timeout=15
    )
    assert receipt.status == 1
    return receipt


def fixture_contract(anvil_chain: dict, name: str):
    """A fixture mock (`agent_registry`, `stake_vault`, `ais_registry`, `action_anchor`) with
    its own mock ABI, which includes the test-only setters the canonical ABI lacks."""
    return anvil_chain["w3"].eth.contract(address=anvil_chain[f"{name}_address"], abi=anvil_chain[f"{name}_abi"])


def bind_actor(anvil_chain: dict, agent_id: str, actor: str | None, *, retired: bool = False) -> None:
    """
    Records `agent_id` in the fixture `AgentRegistry` with `actor` bound (None = registered with
    no actor), the v3 resolution path the middleware reads (`resolveDID(did).actor`). `agent_id`
    must be a real `did:integrity:<64 hex>` DID (use `new_agent()`): the mock parses it exactly
    as the real registry does and reverts `InvalidDid` otherwise. Clears the middleware's actor
    cache so the next read sees the new record.
    """
    zero = "0x0000000000000000000000000000000000000000"
    registry = fixture_contract(anvil_chain, "agent_registry")
    send_tx(anvil_chain, registry.functions.setRecord(agent_id, actor or zero, retired))
    clear_actor_cache()


def chain_settings(anvil_chain: dict, **overrides):
    """`Settings` pointed at the fixture chain and its v3 deployments file."""
    from app.config import Settings

    base = {
        "rpc_url": anvil_chain["rpc_url"],
        "chain_id": anvil_chain["chain_id"],
        "deployments_file": anvil_chain["deployments_file"],
    }
    return Settings(**{**base, **overrides})
