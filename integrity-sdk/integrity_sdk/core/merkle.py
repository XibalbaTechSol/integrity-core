"""Merkle trees in the protocol's one convention (OpenZeppelin semantics).

This is the convention `StateAnchor.verifyLeaf` checks on-chain, pinned by the
cross-implementation vectors in `spec/vault-merkle/vectors.json` and specified
in `docs/design/merkle-standardization.md` §2:

1. hash: keccak-256 (the Ethereum variant, *not* NIST SHA3-256, which pads
   differently);
2. parents: sorted pair, `keccak256(min(a, b) || max(a, b))`, so stock
   OpenZeppelin `MerkleProof.verify` accepts the proofs
   (https://docs.openzeppelin.com/contracts/5.x/api/utils#MerkleProof);
3. an odd node is promoted unchanged, never duplicated -- duplicating would let
   a tree over [A, B, C] prove a nonexistent fourth leaf equal to C;
4. new leaf kinds are double-hashed and domain-separated:
   `keccak256(keccak256("integrity.merkle.<kind>.v2|" || preimage))`. Double
   hashing keeps a 64-byte internal node from ever being presented as a leaf.

Sorted pairs make the root a function of the *set* of leaves, not their order.
Anything whose position matters must therefore carry it inside the leaf (a
receipt carries its own `seq` and `prev_hash`).

keccak comes from pycryptodome rather than eth-utils, so this module stays in
the dependency-light SDK core.
"""

from __future__ import annotations

import re
from typing import List, Sequence

from Crypto.Hash import keccak as _keccak

_KIND_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")


def keccak256(data: bytes) -> bytes:
    """Ethereum keccak-256 (original Keccak padding)."""
    return _keccak.new(digest_bits=256, data=data).digest()


def leaf_hash(kind: str, preimage: bytes) -> bytes:
    """Domain-separated, double-hashed leaf for a new leaf kind (convention rules 4-5)."""
    if not _KIND_RE.fullmatch(kind):
        raise ValueError(f"invalid Merkle leaf kind {kind!r}")
    return keccak256(keccak256(f"integrity.merkle.{kind}.v2|".encode("ascii") + preimage))


def hash_pair(a: bytes, b: bytes) -> bytes:
    """Parent hash with the pair sorted ascending (OpenZeppelin `_hashPair`)."""
    return keccak256(a + b) if a < b else keccak256(b + a)


def merkle_root(leaves: Sequence[bytes]) -> bytes:
    """Root over already-hashed leaves, promoting an odd node at each level."""
    if not leaves:
        raise ValueError("cannot compute a Merkle root over zero leaves")
    level = list(leaves)
    while len(level) > 1:
        parents: List[bytes] = [hash_pair(level[i], level[i + 1]) for i in range(0, len(level) - 1, 2)]
        if len(level) % 2 == 1:
            parents.append(level[-1])
        level = parents
    return level[0]


def merkle_proof(leaves: Sequence[bytes], index: int) -> List[bytes]:
    """Sibling path for `leaves[index]`, verifiable by `verify_leaf` and `StateAnchor.verifyLeaf`."""
    if not 0 <= index < len(leaves):
        raise IndexError(f"leaf index {index} out of range for {len(leaves)} leaves")
    proof: List[bytes] = []
    level = list(leaves)
    position = index
    while len(level) > 1:
        parents: List[bytes] = []
        for i in range(0, len(level) - 1, 2):
            if position in (i, i + 1):
                proof.append(level[i + 1] if position == i else level[i])
                position = len(parents)
            parents.append(hash_pair(level[i], level[i + 1]))
        if len(level) % 2 == 1:
            if position == len(level) - 1:
                position = len(parents)  # promoted unchanged: no sibling at this level
            parents.append(level[-1])
        level = parents
    return proof


def verify_leaf(root: bytes, leaf: bytes, proof: Sequence[bytes]) -> bool:
    """Local mirror of `StateAnchor.verifyLeaf` / OpenZeppelin `MerkleProof.verify`."""
    computed = leaf
    for sibling in proof:
        computed = hash_pair(computed, sibling)
    return computed == root
