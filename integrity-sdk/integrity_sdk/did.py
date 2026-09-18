"""
Decentralized Identifier (DID) module for the Integrity Protocol.

Implements the `did:integrity:<hex-pubkey-fingerprint>` method described in
docs/INTERFACE_CONTRACT.md §4.1. Identity here is *key-based*, not
hardware-based: the DID is derived from an Ed25519 public key, and anyone
holding the matching private key can produce signatures that verify against
the DID document's `verificationMethod`. There is no hardware fallback and
no non-Ed25519 signing path — see `_REMOVED: HMAC fallback` note below for
why that matters.

Security note on the old prototype: the previous SDK (integrity-sdk v2.2.0)
shipped a `_DeterministicKeypair` that signed with HMAC-SHA512 over a seed
derived from the machine's hardware fingerprint whenever the `cryptography`
package was missing. That is NOT a signature scheme — HMAC is symmetric, so
"verifying" it requires the same secret the signer used, which defeats the
entire point of a DID (public verifiability by third parties who never see
the private key). This rebuild requires `cryptography` unconditionally: if
it isn't installed, DID creation fails loudly instead of silently downgrading
to a scheme that only *looks* like a signature.
"""

from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path
from typing import Optional, Tuple

import base58
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature

import hashlib
import shutil
import tempfile

# Multicodec prefix for "ed25519-pub" (0xed, varint-encoded) followed by the
# format byte 0x01. This two-byte prefix is what the `did:key` method (and,
# by extension, most Ed25519VerificationKey2020 producers) prepend before
# base58btc-encoding a raw Ed25519 public key. Prepending it lets any
# multicodec-aware consumer recover the key type from the multibase string
# alone, without out-of-band knowledge of "this is Ed25519".
_MULTICODEC_ED25519_PUB = bytes([0xED, 0x01])

_DID_METHOD = "integrity"


class Keypair:
    """Thin wrapper around `cryptography`'s Ed25519 keys with the
    sign/verify/serialize surface the rest of the SDK needs."""

    def __init__(self, private_key: Ed25519PrivateKey):
        self._sk = private_key
        self._pk = private_key.public_key()

    @classmethod
    def generate(cls) -> "Keypair":
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def from_pem(cls, pem_bytes: bytes) -> "Keypair":
        sk = serialization.load_pem_private_key(pem_bytes, password=None)
        if not isinstance(sk, Ed25519PrivateKey):
            raise TypeError(
                "DID private key file does not hold an Ed25519 key. "
                "Refusing to load a non-Ed25519 key as an Integrity Protocol identity."
            )
        return cls(sk)

    def sign(self, message: bytes) -> bytes:
        """Raw 64-byte Ed25519 signature over `message`. Callers are
        responsible for canonicalizing `message` first (see bcc.py) — Ed25519
        has no notion of "the same logical object serialized differently",
        so signer and verifier MUST agree byte-for-byte on what was signed."""
        return self._sk.sign(message)

    def public_bytes(self) -> bytes:
        """Raw 32-byte Ed25519 public key."""
        return self._pk.public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )

    def private_pem(self) -> bytes:
        return self._sk.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )

    def private_bytes_raw(self) -> bytes:
        """Raw 32-byte Ed25519 seed. Callers should treat this as sensitive
        as the PEM itself — it exists for internal key-derivation use (see
        prover.py's domain-separated ZK secret derivation), not for export."""
        return self._sk.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )


def verify_signature(pubkey_bytes: bytes, message: bytes, signature: bytes) -> bool:
    """Verify a raw Ed25519 signature against a raw 32-byte public key.
    Used by tests and by any code that needs to check a BCC commitment's
    signature locally before/instead of round-tripping to bcc_middleware."""
    try:
        Ed25519PublicKey.from_public_bytes(pubkey_bytes).verify(signature, message)
        return True
    except InvalidSignature:
        return False


def fingerprint_for_pubkey(pubkey_bytes: bytes) -> str:
    """
    The DID's `<hex-pubkey-fingerprint>` component: SHA-256 over the raw
    32-byte Ed25519 public key, hex-encoded (64 chars).

    We hash the pubkey rather than embedding it directly so the DID string
    itself doesn't leak the full public key (it's still recoverable from the
    DID document's `publicKeyMultibase`, but the identifier itself stays a
    fixed-width opaque handle, matching how `did:key` vs. a hash-based method
    differ). This choice isn't pinned by the interface contract beyond "hex
    fingerprint", so if a sibling package expects the raw pubkey hex instead
    of its SHA-256 digest, reconcile here.
    """
    return hashlib.sha256(pubkey_bytes).hexdigest()


