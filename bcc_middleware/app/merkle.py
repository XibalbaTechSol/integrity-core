"""
Merkle batch construction, per docs/INTERFACE_CONTRACT.md §4.4.

This MUST match `integrity-oracle` and `contracts` bit-for-bit, since the
root computed here gets verified on-chain against whatever `contracts`'
`StateAnchor.sol` + OpenZeppelin `MerkleProof.verify` expect. The two rules
from §4.4 this module implements exactly:

  1. Hash function: keccak256 (not sha256 -- it's cheap/native in the EVM,
     and what `MerkleProof.verify` uses).
  2. Parent hashing sorts each child pair ascending before concatenating:
     `keccak256(a < b ? a,b : b,a)`. This is the OpenZeppelin convention:
     it makes leaf position irrelevant to the proof, avoids a
     second-preimage ordering ambiguity, and lets `contracts` verify with
     the stock OZ `MerkleProof` library instead of a custom verifier.

*** INTEGRATION FLAG: leaf encoding ***
§4.4 pins down the hash function and pairing rule but not the exact leaf
*payload* -- what fields get packed into each leaf before hashing is a
cross-package agreement between bcc_middleware (which produces leaves),
integrity-oracle (which likely also builds/verifies batches for scoring),
and contracts (whose `StateAnchor.sol` treats the root as opaque, but
whoever submits a MerkleProof against a leaf needs to reconstruct it
identically). This module's leaf encoding is documented immediately below
`leaf_hash()` -- confirm it during integration before anyone relies on
proofs generated against these leaves.

*** ODD-NODE-COUNT CONVENTION ***
When a level has an odd number of nodes, this implementation duplicates the
last, unpaired node (i.e. it hashes it with itself) rather than promoting it
unchanged. This is the OpenZeppelin-standard convention: it matches
`integrity-oracle`'s `merkle.rs` and `contracts`' `StateAnchor.sol`
bit-for-bit, and it keeps every level a keccak256 output, so a proof step is
always a `_hash_pair` call with no special-casing for odd levels.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from eth_utils import keccak

from app.schemas import BCCCommitment


@dataclass(frozen=True)
class BatchLeaf:
    commitment: BCCCommitment
    leaf_hash: bytes


def leaf_hash(commitment: BCCCommitment) -> bytes:
    """
    keccak256(abi.encodePacked(agent_id, intent_type, intended_state_hash,
    nonce, timestamp)).

    We hand-roll the packed encoding (rather than pulling in a
    solidity-ABI-packed helper) because it's simple for this fixed set of
    types and avoids a version-sensitive dependency:
      - `agent_id`, `intent_type`: raw UTF-8 bytes, no length prefix
        (that's what `abi.encodePacked` does for `string`/`bytes`).
      - `intended_state_hash`: the 32 raw bytes the hex string encodes
        (already a `bytes32` on the wire).
      - `nonce`, `timestamp`: big-endian 32-byte (`uint256`) encoding.
    """
    packed = (
        commitment.agent_id.encode("utf-8")
        + commitment.intent_type.encode("utf-8")
        + bytes.fromhex(commitment.intended_state_hash.removeprefix("0x"))
        + commitment.nonce.to_bytes(32, "big")
        + commitment.timestamp.to_bytes(32, "big")
    )
    return keccak(packed)


def _hash_pair(a: bytes, b: bytes) -> bytes:
    """Sorted-pair keccak256, per §4.4."""
    return keccak((a + b) if a < b else (b + a))


def merkle_root(leaves: list[bytes]) -> bytes:
    """
    Computes the root for a list of leaf hashes (already hashed via
    `leaf_hash`, not raw leaf data). Empty input has no defined root --
    callers should not call this with an empty batch.
    """
    if not leaves:
        raise ValueError("cannot compute a merkle root over zero leaves")
    level = list(leaves)
    while len(level) > 1:
        next_level: list[bytes] = []
        for i in range(0, len(level) - 1, 2):
            next_level.append(_hash_pair(level[i], level[i + 1]))
        if len(level) % 2 == 1:
            # Odd one out: duplicate it (hash it with itself) rather than
            # promoting it unhashed, matching the OpenZeppelin-standard
            # convention used by `integrity-oracle`'s `merkle.rs` and
            # `contracts`' `StateAnchor.sol` -- see module docstring.
            next_level.append(_hash_pair(level[-1], level[-1]))
        level = next_level
    return level[0]


class MerkleBatcher:
    """
    Accumulates approved commitments and flushes a batch (computing its
    root) once `batch_size` is reached, or on demand via `flush()`.

    This class only builds batches and hands roots to the caller -- it does
    NOT submit transactions itself (see anchor.py for that), so it has no
    opinion about chain connectivity and is trivially unit-testable.

    Thread-safe (`threading.Lock` around every mutation/read of `_pending`).
    This was NOT always necessary: `add`/`flush` used to only ever run
    sequentially on `run_intercept`'s single-threaded synchronous path. Once
    `_flush_and_anchor` was moved onto a thread-pool worker via
    `asyncio.to_thread` (PRODUCTION_GAPS.md §5's blocking-hot-path fix), a
    second request's `add()` (still running on the event-loop thread) can
    genuinely interleave with an in-flight `flush()`'s check-then-act
    sequence -- CPython's GIL makes individual list ops atomic, but NOT the
    multi-op `batch, self._pending = self._pending, []` swap, so an
    unguarded interleaving can attach a freshly-added leaf to the batch
    that's about to be flushed (silently misattributing/losing it from the
    NEW pending list) or hand back a `batch_index` computed against a list
    that's about to be swapped out from under it.
    """

    def __init__(self, batch_size: int) -> None:
        self.batch_size = batch_size
        self._pending: list[BatchLeaf] = []
        self._lock = threading.Lock()

    def add(self, commitment: BCCCommitment) -> int:
        """Adds a commitment to the pending batch. Returns its index within the batch."""
        entry = BatchLeaf(commitment=commitment, leaf_hash=leaf_hash(commitment))
        with self._lock:
            self._pending.append(entry)
            return len(self._pending) - 1

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    def is_full(self) -> bool:
        with self._lock:
            return len(self._pending) >= self.batch_size

    def reset(self) -> None:
        """Test/admin hook: discards any pending (unflushed) leaves."""
        with self._lock:
            self._pending = []

    def flush(self) -> tuple[bytes, list[BatchLeaf]] | None:
        """
        Pops the entire current batch and returns (root, leaves), or None if
        there's nothing pending. Root computation happens here so a caller
        that fails to anchor can still know what root it *would* have
        submitted (useful for retry/logging).
        """
        with self._lock:
            if not self._pending:
                return None
            batch, self._pending = self._pending, []
        root = merkle_root([leaf.leaf_hash for leaf in batch])
        return root, batch
