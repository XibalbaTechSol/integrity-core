"""
Memory as a Merkle DAG — content-addressed nodes whose *relationships* are hashed.

Design: `docs/design/memory-dag.md`. Closes §7.4 lineage attestation, recorded as
open in `docs/wiki/concepts/agent-memory.md`.

**Why this exists alongside `vault.py`.** The Trust Vault's Merkle tree commits to a
flat *set* — its sorted-pair convention deliberately erases position ("the root
becomes a function of the set of leaves", `vault.py`). That answers "was this leaf
in this set?" and structurally nothing else. It cannot express that one memory
derives from another. This module adds the missing structure; it does not replace
the tree, which is still what anchors heads (see `root_of_heads`).

**Three layers, and the split is the design:**

  1. Objects (here) — immutable, content-addressed, hashed. `parents` carries ONLY
     backward-in-time edges, so the graph is acyclic *by construction*.
  2. Refs (`RefStore`) — mutable `name -> head id`. This is what makes editing a
     memory work without orphaning its descendants.
  3. Semantic `[[links]]` — committed INSIDE `content_hash` as claims, never as
     `parents`. Wiki links may form cycles and may dangle; both are fine as content
     and both would be fatal as hash edges.

The rule, stated once: structural edges are ordered, positional and backward in
time. Semantic edges live in content. Never promote a semantic link into `parents`.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from eth_utils import keccak

#: Bumping this changes every node id. It is part of the hashed preimage precisely
#: so that a schema change cannot silently produce ids that collide with v1 ids.
SCHEMA = "integrity.memory.node.v1"

#: Structural edge kinds. All point strictly backward in time — that is what makes
#: the object graph a DAG without needing a cycle check anywhere.
EDGE_TYPES = frozenset({"genesis", "supersedes", "derived_from", "forked_from", "session_of"})

NODE_KINDS = frozenset({"memory", "commit", "session", "test_result", "lineage"})


def _vault_home() -> Path:
    """Same root as `vault.py`, so an agent's memory and its vault live together."""
    return Path(os.environ.get("INTEGRITY_VAULT_HOME", str(Path.home() / ".integrity" / "vault")))


