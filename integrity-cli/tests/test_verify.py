from __future__ import annotations

import json

import jcs
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from eth_utils import keccak
from typer.testing import CliRunner

from integrity_cli.main import app
from integrity_cli import main as main_module


runner = CliRunner()
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58(data: bytes) -> str:
    number = int.from_bytes(data, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = _B58[remainder] + encoded
    return "z" + "1" * (len(data) - len(data.lstrip(b"\0"))) + (encoded or "1")


def _sign(key: Ed25519PrivateKey, domain: bytes, body: dict) -> dict:
    return {**body, "signature": key.sign(domain + jcs.canonicalize(body)).hex()}


def _bundle(tmp_path):
    key = Ed25519PrivateKey.generate()
    signer = _b58(b"\xed\x01" + key.public_key().public_bytes_raw())
    receipt_body = {
        "receipt_version": "integrity.receipt/1",
        "log_id": "log-test",
        "seq": 0,
        "prev_hash": "0x" + "00" * 32,
        "timestamp": "2026-09-29T00:00:00Z",
        "agent_did": "did:integrity:test",
        "device_id_hmac": "hmac-sha256:" + "11" * 32,
        "action_hmac": "hmac-sha256:" + "22" * 32,
        "event_class": "test",
        "pack_hash": "pack-test",
        "decision": "permit",
        "reason_code": "TEST_OK",
        "mode": "enforce",
        "controls": [],
        "checkpoint_reference": None,
        "signer_key": signer,
    }
    receipt = _sign(key, b"integrity.receipt.v1\x00", receipt_body)
    receipt_hash = "0x" + keccak(jcs.canonicalize(receipt)).hex()
    leaf = keccak(keccak(b"integrity.merkle.receipt.v2|" + bytes.fromhex(receipt_hash[2:])))
    checkpoint_body = {
        "checkpoint_version": "integrity.checkpoint/1",
        "log_id": "log-test",
        "tree_size": 1,
        "root": "0x" + leaf.hex(),
        "last_receipt_hash": receipt_hash,
        "timestamp": "2026-09-29T00:00:01Z",
        "signer_key": signer,
    }
    checkpoint = _sign(key, b"integrity.checkpoint.v1\x00", checkpoint_body)
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps({"receipts": [receipt], "checkpoint": checkpoint}))
    proof_path = tmp_path / "proof.json"
    proof_path.write_text(json.dumps({"receipt": receipt, "proof": [], "checkpoint": checkpoint}))
    return bundle_path, proof_path, signer, checkpoint["root"]


def test_verify_receipt_bundle_checkpoint_proof_and_anchor(tmp_path):
    bundle, proof, signer, root = _bundle(tmp_path)
    result = runner.invoke(app, [
        "verify", "--receipts", str(bundle), "--trusted-signer", signer,
        "--proof", str(proof), "--anchor-root", root, "--json-output",
    ])
    assert result.exit_code == 0, result.stdout
    document = json.loads(result.stdout)
    assert document["valid"] is True
    assert document["signature"] == "pass"
    assert document["chain"] == "pass"
    assert document["checkpoint"] == "pass"
    assert document["inclusion"] == "pass"
    assert document["anchor"] == "pass"


def test_verify_rejects_tampered_receipt(tmp_path):
    bundle, _proof, signer, _root = _bundle(tmp_path)
    document = json.loads(bundle.read_text())
    document["receipts"][0]["decision"] = "deny"
    bundle.write_text(json.dumps(document))
    result = runner.invoke(app, [
        "verify", "--receipts", str(bundle), "--trusted-signer", signer, "--json-output",
    ])
    assert result.exit_code == 1
    output = json.loads(result.stdout)
    assert output["valid"] is False
    assert output["error"]["code"] == "BAD_SIGNATURE"


def test_verify_reads_local_state_anchor(tmp_path, monkeypatch):
    bundle, proof, signer, root = _bundle(tmp_path)

    class _Call:
        def __init__(self, value):
            self.value = value

        def call(self):
            return self.value

    class _Functions:
        def latestRoot(self):
            return _Call(bytes.fromhex(root[2:]))

        def verifyLeaf(self, supplied_root, leaf, proof_nodes):
            assert supplied_root == bytes.fromhex(root[2:])
            assert len(leaf) == 32
            assert proof_nodes == []
            return _Call(True)

    class _Anchor:
        functions = _Functions()

    class _W3:
        def is_connected(self):
            return True

    monkeypatch.setattr(main_module.chain, "get_w3", lambda _url: _W3())
    monkeypatch.setattr(main_module.chain, "_contract", lambda *_args, **_kwargs: _Anchor())
    result = runner.invoke(app, [
        "verify", "--receipts", str(bundle), "--trusted-signer", signer,
        "--proof", str(proof), "--anchor-contract", "0x" + "11" * 20,
        "--json-output",
    ])
    assert result.exit_code == 0, result.stdout
    document = json.loads(result.stdout)
    assert document["anchor"] == "pass"
    assert document["anchor_scope"] == "local_rpc"
