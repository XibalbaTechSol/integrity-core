"""SDK core: canonical bytes (C1) and the protocol's one Merkle convention."""

from __future__ import annotations

import collections
import json
import math
from pathlib import Path

import pytest

from integrity_sdk import bcc
from integrity_sdk.core import jcs, merkle

VECTORS = Path(__file__).resolve().parents[3] / "spec" / "vault-merkle" / "vectors.json"


def _hex(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("0x"))


# --------------------------------------------------------------------------- keccak / Merkle ---


def test_keccak256_is_the_ethereum_variant_not_nist_sha3():
    # keccak256("") from the Ethereum yellow paper; NIST SHA3-256("") is a7ffc6f8... instead.
    assert merkle.keccak256(b"").hex() == "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"


def test_every_shared_vector_verifies():
    # The same file contracts/test/VaultMerkle.t.sol feeds to StateAnchor.verifyLeaf on-chain.
    vectors = json.loads(VECTORS.read_text())["vectors"]
    assert vectors
    for vector in vectors:
        proof = [_hex(node) for node in vector["proof"]]
        assert merkle.verify_leaf(_hex(vector["root"]), _hex(vector["leaf"]), proof), vector


def test_root_and_proofs_rebuild_exactly_where_vectors_cover_every_leaf():
    by_count = collections.defaultdict(dict)
    roots = {}
    for vector in json.loads(VECTORS.read_text())["vectors"]:
        by_count[vector["leaf_count"]][vector["index"]] = vector
        roots[vector["leaf_count"]] = vector["root"]
    complete = {count: v for count, v in by_count.items() if set(v) == set(range(count))}
    assert complete, "expected at least one leaf count with full index coverage"
    for count, vectors in complete.items():
        leaves = [_hex(vectors[i]["leaf"]) for i in range(count)]
        assert "0x" + merkle.merkle_root(leaves).hex() == roots[count]
        for index in range(count):
            assert ["0x" + n.hex() for n in merkle.merkle_proof(leaves, index)] == vectors[index]["proof"]


def test_odd_node_is_promoted_so_a_duplicated_last_leaf_cannot_be_proven():
    leaves = [merkle.leaf_hash("test", bytes([i])) for i in range(3)]
    root = merkle.merkle_root(leaves)
    # Under the duplicate-last-node convention, [A, B, C] would also accept a 4th leaf == C.
    duplicated_root = merkle.hash_pair(merkle.hash_pair(leaves[0], leaves[1]), merkle.hash_pair(leaves[2], leaves[2]))
    assert root != duplicated_root
    assert merkle.merkle_proof(leaves, 2) == [merkle.hash_pair(leaves[0], leaves[1])]


def test_leaf_hash_is_domain_separated_and_double_hashed():
    assert merkle.leaf_hash("receipt", b"x") != merkle.leaf_hash("memory", b"x")
    assert merkle.leaf_hash("receipt", b"x") == merkle.keccak256(merkle.keccak256(b"integrity.merkle.receipt.v2|x"))
    with pytest.raises(ValueError):
        merkle.leaf_hash("Bad Kind", b"x")


def test_vault_reuses_the_core_implementation():
    from integrity_sdk import vault

    assert vault.merkle_root is merkle.merkle_root
    assert vault.verify_leaf is merkle.verify_leaf


# --------------------------------------------------------------------------------- JCS (C1) ---


def test_jcs_orders_keys_and_emits_utf8():
    assert jcs.canonical_bytes({"b": 1, "a": "é", "c": [True, None]}) == '{"a":"é","b":1,"c":[true,null]}'.encode()


def test_jcs_folds_integral_floats_and_rejects_non_finite_numbers():
    assert jcs.canonical_bytes({"x": 2.0}) == b'{"x":2}'
    assert jcs.canonical_bytes({"x": 0.5}) == b'{"x":0.5}'
    for bad in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError):
            jcs.canonical_bytes({"x": bad})


def test_rfc8785_sort_order_is_utf16_code_units():
    # RFC 8785 §3.2.3 sorts by UTF-16 code units: U+10000 (surrogate pair D800 DC00) sorts
    # before U+FFFF, the reverse of code-point order.
    assert jcs.canonical_bytes({"￿": 1, "\U00010000": 2}) == '{"\U00010000":2,"￿":1}'.encode()


def test_bcc_uses_the_single_jcs_implementation():
    value = {"intent": "tool_call", "n": 3.0, "text": "naïve"}
    assert bcc.canonical_json_bytes(value) == jcs.canonical_bytes(value)
    assert jcs.sha256_hex(value).startswith("sha256:")
