from __future__ import annotations

import pytest

from integrity_sdk.core import PackPinError, PackPinStore, sign_pack
from integrity_sdk.did import Keypair, public_key_multibase


MANIFEST = """\
pack_format: integrity.pack/1
name: lab
version: 1.0.0
kernel_range: '>=1.0.0'
decision_contract: integrity.decision/1
entrypoint: data.integrity.pack.decision
event_classes:
  agent.tool_call:
    no_match: deny
"""
POLICY = "package integrity.pack\n\ndecision := {\"decision\": \"deny\", \"reason_code\": \"DEFAULT\"}\n"


def _pack(tmp_path, signer):
    root = tmp_path / "pack"
    root.mkdir(parents=True)
    (root / "pack.yaml").write_text(MANIFEST)
    (root / "policy.rego").write_text(POLICY)
    sign_pack(root, signer)
    return root


def test_pin_resolves_only_the_verified_hash(tmp_path):
    signer = Keypair.generate()
    trusted = [public_key_multibase(signer.public_bytes())]
    pack_dir = _pack(tmp_path, signer)
    store = PackPinStore(tmp_path / "pins.json")
    pin = store.pin("tenant-lab", pack_dir, trusted_signers=trusted)

    loaded = store.resolve("tenant-lab", "lab", trusted_signers=trusted)
    assert loaded.pack_hash == pin.pack_hash
    assert store.get("tenant-lab", "lab") == pin


def test_tampering_after_pin_is_refused(tmp_path):
    signer = Keypair.generate()
    trusted = [public_key_multibase(signer.public_bytes())]
    pack_dir = _pack(tmp_path, signer)
    store = PackPinStore(tmp_path / "pins.json")
    store.pin("tenant-lab", pack_dir, trusted_signers=trusted)
    (pack_dir / "policy.rego").write_text(POLICY + "\n# changed\n")

    with pytest.raises(PackPinError, match="no longer verifies"):
        store.resolve("tenant-lab", "lab", trusted_signers=trusted)


def test_replacement_requires_current_hash(tmp_path):
    signer = Keypair.generate()
    trusted = [public_key_multibase(signer.public_bytes())]
    first = _pack(tmp_path / "first", signer)
    second = _pack(tmp_path / "second", signer)
    (second / "pack.yaml").write_text(MANIFEST.replace("version: 1.0.0", "version: 2.0.0"))
    sign_pack(second, signer)
    store = PackPinStore(tmp_path / "pins.json")
    original = store.pin("tenant-lab", first, trusted_signers=trusted)
    with pytest.raises(PackPinError, match="currently pinned hash"):
        store.pin("tenant-lab", second, trusted_signers=trusted, replace=True, expected_previous_hash="sha256:" + "0" * 64)
    replacement = store.pin("tenant-lab", second, trusted_signers=trusted, replace=True, expected_previous_hash=original.pack_hash)
    assert replacement.pack_hash != original.pack_hash
