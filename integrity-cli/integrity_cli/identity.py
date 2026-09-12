"""
Local agent identity: Ed25519 keypair generation and DID documents.

This CLI deliberately does NOT hard-depend on integrity-sdk (a sibling
package being rebuilt from scratch in parallel -- see
docs/INTERFACE_CONTRACT.md). Depending on it here would couple this
package's build to the SDK's build order/API stability while both are still
in flux. Instead this module implements the minimal identity primitives
directly: real Ed25519 keys via the `cryptography` library (never an
HMAC/pseudo-signature fallback -- INTERFACE_CONTRACT.md section 4.1 is
explicit about that), producing the exact same DID document shape the
contract specifies, so integrity-oracle can consume it unmodified whichever
package generated it.

Storage location and layout now match integrity-sdk's did.py exactly --
$INTEGRITY_DID_HOME (default ~/.integrity/did), one subdirectory per
identity name holding private_key.pem and document.json. This is a
deliberate change (tri-repo audit 2026-09-12, F2): the DID document shape
was already byte-for-byte identical between the two packages, but each
persisted it under a different root (~/.integrity-cli/identity vs
~/.integrity/did), so the SAME name/agent_id could silently end up with
TWO DIFFERENT DIDs depending on which tool touched it first -- exactly what
happened to Shield's "shield-replacement" identity. Unifying the storage
location closes that permanently: this CLI still implements its own
independent code (no import of integrity_sdk), it just agrees with the SDK
on where state lives, so nothing can diverge again. See
docs/runbooks/gate1-identity-boundary-handoff-2026-09-12.md for the full
reconciliation this required for identities that had already diverged.

Key storage is intentionally simple: a PKCS8 PEM file on disk, mode 0600.
This is a developer CLI for local/dev use, not a production KMS -- don't
reuse these keys for anything that matters.
"""
from __future__ import annotations

