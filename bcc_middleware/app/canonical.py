"""
Canonicalization + Ed25519 signature verification for BCC Commitments.

*** RECONCILED against integrity-sdk / integrity-cli (see
docs/INTERFACE_CONTRACT.md §4.2 and the package README's "Integration
reconciliation" #1-2) ***. Two things §4.2 originally left open, now pinned:

  (a) Canonical JSON = `json.dumps(fields, sort_keys=True,
      separators=(",", ":"), ensure_ascii=True)` encoded as UTF-8.
      `ensure_ascii=True` specifically (not the RFC 8785/JCS default) --
      this is the byte-for-byte rule integrity-sdk's canonical_json_bytes
      also implements; a mismatch here would silently break signatures on
      any non-ASCII content.
  (b) The DID fingerprint is `sha256(pubkey)`, NOT the raw public key --
      a real one-way fingerprint, not a self-encoding one. Since a sha256
      digest can't be inverted back to the key it hashed, a verifier
      holding only `agent_id` cannot recover the pubkey needed to check
      `signature`. The commitment therefore carries the agent's own public
      key (`agent_public_key`, multibase, same form as the DID document's
      `publicKeyMultibase`), and this module BINDS it before trusting it:
      `sha256(decoded_pubkey) == agent_id` fingerprint, or reject. That
      binding is what makes trusting a carried key safe -- see
      `public_key_from_commitment` below.
"""

from __future__ import annotations

import hashlib
import json

import base58
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.schemas import BCCCommitment

# Multicodec prefix for "ed25519-pub" (0xed, varint) + 0x01 format byte, the
# two bytes integrity-sdk's did.py prepends before base58btc-encoding a raw
# Ed25519 public key into `publicKeyMultibase`. Stripped back off here.
_MULTICODEC_ED25519_PUB = bytes([0xED, 0x01])


class SignatureVerificationError(Exception):
    """Raised for any reason a commitment's signature can't be trusted."""


def canonical_commitment_bytes(commitment: BCCCommitment) -> bytes:
    """
    Serialize every signed field of the commitment EXCEPT `signature` itself,
    in the canonical form the signature is expected to cover. See module
    docstring for the exact algorithm and why it's a documented assumption
    rather than a confirmed spec.
    """
    payload = {
        "agent_id": commitment.agent_id,
        "intent_type": commitment.intent_type,
        "intended_state_hash": commitment.intended_state_hash,
        "nonce": commitment.nonce,
        "timestamp": commitment.timestamp,
        # Included (as `null` when unset) even though it's not in the frozen
        # §4.2 shape -- see schemas.py's BCCCommitment.covered_entity_address
        # docstring. It MUST be signed over, not just carried alongside the
        # signed fields: if it weren't, an attacker who intercepts an
        # otherwise-valid signed commitment could swap in a different
        # covered_entity_address without invalidating the signature, and
        # get an unrelated hospital's BAA status used to authorize access
        # against a hospital the agent never agreed to.
        "covered_entity_address": commitment.covered_entity_address,
        # Public-safe rationale used by AOS policy; signed so the policy gate
        # receives the same declared intent the signer committed to.
        "intent_rationale": commitment.intent_rationale,
        # Also signed: the self-certifying public key (see schemas.py). Signing
        # it means an attacker can't swap in a different (but validly-hashing?
        # — no: sha256 makes that infeasible) key AND re-use the signature.
        "agent_public_key": commitment.agent_public_key,
        # Canonical intent encoding (docs/plans/2026-08-18-phase1-canonical-
        # intent-encoding-proposal.md) -- signed so a captured commitment
        # can't be replayed against a different chain/deployment by simply
        # swapping these two fields and leaving the rest (and the signature)
        # untouched.
        "chain_id": commitment.chain_id,
        "verifying_contract": commitment.verifying_contract,
    }
    if commitment.invocation_id is not None:
        payload["invocation_id"] = commitment.invocation_id
    # ensure_ascii=True to match integrity-sdk's canonical_json_bytes byte-for-byte
    # (its module docstring pins ensure_ascii=True as the cross-language protocol
    # rule). For the ASCII-only fields here the two are identical, but they MUST
    # agree — a mismatch would silently break signatures on any non-ASCII content.
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def public_key_from_commitment(commitment: BCCCommitment) -> Ed25519PublicKey:
    """
    Decode the agent's carried `agent_public_key` (multibase) AND verify it is
    the key the DID commits to: `sha256(pubkey)` must equal the `agent_id`
    fingerprint. This binding is what makes trusting a *carried* key safe — an
    attacker can't substitute their own key without also finding a preimage
    collision on the victim's DID fingerprint (infeasible for sha256).

    Mirrors integrity-sdk's did.py: `publicKeyMultibase` = "z" +
    base58btc(0xed 0x01 || raw_pubkey), and fingerprint = sha256(raw_pubkey).hex().
    """
    multibase = commitment.agent_public_key
    if not multibase.startswith("z"):
        raise SignatureVerificationError("agent_public_key must be multibase base58btc ('z'-prefixed)")
    try:
        decoded = base58.b58decode(multibase[1:])
    except Exception as exc:  # base58 raises ValueError on bad input
        raise SignatureVerificationError(f"agent_public_key is not valid base58: {exc}") from exc
    if not decoded.startswith(_MULTICODEC_ED25519_PUB):
        raise SignatureVerificationError("agent_public_key is not multicodec-tagged as ed25519-pub")
    key_bytes = decoded[len(_MULTICODEC_ED25519_PUB):]
    if len(key_bytes) != 32:
        raise SignatureVerificationError(f"decoded public key must be 32 bytes, got {len(key_bytes)}")

    # The load-bearing binding: this key must be the one agent_id commits to.
    fingerprint = commitment.agent_id.removeprefix("did:integrity:")
    if hashlib.sha256(key_bytes).hexdigest() != fingerprint:
        raise SignatureVerificationError(
            "agent_public_key does not match agent_id: sha256(pubkey) != DID fingerprint "
            "(a carried key that isn't the one the DID commits to is a substitution attempt)"
        )

    try:
        return Ed25519PublicKey.from_public_bytes(key_bytes)
    except Exception as exc:
        raise SignatureVerificationError(f"agent_public_key is not a valid Ed25519 public key: {exc}") from exc


def verify_commitment_signature(commitment: BCCCommitment) -> None:
    """
    Raises SignatureVerificationError if the signature doesn't check out.
    Callers MUST treat this as a hard deny (fail closed) -- an
    unverifiable signature means we cannot trust that `agent_id` actually
    authored this commitment, which is the entire basis for every
    downstream check (circuit breaker, BAA, policy).
    """
    public_key = public_key_from_commitment(commitment)
    message = canonical_commitment_bytes(commitment)
    try:
        signature_bytes = bytes.fromhex(commitment.signature.removeprefix("0x"))
    except ValueError as exc:
        raise SignatureVerificationError(f"signature is not valid hex: {exc}") from exc

    try:
        public_key.verify(signature_bytes, message)
    except InvalidSignature as exc:
        raise SignatureVerificationError("Ed25519 signature does not match commitment fields") from exc