def public_key_multibase(pubkey_bytes: bytes) -> str:
    """Multibase (base58btc, 'z' prefix) encoding of the multicodec-tagged
    Ed25519 public key, per §4.1's `publicKeyMultibase`."""
    return "z" + base58.b58encode(_MULTICODEC_ED25519_PUB + pubkey_bytes).decode("ascii")


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def build_did_document(pubkey_bytes: bytes) -> dict:
    """Build the DID document exactly as specified in §4.1. Field names and
    nesting here are load-bearing for integrity-oracle, which parses this
    same shape — don't add/rename top-level keys without updating the
    contract doc."""
    fingerprint = fingerprint_for_pubkey(pubkey_bytes)
    did = f"did:{_DID_METHOD}:{fingerprint}"
    key_id = f"{did}#key-1"
    return {
        "id": did,
        "controller": did,
        "created": _iso_now(),
        "verificationMethod": [
            {
                "id": key_id,
                "type": "Ed25519VerificationKey2020",
                "publicKeyMultibase": public_key_multibase(pubkey_bytes),
            }
        ],
    }


def attach_evm_account(doc: dict, evm_address: str, chain_id: int) -> dict:
    """
    Adds a CAIP-10 `blockchainAccountId` verification method to a DID
    document, binding the off-chain Ed25519 identity to the agent's own
    on-chain EVM wallet (see wallet.py — a deliberately separate keypair,
    not a re-derivation).

    This directly retires bcc_middleware's `chain.py::agent_id_to_address`
    fake `keccak256(pubkey)[-20:]` derivation (flagged there as an
    "INTEGRATION FLAG" placeholder): once an agent's real DID document
    carries this real address, any consumer that used to guess an address
    from the DID fingerprint can read it here instead.

    Uses the `EcdsaSecp256k1RecoveryMethod2020` verification method type and
    a CAIP-10 (`eip155:<chainId>:<address>`) `blockchainAccountId`, per the
    W3C DID spec's documented pattern for binding a blockchain account to a
    DID (this is the same shape `did:pkh` and most EVM-aware DID resolvers
    already expect, so this stays interoperable outside this protocol too).

    Mutates and returns `doc` rather than the more surprising "return a new
    dict" — callers already hold a reference to the document they're
    building up (see registration.py), and this mirrors how
    `build_did_document` itself is the one place that constructs the base
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


def _default_did_home() -> Path:
    """Choose an explicit Integrity store or the active harness profile store."""
    override = os.getenv("INTEGRITY_DID_HOME")
    if override:
        return Path(override).expanduser()
    # Harness profile roots are the default identity boundary for interactive
    # agents. The explicit Integrity override remains available to supervised
    # provisioning tools and tests.
    for variable in ("HERMES_HOME", "CODEX_HOME", "CLAUDE_CONFIG_DIR"):
        profile_root = os.getenv(variable)
        if profile_root:
            return Path(profile_root).expanduser() / ".integrity" / "did"
    return Path.home() / ".integrity" / "did"


def agent_dir(agent_id: Optional[str], *, did_home_root: str | Path | None = None) -> Path:
    """Public so other modules (bcc.py's NonceStore, client.py's offline
    cache) can co-locate their own per-agent state next to the DID files
    without duplicating the path-resolution logic. Harness adapters can pass
    a profile-scoped root; otherwise HERMES_HOME/CODEX_HOME are respected."""
    base = Path(did_home_root).expanduser() if did_home_root is not None else _default_did_home()
    return base / (agent_id or "default")


def did_home() -> Path:
    """Public accessor for the DID storage root (`$INTEGRITY_DID_HOME`, default
    `~/.integrity/did`) -- lets sibling modules (agent_subject.py) co-locate
    state alongside the per-agent directories without re-resolving the env
    var themselves."""
    return _default_did_home()


class IdentityInconsistentError(RuntimeError):
    """Persisted DID state exists but cannot be safely resolved.

    Raised instead of silently regenerating a keypair. A prior version of this function treated
    a missing or mismatched `document.json` as license to call `Keypair.generate()` and
    overwrite `private_key.pem` -- which destroys the original signing key and mints a new DID,
    with no way back. Per SPEC-v2.0.0-proposed.md §4.3: "Missing or inconsistent key state MUST
    fail closed. Ordinary startup MUST NOT generate a replacement key." A registered on-chain
    identity that loses its key this way cannot be recovered by regenerating one -- the new key
    derives a different DID that the chain has never heard of.
    """


def load_or_create_did(
    agent_id: Optional[str] = None,
    *,
    did_home_root: str | Path | None = None,
) -> Tuple[str, Keypair, dict]:
    """
    Load the persisted DID/keypair for `agent_id`, or generate a fresh Ed25519 keypair and DID
    document if this is a genuinely new identity (neither file exists yet).

    `did_home_root` selects an explicit identity-store root, normally the
    `.integrity/did` directory beneath a harness profile root.

    Returns (did, keypair, did_document).

    Fails closed -- raises IdentityInconsistentError -- rather than regenerating whenever
    existing state cannot be trivially and losslessly resolved:
      - key present, document missing or unreadable: the document is reconstructible from the
        key with zero information loss, so this case is repaired in place, not treated as an
        error.
      - key present, document present but does not match the key: ambiguous (which one is
        wrong?) and destructive to guess at, so this fails closed untouched.
      - key missing, document present: the document cannot reconstruct the private key, so
        there is nothing safe to do but fail closed.
    Neither file existing is the only case that creates a new identity.
    """
    # NOTE: previously called a nonexistent `_agent_dir` (undefined anywhere in this
    # module) — a live NameError bug that no test caught because nothing exercised
    # load_or_create_did() yet. Fixed to call the module's actual public `agent_dir`.
    # Shadowing the module-level function name with this local variable is fine —
    # nothing below this line needs the function itself, only this specific path.
    this_agent_dir = agent_dir(agent_id, did_home_root=did_home_root)
    this_agent_dir.parent.mkdir(parents=True, exist_ok=True, mode=stat.S_IRWXU)
    this_agent_dir.mkdir(parents=True, exist_ok=True, mode=stat.S_IRWXU)
    if did_home_root is not None:
        # A profile-scoped identity store contains a signing key. Keep its
        # directory boundary owner-only as well as the private-key file.
        os.chmod(this_agent_dir.parent, stat.S_IRWXU)
        os.chmod(this_agent_dir, stat.S_IRWXU)
    key_path = this_agent_dir / "private_key.pem"
    doc_path = this_agent_dir / "document.json"

    key_exists = key_path.exists()
    doc_exists = doc_path.exists()

    if key_exists and not doc_exists:
        # Losslessly recoverable: the document is pure derived data.
        keypair = Keypair.from_pem(key_path.read_bytes())
        doc = build_did_document(keypair.public_bytes())
        doc_path.write_text(json.dumps(doc, indent=2) + "\n")
        return doc["id"], keypair, doc

    if key_exists and doc_exists:
        keypair = Keypair.from_pem(key_path.read_bytes())
        doc = json.loads(doc_path.read_text())
        if doc.get("id") == f"did:{_DID_METHOD}:{fingerprint_for_pubkey(keypair.public_bytes())}":
            return doc["id"], keypair, doc
        raise IdentityInconsistentError(
            f"{doc_path} does not correspond to the key at {key_path}: "
            f"document claims '{doc.get('id')}' but the key derives "
            f"'did:{_DID_METHOD}:{fingerprint_for_pubkey(keypair.public_bytes())}'. "
            "Resolve manually -- this is not automatically repaired because either file could "
            "be the wrong one, and guessing risks replacing a registered identity's key."
        )

    if doc_exists and not key_exists:
        raise IdentityInconsistentError(
            f"{doc_path} exists but its private key at {key_path} is missing. "
            "A document cannot reconstruct a private key, so this cannot be auto-repaired. "
            "Restore the key from backup, or explicitly delete the document to start a new "
            "identity -- do not let this call silently mint a replacement key."
        )

    keypair = Keypair.generate()
    doc = build_did_document(keypair.public_bytes())

    # Private key material: owner-read/write only.
    key_path.write_bytes(keypair.private_pem())
    os.chmod(str(key_path), stat.S_IRUSR | stat.S_IWUSR)
    doc_path.write_text(json.dumps(doc, indent=2) + "\n")

    return doc["id"], keypair, doc


def migrate_identity_store(agent_id: str, *, source_home: str | Path, destination_home: str | Path) -> str:
    """Copy one canonical DID identity to a new root without key regeneration.

    Migration is deliberately copy-only: the source remains the recovery
    copy, an existing destination is never overwritten, and inconsistent
    source/destination state fails closed. The returned DID is safe to record;
    private key bytes never leave this function or appear in diagnostics.
    """
    source = Path(source_home).expanduser() / agent_id
    destination = Path(destination_home).expanduser() / agent_id
    source_key = source / "private_key.pem"
    source_doc = source / "document.json"
    if not source_key.exists() or not source_doc.exists():
        raise IdentityInconsistentError(f"cannot migrate {agent_id!r}: source identity is incomplete")
    keypair = Keypair.from_pem(source_key.read_bytes())
    document = json.loads(source_doc.read_text(encoding="utf-8"))
    expected_did = f"did:{_DID_METHOD}:{fingerprint_for_pubkey(keypair.public_bytes())}"
    if document.get("id") != expected_did:
        raise IdentityInconsistentError(f"cannot migrate {agent_id!r}: source document does not match its key")

    if destination.exists():
        try:
            existing_did, _, _ = _load_did_from_dir(destination)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise IdentityInconsistentError(f"cannot migrate {agent_id!r}: destination is inconsistent") from exc
        if existing_did != expected_did:
            raise IdentityInconsistentError(f"cannot migrate {agent_id!r}: destination DID mismatch")
        _merge_identity_registry(agent_id, source_home=Path(source_home), destination_home=Path(destination_home))
        return expected_did

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{agent_id}.migration-", dir=destination.parent))
    try:
        os.chmod(staging, stat.S_IRWXU)
        staged_key = staging / "private_key.pem"
        staged_key.write_bytes(source_key.read_bytes())
        os.chmod(staged_key, stat.S_IRUSR | stat.S_IWUSR)
        (staging / "document.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        # Refuse an overwrite if another process created the destination.
        try:
            os.mkdir(destination, stat.S_IRWXU)
        except FileExistsError:
            existing_did, _, _ = _load_did_from_dir(destination)
            if existing_did != expected_did:
                raise IdentityInconsistentError(f"cannot migrate {agent_id!r}: destination DID mismatch")
            _merge_identity_registry(agent_id, source_home=Path(source_home), destination_home=Path(destination_home))
            return expected_did
        shutil.copy2(staged_key, destination / "private_key.pem")
        os.chmod(destination / "private_key.pem", stat.S_IRUSR | stat.S_IWUSR)
        shutil.copy2(staging / "document.json", destination / "document.json")
        _merge_identity_registry(agent_id, source_home=Path(source_home), destination_home=Path(destination_home))
        return expected_did
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _load_did_from_dir(identity_dir: Path) -> Tuple[str, Keypair, dict]:
    keypair = Keypair.from_pem((identity_dir / "private_key.pem").read_bytes())
    document = json.loads((identity_dir / "document.json").read_text(encoding="utf-8"))
    expected = f"did:{_DID_METHOD}:{fingerprint_for_pubkey(keypair.public_bytes())}"
    if document.get("id") != expected:
        raise IdentityInconsistentError(f"identity at {identity_dir} does not match its key")
    return expected, keypair, document


def _merge_identity_registry(agent_id: str, *, source_home: Path, destination_home: Path) -> None:
    """Copy only this agent's validated non-secret registry history."""
    source_path = source_home.expanduser() / "identity_registry.jsonl"
    if not source_path.exists():
        return
    destination_home = destination_home.expanduser()
    destination_home.mkdir(parents=True, exist_ok=True)
    destination_path = destination_home / "identity_registry.jsonl"
    existing = set(destination_path.read_text(encoding="utf-8").splitlines()) if destination_path.exists() else set()
    additions: list[str] = []
    for line in source_path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line in existing:
            continue
        record = json.loads(line)
        if record.get("agent_id") != agent_id:
            continue
        if any(secret in {str(key).lower() for key in record} for secret in ("private_key", "seed", "password", "bearer_token", "keystore")):
            raise IdentityInconsistentError("cannot migrate identity registry containing secret-bearing fields")
        additions.append(line)
    if additions:
        with destination_path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(additions) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