def canonical(obj: Any) -> bytes:
    """Canonical JSON — sorted keys, no whitespace, `ensure_ascii=True`.

    Byte-identical to the convention `integrity_sdk/bcc.py`, `integrity_cli/bcc.py`
    and `bcc_middleware/app/canonical.py` already share. Reusing it rather than
    inventing a second encoding is deliberate: the repo already carries one
    documented non-ASCII disagreement between Python and Rust canonicalization, and
    a second canonical form would be a second place for that class of bug to live.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def content_hash(body: str) -> str:
    """Hash of a memory's actual text. Only this ever leaves the machine.

    Structure is provable without disclosing content — the same posture the BCC
    hash-only commitment takes, and what lets an ancestry proof reveal the shape of
    a lineage while revealing none of its text.
    """
    return "0x" + keccak(text=body).hex()


@dataclass(frozen=True)
class MemoryNode:
    """One immutable node. `node_id` is a function of every other field.

    `parents` is a tuple (not a list) so the dataclass stays hashable and so the
    order is fixed — parent order is *meaning* here (`parents[0]` is the superseded
    version), which is exactly the information the vault's sorted-pair tree throws
    away. Never sort it.
    """

    agent_id: str
    kind: str
    content_hash: str
    parents: Tuple[str, ...]
    edge_type: str
    timestamp: int
    source: str
    schema: str = SCHEMA

    def preimage(self) -> Dict[str, Any]:
        """Exactly the fields that are hashed. `node_id` is excluded — it is the output."""
        return {
            "schema": self.schema,
            "agent_id": self.agent_id,
            "kind": self.kind,
            "content_hash": self.content_hash,
            "parents": list(self.parents),
            "edge_type": self.edge_type,
            "timestamp": self.timestamp,
            "source": self.source,
        }

    @property
    def node_id(self) -> str:
        return "0x" + keccak(canonical(self.preimage())).hex()

    def to_json(self) -> Dict[str, Any]:
        d = asdict(self)
        d["parents"] = list(self.parents)
        d["node_id"] = self.node_id
        return d

    @staticmethod
    def from_json(d: Dict[str, Any]) -> "MemoryNode":
        node = MemoryNode(
            agent_id=d["agent_id"],
            kind=d["kind"],
            content_hash=d["content_hash"],
            parents=tuple(d["parents"]),
            edge_type=d["edge_type"],
            timestamp=d["timestamp"],
            source=d["source"],
            schema=d.get("schema", SCHEMA),
        )
        # A stored id that disagrees with the recomputed one means the file was
        # edited underneath us. Surfacing that loudly is the entire point of
        # content-addressing; silently trusting the stored id would discard it.
        stored = d.get("node_id")
        if stored is not None and stored != node.node_id:
            raise ValueError(f"node_id mismatch: stored {stored}, recomputed {node.node_id}")
        return node


class MemoryGraphError(RuntimeError):
    pass


class MemoryGraph:
    """Append-only object store + mutable ref store for one agent.

    Files under `~/.integrity/vault/<agent_id>/`, mirroring `vault.py`'s layout:
      * `memory_nodes.jsonl` — every node ever written, append-only
      * `memory_refs.json`   — name -> current head node_id

    **The acyclicity invariant, and why it needs no cycle detection.** `append`
    refuses a node whose parents are not already stored. Since a parent must exist
    before its child can be built, and a node's id depends on its parents' ids, a
    cycle would require knowing a node's id before creating it. Time and hashing
    supply the ordering that a wiki's `Related:` links never could.
    """

    def __init__(self, agent_id: str, home: Optional[Path] = None):
        safe = agent_id.replace(":", "_").replace("/", "_")
        self.agent_id = agent_id
        self.dir = (home or _vault_home()) / safe
        self.dir.mkdir(parents=True, exist_ok=True)
        self.nodes_path = self.dir / "memory_nodes.jsonl"
        self.refs_path = self.dir / "memory_refs.json"

    # --- objects ---------------------------------------------------------------

    def all_nodes(self) -> List[MemoryNode]:
        if not self.nodes_path.exists():
            return []
        return [MemoryNode.from_json(json.loads(l)) for l in self.nodes_path.read_text().splitlines() if l.strip()]

    def _index(self) -> Dict[str, MemoryNode]:
        return {n.node_id: n for n in self.all_nodes()}

    def get(self, node_id: str) -> Optional[MemoryNode]:
        return self._index().get(node_id)

    def append(self, node: MemoryNode) -> str:
        """Validates and stores a node. Returns its id.

        Validation is not decoration — each rejection below is a way the graph could
        otherwise become unprovable.
        """
        if node.kind not in NODE_KINDS:
            raise MemoryGraphError(f"unknown kind {node.kind!r}")
        if node.edge_type not in EDGE_TYPES:
            raise MemoryGraphError(f"unknown edge_type {node.edge_type!r}")
        if node.agent_id != self.agent_id:
            raise MemoryGraphError(f"node belongs to {node.agent_id}, not {self.agent_id}")

        known = self._index()
        if node.node_id in known:
            return node.node_id  # content-addressed: re-appending is a no-op, not an error

        for parent in node.parents:
            if parent not in known:
                raise MemoryGraphError(
                    f"parent {parent[:18]}… is not stored; a node may only reference "
                    "existing nodes (this is what makes the graph acyclic)"
                )
            if known[parent].timestamp > node.timestamp:
                raise MemoryGraphError("parent is newer than child — structural edges point backward in time")

        if node.edge_type == "genesis" and node.parents:
            raise MemoryGraphError("a genesis node has no parents")
        if node.edge_type != "genesis" and not node.parents:
            raise MemoryGraphError(f"edge_type {node.edge_type!r} requires at least one parent")

        with self.nodes_path.open("a") as f:
            f.write(json.dumps(node.to_json()) + "\n")
        return node.node_id

    # --- refs ------------------------------------------------------------------

    def refs(self) -> Dict[str, str]:
        if not self.refs_path.exists():
            return {}
        return json.loads(self.refs_path.read_text())

    def resolve(self, name: str) -> Optional[str]:
        """Current head id for a memory name, or None if the name is unknown.

        None is the correct answer for a dangling `[[link]]` — the memory
        instructions explicitly allow naming a memory that does not exist yet, and
        that must not be an error.
        """
        return self.refs().get(name)

    def set_ref(self, name: str, node_id: str) -> None:
        refs = self.refs()
        refs[name] = node_id
        self.refs_path.write_text(json.dumps(refs, sort_keys=True, indent=2) + "\n")

    # --- the two operations that actually get used -----------------------------

    def write(self, name: str, body: str, *, kind: str = "memory", source: str = "claude-code",
              extra_parents: Sequence[str] = (), timestamp: Optional[int] = None) -> MemoryNode:
        """Create or update the memory called `name`.

        This is the operation that makes editing safe. An update does NOT mutate the
        existing node — it writes a new one whose `parents[0]` is the previous head
        (`supersedes`) and moves the ref. Every prior version stays addressable and
        every descendant stays valid, which is precisely what in-place editing of a
        content-addressed node would destroy.
        """
        ts = int(timestamp if timestamp is not None else time.time() * 1000)
        head = self.resolve(name)
        parents = ((head,) if head else ()) + tuple(extra_parents)
        node = MemoryNode(
            agent_id=self.agent_id,
            kind=kind,
            content_hash=content_hash(body),
            parents=parents,
            edge_type="supersedes" if head else ("derived_from" if extra_parents else "genesis"),
            timestamp=ts,
            source=source,
        )
        self.append(node)
        self.set_ref(name, node.node_id)
        return node

    def history(self, name: str) -> List[MemoryNode]:
        """Every version of `name`, newest first, by walking `supersedes` edges."""
        index = self._index()
        head = self.resolve(name)
        out: List[MemoryNode] = []
        while head:
            node = index.get(head)
            if node is None:
                break
            out.append(node)
            head = node.parents[0] if node.parents else None
        return out


# --- proofs --------------------------------------------------------------------


def ancestry_proof(graph: MemoryGraph, descendant_id: str, ancestor_id: str) -> Optional[List[Dict[str, Any]]]:
    """The chain of node preimages proving `descendant` descends from `ancestor`.

    Returns preimages (not bodies) — so a verifier learns the *shape* of a lineage
    and none of its text. Depth-first over `parents`; returns None when no path
    exists, rather than an empty list, so "no relationship" is distinguishable from
    "they are the same node".
    """
    index = graph._index()
    if descendant_id not in index or ancestor_id not in index:
        return None

    stack: List[Tuple[str, List[str]]] = [(descendant_id, [descendant_id])]
    seen = set()
    while stack:
        current, path = stack.pop()
        if current == ancestor_id:
            return [index[i].preimage() for i in path]
        if current in seen:
            continue
        seen.add(current)
        for parent in index[current].parents:
            if parent in index:
                stack.append((parent, path + [parent]))
    return None


def verify_ancestry(chain: Sequence[Dict[str, Any]]) -> bool:
    """Re-derives every id in a proof chain and checks each link.

    Deliberately takes ONLY the chain — no graph, no store. A proof that needs the
    prover's database to check is not a proof. `chain[0]` is the descendant,
    `chain[-1]` the ancestor.
    """
    if len(chain) < 2:
        return False
    ids = ["0x" + keccak(canonical(node)).hex() for node in chain]
    for i in range(len(chain) - 1):
        if ids[i + 1] not in chain[i].get("parents", []):
            return False
        if chain[i + 1].get("timestamp", 0) > chain[i].get("timestamp", 0):
            return False  # an edge that points forward in time is not a lineage
    return True


def root_of_heads(head_ids: Iterable[str]) -> bytes:
    """Single 32-byte commitment over all current refs, for `StateAnchor.anchorRoot`.

    Reuses `vault.py`'s tree — sorted-pair position-erasure is harmless here because
    each head already commits to its own structure transitively. Anchoring one head
    therefore commits its entire reachable history, which is why this is strictly
    stronger than anchoring a batch of unrelated leaves.
    """
    from .vault import merkle_root  # local import: avoids a cycle at module load

    leaves = sorted(bytes.fromhex(h.removeprefix("0x")) for h in head_ids)
    if not leaves:
        raise MemoryGraphError("no heads to anchor")
    return merkle_root(leaves)
