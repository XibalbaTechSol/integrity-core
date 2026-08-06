#!/usr/bin/env python3
"""
Build the protocol evidence DAG from the existing Trust Vault leaves.

Step 4 of `docs/design/memory-dag.md`. Each vault leaf (one per commit) becomes a
`commit` node chained to its predecessor by `derived_from`, turning a flat,
order-less *set* of 21 leaves into a walkable, provable development lineage.

    integrity-sdk/.venv/bin/python scripts/import_memory_dag.py --dry-run
    integrity-sdk/.venv/bin/python scripts/import_memory_dag.py

**NEVER RUN — written 2026-07-31 without shell access.** Use `--dry-run` first and
treat the first execution as a test, not a migration.

**Scope (corrected 2026-07-31).** An earlier version of this script imported the
agent's working-memory `.md` files. That was wrong: this DAG holds *protocol
evidence*, which is append-only and anchored. Xibalba's day-to-day recall is a
separate local system (`docs/design/xibalba-supermemory.md`) precisely because it
must be able to forget, and this must not.

Deliberately does NOT anchor on-chain. Anchoring is a signed transaction and stays
with the existing `anchor_vault.py` path — the same separation `vault.py` keeps
between recording a leaf and anchoring a root.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "integrity-sdk"))

DEFAULT_DID = "did:integrity:68fed1331613937555a59398223e8e87520a87dd0305aac4fd7ecdc32a14a861"


def _is_ancestor(a: str, b: str, cache: dict[tuple[str, str], bool]) -> bool:
    """
    True iff commit `a` is a genuine git ancestor of commit `b`.

    A missing commit answers False: an edge we cannot verify is one we must not
    assert. See `_parent_for` for why that direction is the safe one.
    """
    key = (a, b)
    if key not in cache:
        cache[key] = (
            subprocess.run(
                ["git", "-C", str(REPO), "merge-base", "--is-ancestor", a, b],
                capture_output=True,
            ).returncode
            == 0
        )
    return cache[key]


def _parent_for(leaf, earlier: list, cache: dict[tuple[str, str], bool]):
    """
    The tightest TRUE parent of `leaf`: the most recent already-imported leaf whose
    commit is an actual git ancestor of this one. `earlier` is in import order.

    Why this is not "just chain to the previous leaf" (the original approach, and a
    real defect caught on first execution 2026-07-31): the vault's leaves are ordered
    by wall-clock time, and wall-clock order is NOT ancestry. Measured on the real
    21-leaf vault, 19 of 20 consecutive pairs happen to be ancestor pairs, but
    `6c0c9bf -> d7e4deb` is not — they are siblings off merge-base `354c6b5`, one on
    `docs/spec-open-definitions` and one on `main`, because the developer switched
    branches. Chaining linearly would have recorded a `derived_from` edge asserting
    that one commit descends from the other when git says it does not.

    In a recall system that would be a harmless approximation. This is an *evidence*
    system whose whole claim is that its lineage is non-forgeable, so a lineage edge
    that is merely plausible is worse than no edge: it is a false statement that
    verifies. Where no earlier leaf is an ancestor, the node becomes a second root
    (`genesis`) rather than inventing a parent — an honestly disconnected branch
    beats a fabricated chain.
    """
    for candidate in reversed(earlier):
        if _is_ancestor(candidate.commit_sha, leaf.commit_sha, cache):
            return candidate
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--did", default=DEFAULT_DID)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    from integrity_sdk.memory_dag import MemoryGraph, MemoryNode
    from integrity_sdk.vault import TrustVault

    vault = TrustVault(args.did)
    graph = MemoryGraph(args.did)

    leaves = vault.all_leaves()
    if not leaves:
        print("no vault leaves — nothing to import")
        return 0

    print(f"{len(leaves)} vault leaves; {len(graph.all_nodes())} nodes already in the DAG\n")

    known = {n.node_id for n in graph.all_nodes()}
    imported = skipped = unverified = 0
    roots = 0
    # Ancestry is resolved against git, never assumed from file order — see `_parent_for`.
    anc_cache: dict[tuple[str, str], bool] = {}
    node_id_of: dict[str, str] = {}  # commit_sha -> node_id, for parent lookup
    seen: list = []  # leaves already imported, in order
    last: str | None = None

    for leaf in leaves:
        parent_leaf = _parent_for(leaf, seen, anc_cache)
        prev = node_id_of.get(parent_leaf.commit_sha) if parent_leaf else None
        if prev is None:
            roots += 1

        # The leaf hash IS the content commitment — reuse it rather than rehashing,
        # so a DAG node and its vault leaf commit to the same bytes and either can
        # be checked against the other.
        node = MemoryNode(
            agent_id=args.did,
            kind="commit",
            content_hash=leaf.leaf_hash,
            parents=(prev,) if prev else (),
            edge_type="derived_from" if prev else "genesis",
            # Vault leaves are second-resolution; the DAG is millisecond. Scale rather
            # than reuse, or every parent looks simultaneous with its child and the
            # backward-in-time check in `append` becomes meaningless.
            timestamp=leaf.timestamp * 1000,
            source="claude-code",
        )

        # Honest accounting: a leaf whose tests were never recorded produces a node
        # that proves a commit happened and nothing about whether it was sound.
        if leaf.test_result_hash.startswith("unverified"):
            unverified += 1

        via = f" <- {parent_leaf.commit_sha[:8]}" if parent_leaf else " (no ancestor among earlier leaves)"
        if node.node_id in known:
            skipped += 1
        elif args.dry_run:
            print(f"[would add] {leaf.commit_sha[:8]} -> {node.node_id[:18]}… ({node.edge_type}){via}")
            imported += 1
        else:
            graph.append(node)
            print(f"[add] {leaf.commit_sha[:8]} -> {node.node_id[:18]}… ({node.edge_type}){via}")
            imported += 1

        node_id_of[leaf.commit_sha] = node.node_id
        seen.append(leaf)
        last = node.node_id

    # `head` tracks the newest imported node. It is a head, not necessarily THE only
    # one: a branch that was never merged leaves its own tip with no descendant (in the
    # real 21-leaf import, `6c0c9bf` on `docs/spec-open-definitions`). Those tips are
    # reachable in the graph but carry no named ref, so `root_of_heads(refs)` below
    # commits to the main line only — it is not yet a commitment to the whole frontier.
    # Recorded rather than silently papered over; see docs/design/memory-dag.md.
    if not args.dry_run and last:
        graph.set_ref("head", last)

    print(f"\nadded {imported}, already present {skipped}")
    if roots > 1:
        print(
            f"NOTE: {roots} root nodes — {roots - 1} leaf/leaves had no git ancestor "
            "among earlier leaves (branch work that never merged before its successor). "
            "Recorded as disconnected roots rather than chained to a non-ancestor."
        )
    if unverified:
        print(
            f"WARNING: {unverified}/{len(leaves)} leaves carry test_result_hash "
            "'unverified' — those nodes attest that work happened, never that it "
            "was sound (audit finding F5; see e2e-audit-2026-07-31.md for why no "
            "commit ordering currently fixes this)."
        )

    if not args.dry_run:
        from integrity_sdk.memory_dag import root_of_heads

        heads = list(graph.refs().values())
        print(f"\nroot_of_heads = 0x{root_of_heads(heads).hex()}")
        print("Anchor with the existing anchor_vault.py path.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
