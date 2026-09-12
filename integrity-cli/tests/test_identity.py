"""Tests for integrity_cli.identity: Ed25519 keygen, DID document shape,
and the base58/multibase encoding used for publicKeyMultibase."""
from __future__ import annotations

import stat

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from integrity_cli import identity


def test_base58btc_encode_matches_known_vectors():
    # Standard "hello world" base58 test vector (used across base58
    # implementations, e.g. python-base58's own test suite).
    assert identity._base58btc_encode(b"hello world") == "StV1DL6CwTryKyV"
    # Leading zero bytes must become leading '1' characters.
    assert (
        identity._base58btc_encode(bytes([0x00, 0x00, 0x28, 0x7F, 0xB4, 0xCD]))
        == "11233QC4"
    )
    assert identity._base58btc_encode(b"") == ""


def test_generate_identity_creates_key_file_with_restricted_permissions():
    doc = identity.generate_identity("default")
    path = identity._key_path("default")
    assert path.parent == identity.agent_dir("default")
    assert path.exists()
    # Private key material must not be world/group readable.
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == stat.S_IRUSR | stat.S_IWUSR
    assert doc["id"].startswith("did:integrity:")


def test_generate_identity_refuses_overwrite_without_force():
    identity.generate_identity("default")
    with pytest.raises(FileExistsError):
        identity.generate_identity("default")
    # --force is required to overwrite.
    identity.generate_identity("default", force=True)


def test_did_document_matches_interface_contract_shape():
    doc = identity.generate_identity("default")
    assert set(doc.keys()) == {"id", "controller", "created", "verificationMethod"}
    assert doc["id"] == doc["controller"]
    assert doc["id"].startswith("did:integrity:")
    [vm] = doc["verificationMethod"]
    assert vm["id"] == f"{doc['id']}#key-1"
    assert vm["type"] == "Ed25519VerificationKey2020"
    assert vm["publicKeyMultibase"].startswith("z")


def test_load_private_key_roundtrips_with_generated_identity():
    doc = identity.generate_identity("default")
    loaded = identity.load_private_key("default")
    assert isinstance(loaded, Ed25519PrivateKey)
    # Loading the same identity's key must reproduce the same DID.
    assert identity.did_document_for_key(loaded.public_key())["id"] == doc["id"]


def test_load_private_key_missing_identity_raises_clear_error():
    with pytest.raises(FileNotFoundError, match="No identity named 'ghost'"):
        identity.load_private_key("ghost")


def test_different_identities_get_different_dids():
    doc_a = identity.generate_identity("a")
    doc_b = identity.generate_identity("b")
    assert doc_a["id"] != doc_b["id"]