import datetime
import hashlib
import os
import stat
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def _default_identity_dir() -> Path:
    override = os.getenv("INTEGRITY_DID_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".integrity" / "did"


# Base directory holding one subdirectory per identity name -- mirrors
# integrity-sdk's did.py::_default_did_home(). A plain module attribute
# (not a function) so existing tests can monkeypatch it directly, same
# pattern as before this change.
IDENTITY_DIR = _default_identity_dir()


def agent_dir(name: str) -> Path:
    """Per-identity directory: IDENTITY_DIR/<name>/, matching integrity-sdk's
    did.py::agent_dir nested layout exactly (private_key.pem, document.json,
    and any other per-identity file colocated the same way)."""
    return IDENTITY_DIR / name

# Multicodec varint prefix for "ed25519-pub" (0xed, 0x01), per the
# multiformats table used by the did:key method / Ed25519VerificationKey2020.
# Prepending this is what makes the multibase string self-describing as an
# Ed25519 public key rather than opaque bytes -- a verifier can look at the
# prefix alone to know how to interpret what follows.
_ED25519_MULTICODEC_PREFIX = bytes([0xED, 0x01])

_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _base58btc_encode(data: bytes) -> str:
    """Encode bytes as base58 (Bitcoin alphabet).

    Implemented locally rather than adding a dependency for something this
    small; matches the `base58` PyPI package's b58encode byte-for-byte
    (verified against the standard "hello world" test vector in
    tests/test_identity.py).
    """
    n = int.from_bytes(data, "big")
    encoded = ""
    while n > 0:
        n, rem = divmod(n, 58)
        encoded = _BASE58_ALPHABET[rem] + encoded
    # Leading zero bytes don't affect the big-endian integer value at all,
    # so they must be re-added as leading '1' characters (base58's zero digit).
    n_leading_zeros = len(data) - len(data.lstrip(b"\x00"))
    return "1" * n_leading_zeros + encoded


def _multibase_encode_pubkey(public_bytes: bytes) -> str:
    """multibase 'z' prefix (declares "base58btc") over the multicodec-tagged
    public key -- this is `publicKeyMultibase` in INTERFACE_CONTRACT.md
    section 4.1, and the standard did:key encoding."""
    return "z" + _base58btc_encode(_ED25519_MULTICODEC_PREFIX + public_bytes)


def _fingerprint(public_bytes: bytes) -> str:
    """`did:integrity:<hex-pubkey-fingerprint>` = full sha256(pubkey), 64 hex chars.

    Must be the FULL sha256 digest, not a truncation: bcc_middleware's
    reconciled signature verification (app/canonical.py::public_key_from_commitment)
    binds the carried `agent_public_key` to the DID by checking
    `sha256(pubkey).hexdigest() == fingerprint`. A 20-byte-truncated fingerprint
    (as an earlier version of this file used) could never match that full
    digest, so a CLI-built commitment would fail verification at the middleware.
    This now matches integrity-sdk's did.py::fingerprint_for_pubkey exactly.
    """
    return hashlib.sha256(public_bytes).hexdigest()


def _key_path(name: str) -> Path:
    return agent_dir(name) / "private_key.pem"


def document_path(name: str) -> Path:
    """Public so main.py can persist/read the DID document alongside the key,
    at the same path integrity-sdk's registration.py writes/reads."""
    return agent_dir(name) / "document.json"


def identity_exists(name: str = "default") -> bool:
    return _key_path(name).exists()


def generate_identity(name: str = "default", force: bool = False) -> dict:
    """Generate a new Ed25519 keypair and persist the private key locally.

    Returns the DID document for the new identity. Raises FileExistsError if
    an identity with this name already exists and force=False, so a
    keygen invocation can't silently clobber a key another tool/agent relies on.
    """
    path = _key_path(name)
    if path.exists() and not force:
        raise FileExistsError(
            f"Identity '{name}' already exists at {path}. Use --force to overwrite."
        )
    agent_dir(name).mkdir(parents=True, exist_ok=True)
    private_key = Ed25519PrivateKey.generate()
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path.write_bytes(pem)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    return did_document_for_key(private_key.public_key())


def load_private_key(name: str = "default") -> Ed25519PrivateKey:
    path = _key_path(name)
    if not path.exists():
        raise FileNotFoundError(
            f"No identity named '{name}' found at {path}. "
            "Run `integrity identity keygen` first."
        )
    pem = path.read_bytes()
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError(f"Key at {path} is not an Ed25519 key.")
    return key


def did_document_for_key(public_key: Ed25519PublicKey) -> dict:
    """Build the DID document shape pinned in INTERFACE_CONTRACT.md section
    4.1 for a given public key."""
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    fingerprint = _fingerprint(public_bytes)
    did = f"did:integrity:{fingerprint}"
    return {
        "id": did,
        "controller": did,
        "created": datetime.datetime.now(datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "verificationMethod": [
            {
                "id": f"{did}#key-1",
                "type": "Ed25519VerificationKey2020",
                "publicKeyMultibase": _multibase_encode_pubkey(public_bytes),
            }
        ],
    }


def did_document(name: str = "default") -> dict:
    """Load a local identity and return its DID document."""
    private_key = load_private_key(name)
    return did_document_for_key(private_key.public_key())


def attach_evm_account(doc: dict, evm_address: str, chain_id: int) -> dict:
    """
    Adds a CAIP-10 `blockchainAccountId` verification method to a DID
    document, binding the off-chain Ed25519 identity to the agent's own
    on-chain EVM wallet (see wallet.py -- a deliberately separate keypair,
    not a re-derivation). Mirrors integrity-sdk's did.py::attach_evm_account
    byte-for-byte (same verification method shape), so a DID document
    produced by either package is interchangeable for any consumer
    (integrity-oracle in particular).

    Uses the `EcdsaSecp256k1RecoveryMethod2020` verification method type and
    a CAIP-10 (`eip155:<chainId>:<address>`) `blockchainAccountId`, per the
    W3C DID spec's documented pattern for binding a blockchain account to a
    DID.

    Mutates and returns `doc` rather than the more surprising "return a new
    dict" -- callers already hold a reference to the document they're
    building up (see main.py's `agent register`), and this mirrors how
    `did_document_for_key` itself is the one place that constructs the base
    shape.
    """
    key_id = f"{doc['id']}#evm-1"
    doc.setdefault("verificationMethod", []).append(
        {
            "id": key_id,
            "type": "EcdsaSecp256k1RecoveryMethod2020",
            "controller": doc["id"],
            "blockchainAccountId": f"eip155:{chain_id}:{evm_address}",
        }
    )
    return doc
