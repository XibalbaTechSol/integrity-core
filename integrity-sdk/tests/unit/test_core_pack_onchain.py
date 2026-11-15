"""Policy pack on-chain section -> PolicyRegistry graph root and per-call proofs.

Registration v3 spec Part 4 ("Policy pack -> on-chain policy"). The leaf is INTERFACE_CONTRACT
§4.4c; the golden vector below is the one `contracts/test/trust/GoldenVectors.t.sol` asserts.
"""

from __future__ import annotations

import json

import pytest

from integrity_sdk.core.merkle import keccak256, verify_leaf
from integrity_sdk.core.pack_onchain import (
    ONCHAIN_FILE,
    OnchainSectionError,
    compile_onchain,
    domain_id,
    edge_leaf,
    node_id,
    onchain_policy_of,
    proof_for,
)
from integrity_sdk.core.packs import CompiledPack

TOKEN = "0x00000000000000000000000000000000000000CA"
GOLDEN_LEAF = bytes.fromhex("58febd532cdbee740056933391a0fc3ca82d1d90cef567a211dc4e049ea138d0")


def _word(n: int) -> str:
    return "0x" + n.to_bytes(32, "big").hex()


def _section(edges=None, domain="health"):
    return {
        "domain": domain,
        "edges": edges
        if edges is not None
        else [
            {"target": TOKEN, "selector": "0xa9059cbb", "risk_weight_bps": 500},
            {"target": "0x00000000000000000000000000000000000000cb", "selector": "0x095ea7b3", "risk_weight_bps": 0},
            {"target": TOKEN, "selector": "0x23b872dd", "risk_weight_bps": 9000},
        ],
    }


def test_leaf_matches_interface_contract_golden_vector():
    leaf = edge_leaf(_word(1), _word(2), _word(3), TOKEN, "0xa9059cbb", 500)
    assert leaf == GOLDEN_LEAF


def test_golden_vector_via_section_with_raw_node_ids():
    policy = compile_onchain(
        _section([{"from_node": _word(1), "relation": _word(2), "to_node": _word(3),
                   "target": TOKEN, "selector": "0xa9059cbb", "risk_weight_bps": 500}])
    )
    assert policy.leaves == (GOLDEN_LEAF,)
    assert policy.root == GOLDEN_LEAF  # a one-leaf tree's root is the leaf


def test_plain_call_naming_defaults():
    policy = compile_onchain(_section())
    e = policy.edges[0]
    assert e.from_node == keccak256(b"agent")
    assert e.relation == keccak256(b"calls")
    assert e.to_node == node_id(f"{TOKEN.lower()}:0xa9059cbb")


def test_domain_id_matches_domain_registry():
    assert domain_id("health") == keccak256(b"health")
    assert compile_onchain(_section()).domain_id == keccak256(b"health")


def test_root_is_independent_of_edge_order():
    a = compile_onchain(_section())
    b = compile_onchain(_section(list(reversed(_section()["edges"]))))
    assert a.root == b.root


def test_every_proof_verifies_and_a_tampered_edge_does_not():
    policy = compile_onchain(_section())
    for edge in policy.edges:
        assert verify_leaf(policy.root, edge.leaf, proof_for(policy, edge))
    first = policy.edges[0]
    tampered = edge_leaf(first.from_node, first.relation, first.to_node, first.target, first.selector, 1)
    assert not verify_leaf(policy.root, tampered, proof_for(policy, first))


def test_proof_for_an_edge_outside_the_map_raises():
    policy = compile_onchain(_section())
    other = compile_onchain(_section([{"target": TOKEN, "selector": "0xdeadbeef", "risk_weight_bps": 1}])).edges[0]
    with pytest.raises(OnchainSectionError, match="NOT_IN_MAP"):
        proof_for(policy, other)


@pytest.mark.parametrize(
    "edges, code",
    [
        ([], "EMPTY"),
        ([{"target": TOKEN, "selector": "0xa9059cbb", "risk_weight_bps": 500}] * 2, "DUPLICATE_EDGE"),
        ([{"target": "0x1234", "selector": "0xa9059cbb", "risk_weight_bps": 0}], "BAD_TARGET"),
        ([{"target": TOKEN, "selector": "0xa9059c", "risk_weight_bps": 0}], "BAD_SELECTOR"),
        ([{"target": TOKEN, "selector": "0xa9059cbb", "risk_weight_bps": 10001}], "BAD_RISK_WEIGHT"),
        ([{"target": TOKEN, "selector": "0xa9059cbb", "risk_weight_bps": -1}], "BAD_RISK_WEIGHT"),
        ([{"target": TOKEN, "selector": "0xa9059cbb"}], "MISSING_FIELD"),
        ([{"target": TOKEN, "selector": "0xa9059cbb", "risk_weight_bps": 0, "extra": 1}], "UNKNOWN_FIELD"),
    ],
)
def test_malformed_sections_are_rejected(edges, code):
    with pytest.raises(OnchainSectionError) as exc:
        compile_onchain(_section(edges))
    assert exc.value.code == code


def test_missing_domain_rejected():
    with pytest.raises(OnchainSectionError) as exc:
        compile_onchain({"edges": _section()["edges"]})
    assert exc.value.code == "MISSING_FIELD"


def test_policy_is_bound_to_the_pack_hash():
    section = json.dumps(_section()).encode()
    pack = CompiledPack(manifest={}, files={ONCHAIN_FILE: section, "policy.rego": b"package x"}, pack_hash="sha256:ab")
    policy = onchain_policy_of(pack)
    assert policy is not None
    assert policy.pack_hash == "sha256:ab"
    assert policy.root == compile_onchain(_section()).root


def test_pack_without_onchain_section_has_no_policy():
    pack = CompiledPack(manifest={}, files={"policy.rego": b"package x"}, pack_hash="sha256:ab")
    assert onchain_policy_of(pack) is None


# --- edges_for_call: "is this call in the map?" (the CLI's `policy check`) ---------------------

def test_edges_for_call_matches_target_and_selector_case_insensitively():
    from integrity_sdk.core.pack_onchain import edges_for_call

    policy = compile_onchain(_section())
    hits = edges_for_call(policy, TOKEN.lower(), "0xA9059CBB")
    assert [e.risk_weight_bps for e in hits] == [500]


def test_edges_for_call_returns_every_mapped_risk_weight():
    from integrity_sdk.core.pack_onchain import edges_for_call

    policy = compile_onchain(_section(edges=[
        {"target": TOKEN, "selector": "0xa9059cbb", "risk_weight_bps": 500},
        {"target": TOKEN, "selector": "0xa9059cbb", "risk_weight_bps": 900, "to_node": "big-transfer"},
    ]))
    assert sorted(e.risk_weight_bps for e in edges_for_call(policy, TOKEN, "0xa9059cbb")) == [500, 900]


def test_edges_for_call_is_empty_for_an_unmapped_call_and_rejects_malformed_input():
    from integrity_sdk.core.pack_onchain import edges_for_call

    policy = compile_onchain(_section())
    assert edges_for_call(policy, TOKEN, "0x095ea7b3") == ()
    assert edges_for_call(policy, "0x" + "11" * 20, "0xa9059cbb") == ()
    with pytest.raises(OnchainSectionError) as e:
        edges_for_call(policy, "not-an-address", "0xa9059cbb")
    assert e.value.code == "BAD_TARGET"
    with pytest.raises(OnchainSectionError) as e:
        edges_for_call(policy, TOKEN, "0xa9059c")
    assert e.value.code == "BAD_SELECTOR"
