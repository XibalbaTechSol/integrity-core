"""Trust Vault — leaves, the two-level Merkle structure, and anchor bookkeeping.

The property that matters most: roots and proofs produced here must be accepted by
`StateAnchor.verifyLeaf` on-chain. A convention mismatch would produce roots that anchor
successfully and then fail every verification — silent, and expensive to discover later. The
sorted-pair tests below pin that convention.
"""

from __future__ import annotations

import pytest
from eth_utils import keccak

from integrity_sdk.vault import (
    TrustVault,
    VaultLeaf,
    hash_pair,
    merkle_proof,
    merkle_root,
    verify_leaf,
)


# --- Merkle convention (must match StateAnchor / OpenZeppelin) ---------------------------


def test_pair_hashing_is_order_independent() -> None:
    a, b = keccak(text="a"), keccak(text="b")
    assert hash_pair(a, b) == hash_pair(b, a), "parents sort the pair; order must not matter"


def test_root_matches_hand_computed_tree() -> None:
    """Four leaves, computed by hand with the same convention StateAnchor.t.sol uses."""
    leaves = [keccak(text=x) for x in ("l0", "l1", "l2", "l3")]
    expected = hash_pair(hash_pair(leaves[0], leaves[1]), hash_pair(leaves[2], leaves[3]))
    assert merkle_root(leaves) == expected


def test_single_leaf_root_is_the_leaf() -> None:
    leaf = keccak(text="only")
    assert merkle_root([leaf]) == leaf


def test_odd_node_is_promoted_not_duplicated() -> None:
    """Duplicating an odd node would let a tree over [A,B,C] verify a proof for a fourth leaf
    equal to C — a forgery vector, not a style preference."""
    leaves = [keccak(text=x) for x in ("a", "b", "c")]
    expected = hash_pair(hash_pair(leaves[0], leaves[1]), leaves[2])
    assert merkle_root(leaves) == expected


def test_empty_tree_raises_rather_than_returning_a_root() -> None:
    with pytest.raises(ValueError):
        merkle_root([])


@pytest.mark.parametrize("count", [1, 2, 3, 4, 5, 8, 9, 17])
def test_every_leaf_proves_against_the_root(count: int) -> None:
    """Odd counts included deliberately — promotion is where an off-by-one hides."""
    leaves = [keccak(text=f"leaf-{i}") for i in range(count)]
    root = merkle_root(leaves)
    for i, leaf in enumerate(leaves):
        assert verify_leaf(root, leaf, merkle_proof(leaves, i)), f"leaf {i} of {count} failed"


def test_a_leaf_not_in_the_tree_does_not_verify() -> None:
    leaves = [keccak(text=f"leaf-{i}") for i in range(4)]
    root = merkle_root(leaves)
    assert not verify_leaf(root, keccak(text="never-added"), merkle_proof(leaves, 0))


# --- Leaves -------------------------------------------------------------------------------


def test_commit_leaf_is_deterministic_and_field_sensitive() -> None:
    a = VaultLeaf.for_commit("task-1", "abc123", "tests-ok", timestamp=1700)
    b = VaultLeaf.for_commit("task-1", "abc123", "tests-ok", timestamp=1700)
    assert a.leaf_hash == b.leaf_hash

    for changed in (
        VaultLeaf.for_commit("task-2", "abc123", "tests-ok", timestamp=1700),
        VaultLeaf.for_commit("task-1", "def456", "tests-ok", timestamp=1700),
        VaultLeaf.for_commit("task-1", "abc123", "tests-FAILED", timestamp=1700),
        VaultLeaf.for_commit("task-1", "abc123", "tests-ok", timestamp=1701),
    ):
        assert changed.leaf_hash != a.leaf_hash, "every field must be committed to"


def test_field_boundaries_cannot_collide() -> None:
    """Concatenating without a separator would make ("ab","c") and ("a","bc") identical."""
    x = VaultLeaf.for_commit("ab", "c", "h", timestamp=1)
    y = VaultLeaf.for_commit("a", "bc", "h", timestamp=1)
    assert x.leaf_hash != y.leaf_hash


# --- Two-level vault ----------------------------------------------------------------------


def test_pending_leaves_and_session_root(tmp_path) -> None:
    v = TrustVault("did:integrity:test", home=tmp_path)
    assert v.session_root() is None, "nothing pending means no root, not a root over nothing"

    for i in range(3):
        v.append(VaultLeaf.for_commit(f"task-{i}", f"sha{i}", "ok", timestamp=1000 + i))

    pending = v.pending_leaves()
    assert len(pending) == 3
    assert v.session_root() == merkle_root([leaf.hash_bytes() for leaf in pending])


def test_anchoring_advances_the_pending_window(tmp_path) -> None:
    v = TrustVault("did:integrity:test", home=tmp_path)
    for i in range(2):
        v.append(VaultLeaf.for_commit(f"t{i}", f"s{i}", "ok", timestamp=1000 + i))

    root = v.session_root()
    v.record_anchor(root, "0xdeadbeef", epoch=2)

    assert v.pending_leaves() == [], "anchored leaves must not be re-anchored"
    assert v.session_root() is None

    v.append(VaultLeaf.for_commit("t2", "s2", "ok", timestamp=2000))
    assert len(v.pending_leaves()) == 1, "only the new leaf is pending"


def test_leaf_log_is_append_only_across_anchors(tmp_path) -> None:
    v = TrustVault("did:integrity:test", home=tmp_path)
    v.append(VaultLeaf.for_commit("t0", "s0", "ok", timestamp=1))
    v.record_anchor(v.session_root(), "0xaaa", epoch=2)
    v.append(VaultLeaf.for_commit("t1", "s1", "ok", timestamp=2))

    assert len(v.all_leaves()) == 2, "anchoring must never truncate history"


def test_proof_resolves_against_the_batch_that_was_anchored(tmp_path) -> None:
    """Two anchored sessions: a leaf must prove against ITS session's root, not a later one."""
    v = TrustVault("did:integrity:test", home=tmp_path)
    first = [VaultLeaf.for_commit(f"a{i}", f"s{i}", "ok", timestamp=100 + i) for i in range(3)]
    for leaf in first:
        v.append(leaf)
    root1 = v.session_root()
    v.record_anchor(root1, "0xaaa", epoch=2)

    second = [VaultLeaf.for_commit(f"b{i}", f"t{i}", "ok", timestamp=200 + i) for i in range(2)]
    for leaf in second:
        v.append(leaf)
    root2 = v.session_root()
    v.record_anchor(root2, "0xbbb", epoch=3)

    assert root1 != root2

    p = v.proof_for(first[1])
    assert p["root"] == "0x" + root1.hex()
    assert p["tx_hash"] == "0xaaa"
    assert verify_leaf(root1, first[1].hash_bytes(), [bytes.fromhex(x[2:]) for x in p["proof"]])

    q = v.proof_for(second[0])
    assert q["root"] == "0x" + root2.hex()


def test_pending_leaf_has_no_proof(tmp_path) -> None:
    """A proof against a root nobody anchored is worthless — return None rather than pretend."""
    v = TrustVault("did:integrity:test", home=tmp_path)
    leaf = VaultLeaf.for_commit("t", "s", "ok", timestamp=1)
    v.append(leaf)
    assert v.proof_for(leaf) is None


def test_separate_agents_do_not_share_a_vault(tmp_path) -> None:
    a = TrustVault("did:integrity:aaa", home=tmp_path)
    b = TrustVault("did:integrity:bbb", home=tmp_path)
    a.append(VaultLeaf.for_commit("t", "s", "ok", timestamp=1))
    assert b.all_leaves() == []
