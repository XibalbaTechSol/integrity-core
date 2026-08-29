"""
Trust Vault — the agent's own append-only memory, and the Merkle machinery that makes it
provable without revealing it.

Spec v0.4 §4.1/§7: the agent controls a durable vault whose *commitments* are anchored on its
own `StateAnchor`. Content stays local and agent-controlled; only roots go on-chain. Anchoring
every leaf would be prohibitively expensive, so leaves accumulate locally and are anchored as a
batch — which is why this module exists rather than the SDK calling `anchorRoot` directly.

**Two-level structure.** Leaves are per unit of work (a commit); leaves accumulate into a
session subtree; the subtree root is anchored once per session. That keeps commit-level
provability — any single commit can be proven to have been in an anchored root — while
anchoring at session cadence rather than per commit.

**Merkle convention must match `StateAnchor` bit-for-bit** (docs/INTERFACE_CONTRACT.md §4.4):
`keccak256` leaves, and parents hashed with the pair sorted ascending, so OpenZeppelin's
`MerkleProof.verify` accepts a proof produced here. A mismatch would produce roots that anchor
fine and then fail every verification — silent and expensive to discover.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from eth_utils import keccak


def _vault_home() -> Path:
    return Path(os.environ.get("INTEGRITY_VAULT_HOME", str(Path.home() / ".integrity" / "vault")))


def hash_pair(a: bytes, b: bytes) -> bytes:
    """Parent hash with the pair sorted ascending — the OpenZeppelin convention.

    Sorting (rather than positional left/right) means a verifier does not need to know which
    side a sibling was on, and it closes the ambiguity where two different trees could be built
    from one leaf set by permuting children. The root becomes a function of the *set* of leaves.
    """
    return keccak(a + b) if a < b else keccak(b + a)


def merkle_root(leaves: Sequence[bytes]) -> bytes:
    """Root over pre-hashed leaves, matching `StateAnchor.verifyLeaf`.

    An odd node at any level is promoted unchanged rather than duplicated. Duplicating it — the
    other common convention — makes a tree with leaves [A, B, C] verify a proof for a
    non-existent fourth leaf equal to C, which is a real forgery vector, not a style choice.
    """
    if not leaves:
        raise ValueError("cannot compute a Merkle root over zero leaves")
    level = list(leaves)
    while len(level) > 1:
        nxt: List[bytes] = []
        for i in range(0, len(level) - 1, 2):
            nxt.append(hash_pair(level[i], level[i + 1]))
        if len(level) % 2 == 1:
            nxt.append(level[-1])
        level = nxt
    return level[0]


def merkle_proof(leaves: Sequence[bytes], index: int) -> List[bytes]:
    """Sibling path for `leaves[index]`, verifiable by `StateAnchor.verifyLeaf`."""
    if not 0 <= index < len(leaves):
        raise IndexError(f"leaf index {index} out of range for {len(leaves)} leaves")
    proof: List[bytes] = []
    level = list(leaves)
    idx = index
    while len(level) > 1:
        nxt: List[bytes] = []
        for i in range(0, len(level) - 1, 2):
            if i == idx or i + 1 == idx:
                proof.append(level[i + 1] if i == idx else level[i])
                idx = len(nxt)
            nxt.append(hash_pair(level[i], level[i + 1]))
        if len(level) % 2 == 1:
            if idx == len(level) - 1:
                idx = len(nxt)  # promoted unchanged; no sibling to add
            nxt.append(level[-1])
        level = nxt
    return proof


def verify_leaf(root: bytes, leaf: bytes, proof: Sequence[bytes]) -> bool:
    """Local mirror of `StateAnchor.verifyLeaf`, for checking a proof before submitting it."""
    computed = leaf
    for sibling in proof:
        computed = hash_pair(computed, sibling)
    return computed == root


@dataclass(frozen=True)
class VaultLeaf:
    """One unit of development work.

    `leaf_hash` commits to the tuple; the fields are kept alongside it locally so a proof can be
    explained later. Only the hash ever leaves this machine.
    """

    kind: str
    task_id: str
    commit_sha: str
    test_result_hash: str
    timestamp: int
    leaf_hash: str

    @staticmethod
    def for_commit(task_id: str, commit_sha: str, test_result_hash: str, timestamp: Optional[int] = None) -> "VaultLeaf":
        ts = int(timestamp if timestamp is not None else time.time())
        # Domain-separated: a leaf hash must not be reinterpretable as a leaf of another kind
        # once more kinds exist. Fields are joined with a separator that cannot appear in the
        # hex/id components, so ("ab","c") and ("a","bc") cannot collide.
        preimage = "|".join(["integrity.vault.commit.v1", task_id, commit_sha, test_result_hash, str(ts)])
        return VaultLeaf(
            kind="commit",
            task_id=task_id,
            commit_sha=commit_sha,
            test_result_hash=test_result_hash,
            timestamp=ts,
            leaf_hash="0x" + keccak(text=preimage).hex(),
        )

    def hash_bytes(self) -> bytes:
        return bytes.fromhex(self.leaf_hash.removeprefix("0x"))


class TrustVault:
    """Append-only local vault for one agent, with anchor bookkeeping.

    Two files, both under `~/.integrity/vault/<agent_id>/`:
      * `leaves.jsonl`  — every leaf ever appended, append-only
      * `anchors.jsonl` — each anchored root with the leaf range it covered

    Splitting them means the leaf log is never rewritten, which is what makes "append-only"
    true of the file and not merely of the intent.
    """

    def __init__(self, agent_id: str, home: Optional[Path] = None):
        safe = agent_id.replace(":", "_").replace("/", "_")
        self.agent_id = agent_id
        self.dir = (home or _vault_home()) / safe
        self.dir.mkdir(parents=True, exist_ok=True)
        self.leaves_path = self.dir / "leaves.jsonl"
        self.anchors_path = self.dir / "anchors.jsonl"

    def append(self, leaf: VaultLeaf) -> None:
        with self.leaves_path.open("a") as f:
            f.write(json.dumps(asdict(leaf)) + "\n")

    def all_leaves(self) -> List[VaultLeaf]:
        if not self.leaves_path.exists():
            return []
        return [VaultLeaf(**json.loads(line)) for line in self.leaves_path.read_text().splitlines() if line.strip()]

    def anchored_count(self) -> int:
        """How many leaves previous anchors already covered.

        Stored as a count rather than recomputed, so a partially-failed anchor cannot silently
        re-anchor leaves that were already committed to.
        """
        if not self.anchors_path.exists():
            return 0
        total = 0
        for line in self.anchors_path.read_text().splitlines():
            if line.strip():
                total = max(total, json.loads(line)["leaves_through"])
        return total

    def pending_leaves(self) -> List[VaultLeaf]:
        """Leaves appended since the last successful anchor."""
        return self.all_leaves()[self.anchored_count():]

    def session_root(self) -> Optional[bytes]:
        """Root over the pending leaves — the session subtree. `None` when nothing is pending.

        Returning None rather than a root over zero leaves is deliberate: anchoring "nothing"
        would consume an epoch and assert a commitment to an empty set, which is not the same
        as not anchoring.
        """
        pending = self.pending_leaves()
        if not pending:
            return None
        return merkle_root([leaf.hash_bytes() for leaf in pending])

    def record_anchor(self, root: bytes, tx_hash: str, epoch: Optional[int] = None) -> Dict[str, Any]:
        """Record a successful on-chain anchor. Call only AFTER the transaction confirms.

        Recording before confirmation would advance `anchored_count` past leaves that never made
        it on-chain, and those leaves would never be anchored by any later run — silent loss of
        exactly the evidence this exists to preserve.
        """
        entry = {
            "root": "0x" + root.hex(),
            "tx_hash": tx_hash,
            "epoch": epoch,
            "leaves_through": len(self.all_leaves()),
            "anchored_at": int(time.time()),
        }
        with self.anchors_path.open("a") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    def proof_for(self, leaf: VaultLeaf) -> Optional[Dict[str, Any]]:
        """Proof that `leaf` is under one of this vault's anchored roots.

        Searches the anchored batches rather than the whole leaf log, because a proof is only
        meaningful against a root `StateAnchor` actually anchored. Returns None for a leaf that
        is still pending — honest, rather than returning a proof against a root nobody has seen.
        """
        leaves = self.all_leaves()
        target = leaf.leaf_hash
        start = 0
        for line in (self.anchors_path.read_text().splitlines() if self.anchors_path.exists() else []):
            if not line.strip():
                continue
            entry = json.loads(line)
            batch = leaves[start:entry["leaves_through"]]
            for i, candidate in enumerate(batch):
                if candidate.leaf_hash == target:
                    hashes = [b.hash_bytes() for b in batch]
                    return {
                        "root": entry["root"],
                        "leaf": target,
                        "proof": ["0x" + p.hex() for p in merkle_proof(hashes, i)],
                        "tx_hash": entry["tx_hash"],
                    }
            start = entry["leaves_through"]
        return None
