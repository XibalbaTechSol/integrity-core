"""
Tests for the Merkle DAG memory layer (`docs/design/memory-dag.md`).

These pin the *structural* properties the design rests on, not just round-trips.
Each of the first four would still pass under a design that silently loses the
thing it is meant to prove, so they assert the failure mode directly.
"""

from __future__ import annotations

import pytest

from integrity_sdk.memory_dag import (
    MemoryGraph,
    MemoryGraphError,
    MemoryNode,
    ancestry_proof,
    canonical,
    content_hash,
    root_of_heads,
    verify_ancestry,
)

DID = "did:integrity:" + "a" * 64
OTHER_DID = "did:integrity:" + "b" * 64


@pytest.fixture
def graph(tmp_path):
    return MemoryGraph(DID, home=tmp_path)


def _node(**kw):
    base = dict(
        agent_id=DID,
        kind="memory",
        content_hash=content_hash("body"),
        parents=(),
        edge_type="genesis",
        timestamp=1000,
        source="claude-code",
    )
    base.update(kw)
    return MemoryNode(**base)


# --- identity / canonicalization ------------------------------------------------


def test_node_id_is_deterministic_and_independent_of_field_order():
    """Canonical encoding sorts keys, so two equal nodes hash identically."""
    assert _node().node_id == _node().node_id


def test_canonical_encoding_is_ascii_and_compact():
    """Must match the BCC canonical form the rest of the repo already shares."""
    out = canonical({"b": 1, "a": "é"})
    assert out == b'{"a":"\\u00e9","b":1}'


def test_changing_a_parent_changes_the_descendant_id():
    """The whole point: relationships are inside the hash, so an edge cannot be
    rewritten without invalidating everything downstream."""
    a = _node(content_hash=content_hash("a"))
    b = _node(content_hash=content_hash("b"))
    child_of_a = _node(parents=(a.node_id,), edge_type="derived_from", timestamp=2000)
    child_of_b = _node(parents=(b.node_id,), edge_type="derived_from", timestamp=2000)
    assert child_of_a.node_id != child_of_b.node_id


def test_parent_order_is_significant():
    """Structural edges are positional — `parents[0]` is the superseded version.
    If this ever sorts, lineage semantics vanish the way leaf position does in the
    vault's sorted-pair tree."""
    p1, p2 = _node(content_hash=content_hash("1")), _node(content_hash=content_hash("2"))
    forward = _node(parents=(p1.node_id, p2.node_id), edge_type="derived_from", timestamp=2000)
    reversed_ = _node(parents=(p2.node_id, p1.node_id), edge_type="derived_from", timestamp=2000)
    assert forward.node_id != reversed_.node_id


def test_from_json_rejects_a_tampered_stored_id():
    d = _node().to_json()
    d["content_hash"] = content_hash("something else")
    with pytest.raises(ValueError, match="node_id mismatch"):
        MemoryNode.from_json(d)


# --- the acyclicity invariant ---------------------------------------------------


def test_a_node_referencing_an_unstored_parent_is_rejected(graph):
    """This single rule is what makes the graph acyclic without a cycle check."""
    orphan = _node(parents=("0x" + "ff" * 32,), edge_type="derived_from", timestamp=2000)
    with pytest.raises(MemoryGraphError, match="not stored"):
        graph.append(orphan)


def test_a_parent_newer_than_its_child_is_rejected(graph):
    parent = _node(timestamp=5000)
    graph.append(parent)
    with pytest.raises(MemoryGraphError, match="backward in time"):
        graph.append(_node(parents=(parent.node_id,), edge_type="derived_from", timestamp=1000))


def test_genesis_and_non_genesis_parent_rules(graph):
    with pytest.raises(MemoryGraphError, match="genesis node has no parents"):
        p = _node()
        graph.append(p)
        graph.append(_node(parents=(p.node_id,), edge_type="genesis", timestamp=2000))
    with pytest.raises(MemoryGraphError, match="requires at least one parent"):
        graph.append(_node(edge_type="supersedes", timestamp=3000))


def test_appending_the_same_node_twice_is_a_noop(graph):
    n = _node()
    assert graph.append(n) == graph.append(n)
    assert len(graph.all_nodes()) == 1


def test_a_node_from_another_agent_is_rejected(graph):
    with pytest.raises(MemoryGraphError, match="belongs to"):
        graph.append(_node(agent_id=OTHER_DID))


