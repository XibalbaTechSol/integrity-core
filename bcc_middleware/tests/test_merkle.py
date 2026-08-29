"""Tests for app/merkle.py -- keccak256 sorted-pair Merkle tree (§4.4)."""

from eth_utils import keccak

from app.merkle import MerkleBatcher, _hash_pair, leaf_hash, merkle_root
from tests.helpers import make_commitment_model, new_agent, sign_commitment


def _commitment(nonce: int) -> object:
    agent_id, private_key = new_agent()
    payload = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=nonce)
    return make_commitment_model(**payload)


def test_hash_pair_is_order_independent():
    a = keccak(b"a")
    b = keccak(b"b")
    assert _hash_pair(a, b) == _hash_pair(b, a)


def test_hash_pair_matches_manual_sorted_concatenation():
    a = keccak(b"leaf-a")
    b = keccak(b"leaf-b")
    expected = keccak((a + b) if a < b else (b + a))
    assert _hash_pair(a, b) == expected


def test_merkle_root_of_single_leaf_is_the_leaf_itself():
    leaf = keccak(b"only-leaf")
    assert merkle_root([leaf]) == leaf


def test_merkle_root_of_two_leaves_is_their_sorted_pair_hash():
    a = keccak(b"leaf-a")
    b = keccak(b"leaf-b")
    assert merkle_root([a, b]) == _hash_pair(a, b)


def test_merkle_root_with_odd_leaf_count_duplicates_last_node():
    a, b, c = keccak(b"1"), keccak(b"2"), keccak(b"3")
    # level 1: [hash(a,b), hash(c,c)]  (c has no pair, duplicated rather
    # than promoted unhashed -- the OpenZeppelin-standard convention that
    # matches `integrity-oracle`'s `merkle.rs` and `contracts`'
    # `StateAnchor.sol` bit-for-bit.)
    # level 0 (root): hash(hash(a,b), hash(c,c))
    expected = _hash_pair(_hash_pair(a, b), _hash_pair(c, c))
    assert merkle_root([a, b, c]) == expected


def test_merkle_root_with_odd_leaf_count_does_not_promote_unhashed():
    # Guards against regressing to the old (wrong) "promote unchanged"
    # convention: the duplicate-node root must differ from what promoting
    # the odd leaf unhashed into the next level would produce.
    a, b, c = keccak(b"1"), keccak(b"2"), keccak(b"3")
    duplicated_root = merkle_root([a, b, c])
    promoted_unchanged_root = _hash_pair(_hash_pair(a, b), c)
    assert duplicated_root != promoted_unchanged_root


def test_merkle_root_with_larger_odd_leaf_count():
    # 7 leaves: one odd-node-count level is exercised (7 -> 4, via the
    # duplicated leaves[6]); 4 -> 2 -> 1 are all even, mirroring the
    # oracle's Rust test.
    leaves = [keccak(bytes([i])) for i in range(7)]
    level1 = [
        _hash_pair(leaves[0], leaves[1]),
        _hash_pair(leaves[2], leaves[3]),
        _hash_pair(leaves[4], leaves[5]),
        _hash_pair(leaves[6], leaves[6]),
    ]
    level2 = [_hash_pair(level1[0], level1[1]), _hash_pair(level1[2], level1[3])]
    expected_root = _hash_pair(level2[0], level2[1])
    assert merkle_root(leaves) == expected_root


def test_leaf_hash_is_deterministic_for_the_same_commitment_fields():
    commitment = _commitment(nonce=42)
    assert leaf_hash(commitment) == leaf_hash(commitment)


def test_leaf_hash_differs_for_different_nonces():
    agent_id, private_key = new_agent()
    c1 = make_commitment_model(**sign_commitment(private_key, agent_id=agent_id, nonce=1))
    c2 = make_commitment_model(**sign_commitment(private_key, agent_id=agent_id, nonce=2))
    assert leaf_hash(c1) != leaf_hash(c2)


def test_batcher_flushes_at_batch_size_and_computes_a_root():
    batcher = MerkleBatcher(batch_size=3)
    for i in range(3):
        assert batcher.add(_commitment(nonce=i)) == i
    assert batcher.is_full()

    flushed = batcher.flush()
    assert flushed is not None
    root, leaves = flushed
    assert len(leaves) == 3
    assert root == merkle_root([leaf.leaf_hash for leaf in leaves])
    assert batcher.pending_count == 0


def test_batcher_flush_on_empty_batch_returns_none():
    batcher = MerkleBatcher(batch_size=3)
    assert batcher.flush() is None


# --- concurrent access (PRODUCTION_GAPS.md §5) ----------------------------------------


def test_batcher_concurrent_add_and_flush_never_loses_or_duplicates_a_leaf():
    """
    Real regression test for the thread-safety `app/main.py`'s move of
    `_flush_and_anchor` onto an `asyncio.to_thread` worker made necessary:
    many threads calling `add()` concurrently with other threads repeatedly
    calling `flush()` on the SAME batcher. Every leaf that goes in via
    `add()` must come back out via exactly one `flush()` call (or remain in
    `pending_count` if never flushed) -- never both lost and never
    double-counted. batch_size is set impractically high so `add()` never
    triggers a size-based auto-full state on its own; flushing here is
    driven entirely by the concurrent `_flusher` thread, which is what
    exercises the actual race window (add() interleaved with flush()'s
    check-then-act swap).
    """
    import threading

    batcher = MerkleBatcher(batch_size=1_000_000)
    total_leaves = 400
    commitments = [_commitment(nonce=i) for i in range(total_leaves)]

    flushed_leaves: list = []
    flush_lock = threading.Lock()
    stop_flushing = threading.Event()

    def _adder(chunk: list) -> None:
        for c in chunk:
            batcher.add(c)

    def _flusher() -> None:
        while not stop_flushing.is_set():
            result = batcher.flush()
            if result is not None:
                _, leaves = result
                with flush_lock:
                    flushed_leaves.extend(leaves)

    chunk_size = 20
    chunks = [commitments[i : i + chunk_size] for i in range(0, total_leaves, chunk_size)]
    adders = [threading.Thread(target=_adder, args=(chunk,)) for chunk in chunks]
    flushers = [threading.Thread(target=_flusher) for _ in range(4)]

    for f in flushers:
        f.start()
    for a in adders:
        a.start()
    for a in adders:
        a.join(timeout=30)
    stop_flushing.set()
    for f in flushers:
        f.join(timeout=30)

    # Whatever's still pending after adders finish and flushers stop counts too.
    final = batcher.flush()
    if final is not None:
        flushed_leaves.extend(final[1])

    recovered_hashes = sorted(leaf.leaf_hash for leaf in flushed_leaves)
    expected_hashes = sorted(leaf_hash(c) for c in commitments)
    assert len(recovered_hashes) == total_leaves, (
        f"expected {total_leaves} leaves recovered across all flushes, got {len(recovered_hashes)} "
        "-- a leaf was lost or duplicated under concurrent add()/flush()"
    )
    assert recovered_hashes == expected_hashes
