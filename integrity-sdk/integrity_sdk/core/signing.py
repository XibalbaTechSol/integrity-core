"""Ed25519 helpers shared by packs, receipts and checkpoints.

Signer identities are multibase public keys (`z` + base58btc of the
multicodec-tagged Ed25519 key), the same form DID documents use, so a key can
be compared, pinned in configuration and printed without ambiguity.
"""

from __future__ import annotations

from typing import Collection

import base58

from ..did import _MULTICODEC_ED25519_PUB, verify_signature


def public_key_from_multibase(value: str) -> bytes:
    """Decode a multibase Ed25519 public key; raises ValueError when it is not one."""
    if not isinstance(value, str) or not value.startswith("z"):
        raise ValueError("expected a base58btc multibase string starting with 'z'")
    raw = base58.b58decode(value[1:])
    if len(raw) != 34 or raw[:2] != _MULTICODEC_ED25519_PUB:
        raise ValueError("not a multicodec Ed25519 public key")
    return raw[2:]


def signer_matches(signer_key: str, trusted: Collection[str]) -> bool:
    """Whether `signer_key` is one of the trusted keys (compared as decoded key bytes)."""
    try:
        wanted = public_key_from_multibase(signer_key)
    except ValueError:
        return False
    for candidate in trusted:
        try:
            if public_key_from_multibase(candidate) == wanted:
                return True
        except ValueError:
            continue
    return False


def verify_multibase_signature(signer_key: str, message: bytes, signature_hex: str) -> bool:
    """Verify a hex Ed25519 signature against a multibase public key; False on any malformation."""
    try:
        public_key = public_key_from_multibase(signer_key)
        signature = bytes.fromhex(signature_hex)
    except (ValueError, TypeError):
        return False
    if len(signature) != 64:
        return False
    return verify_signature(public_key, message, signature)