# --- refs: editing without orphaning --------------------------------------------


def test_editing_a_memory_creates_a_new_node_and_moves_the_ref(graph):
    v1 = graph.write("spec-notes", "first version", timestamp=1000)
    v2 = graph.write("spec-notes", "second version", timestamp=2000)

    assert v1.node_id != v2.node_id
    assert v2.edge_type == "supersedes"
    assert v2.parents[0] == v1.node_id
    assert graph.resolve("spec-notes") == v2.node_id
    # v1 is still addressable — nothing was mutated.
    assert graph.get(v1.node_id) is not None


def test_history_walks_every_version_newest_first(graph):
    graph.write("m", "v1", timestamp=1000)
    graph.write("m", "v2", timestamp=2000)
    graph.write("m", "v3", timestamp=3000)
    hist = graph.history("m")
    assert [n.content_hash for n in hist] == [content_hash(v) for v in ("v3", "v2", "v1")]


def test_editing_does_not_orphan_a_descendant(graph):
    """The failure this design exists to prevent: an in-place edit would change the
    id and break every node pointing at it."""
    base = graph.write("base", "original", timestamp=1000)
    derived = graph.write("derived", "cites base", extra_parents=(base.node_id,), timestamp=1500)
    graph.write("base", "revised", timestamp=2000)

    still = graph.get(derived.node_id)
    assert still is not None
    assert graph.get(still.parents[-1]) is not None  # base v1 still resolves


def test_a_dangling_link_resolves_to_none_rather_than_raising(graph):
    """`[[name]]` for a memory that doesn't exist yet is explicitly allowed."""
    assert graph.resolve("never-written") is None


# --- ancestry proofs ------------------------------------------------------------


def test_ancestry_proof_verifies_without_access_to_the_graph(graph):
    a = graph.write("a", "root", timestamp=1000)
    b = graph.write("b", "mid", extra_parents=(a.node_id,), timestamp=2000)
    c = graph.write("c", "leaf", extra_parents=(b.node_id,), timestamp=3000)

    chain = ancestry_proof(graph, c.node_id, a.node_id)
    assert chain is not None
    assert verify_ancestry(chain) is True


def test_ancestry_proof_returns_none_when_unrelated(graph):
    a = graph.write("a", "one", timestamp=1000)
    b = graph.write("b", "two", timestamp=2000)
    assert ancestry_proof(graph, b.node_id, a.node_id) is None


def test_verify_ancestry_rejects_a_tampered_chain(graph):
    a = graph.write("a", "root", timestamp=1000)
    b = graph.write("b", "leaf", extra_parents=(a.node_id,), timestamp=2000)
    chain = ancestry_proof(graph, b.node_id, a.node_id)

    chain[-1]["content_hash"] = content_hash("forged ancestor")
    assert verify_ancestry(chain) is False


def test_verify_ancestry_rejects_a_forward_pointing_edge():
    """A chain whose 'ancestor' is newer is not a lineage, even if the hashes link."""
    parent = _node(timestamp=9000)
    child = _node(parents=(parent.node_id,), edge_type="derived_from", timestamp=1000)
    assert verify_ancestry([child.preimage(), parent.preimage()]) is False


# --- the payoff: shared provenance without disclosure ---------------------------


def test_identical_content_across_runtimes_is_detectable_from_hashes_alone(tmp_path):
    """Two runtimes reaching the same conclusion produce the same `content_hash`,
    while their node ids differ (different source/timestamp). That is the one real
    inference primitive content-addressing provides — and it discloses no text."""
    g = MemoryGraph(DID, home=tmp_path)
    claude = g.write("finding", "the gate cannot deny", source="claude-code", timestamp=1000)
    hermes = g.write("finding-h", "the gate cannot deny", source="hermes", timestamp=2000)

    assert claude.content_hash == hermes.content_hash
    assert claude.node_id != hermes.node_id


# --- anchoring ------------------------------------------------------------------


def test_root_of_heads_is_stable_and_32_bytes(graph):
    graph.write("a", "one", timestamp=1000)
    graph.write("b", "two", timestamp=2000)
    heads = list(graph.refs().values())
    root = root_of_heads(heads)
    assert len(root) == 32
    assert root == root_of_heads(reversed(heads))  # order-independent by design


def test_root_of_heads_rejects_an_empty_set(graph):
    with pytest.raises(MemoryGraphError, match="no heads"):
        root_of_heads([])
