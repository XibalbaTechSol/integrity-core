"""
Tests for app/anchor.py::anchor_batch_per_agent on the v3 `ActionAnchor` (v2 graph deletion slice
D2, owner question 8a): a flushed batch is anchored as ONE root under this service's signer address,
and that root is a tree over per-agent sub-roots. Each agent's result carries its real sub-root
(PRODUCTION_GAPS.md §5: the value returned must match something actually anchored), the batch root,
and the sub-root's proof up to it.

The discriminating checks are on chain: a single commitment leaf, folded through its sub-tree proof
and then the sub-root's proof, verifies with `ActionAnchor.verifyLeaf(signer, leaf, proof)` against
the fixture contract, and the transaction's `RootAnchored` event carries the batch root under the
signer.
"""

from __future__ import annotations

from eth_account import Account

from app.anchor import anchor_batch_per_agent
from app.config import Settings
from app.merkle import BatchLeaf, leaf_hash, merkle_proof, merkle_root
from tests.helpers import chain_settings, fixture_contract, new_agent, sign_commitment


def _leaves_for_agent(agent_id: str, private_key, count: int, *, start_nonce: int = 1) -> list[BatchLeaf]:
    from app.schemas import BCCCommitment

    leaves = []
    for i in range(count):
        commitment = BCCCommitment(**sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=start_nonce + i))
        leaves.append(BatchLeaf(commitment=commitment, leaf_hash=leaf_hash(commitment)))
    return leaves


def _settings(anvil_chain) -> Settings:
    return chain_settings(anvil_chain, anchor_signer_private_key=anvil_chain["signer_private_key"])


def test_anchor_batch_per_agent_returns_the_real_sub_root(anvil_chain):
    """The root returned for an agent is the sub-root over just THAT agent's leaves."""
    agent_id, private_key = new_agent()
    agent_leaves = _leaves_for_agent(agent_id, private_key, 3)

    results = anchor_batch_per_agent(_settings(anvil_chain), agent_leaves)

    assert results[agent_id].submitted, results[agent_id].detail
    assert results[agent_id].root == merkle_root([leaf.leaf_hash for leaf in agent_leaves])


def test_a_mixed_batch_is_one_transaction_with_one_batch_root(anvil_chain):
    """Two agents in one flush: distinct sub-roots, one tx, one batch root over the sub-roots."""
    agent_a, key_a = new_agent()
    agent_b, key_b = new_agent()
    leaves_a = _leaves_for_agent(agent_a, key_a, 2)
    leaves_b = _leaves_for_agent(agent_b, key_b, 5)

    results = anchor_batch_per_agent(_settings(anvil_chain), leaves_a + leaves_b)

    a, b = results[agent_a], results[agent_b]
    assert a.submitted and b.submitted
    assert a.root == merkle_root([leaf.leaf_hash for leaf in leaves_a])
    assert b.root == merkle_root([leaf.leaf_hash for leaf in leaves_b])
    assert a.root != b.root
    assert a.tx_hash == b.tx_hash
    # Sub-roots are the batch tree's leaves, in agent-id order.
    assert a.batch_root == b.batch_root == merkle_root([results[aid].root for aid in sorted(results)])
    signer = Account.from_key(anvil_chain["signer_private_key"]).address
    assert a.anchorer == b.anchorer == signer


def test_a_commitment_leaf_verifies_on_chain_against_the_anchored_batch_root(anvil_chain):
    """
    The evidence claim, checked by the contract: leaf -> (sub-tree proof) -> sub-root -> (batch
    proof) -> batch root, verified by `ActionAnchor.verifyLeaf(signer, leaf, proof)`. Also checks
    the `RootAnchored` event of the anchoring tx names the signer and carries the batch root.
    """
    agent_a, key_a = new_agent()
    agent_b, key_b = new_agent()
    agent_c, key_c = new_agent()
    leaves_a = _leaves_for_agent(agent_a, key_a, 3)
    leaves_b = _leaves_for_agent(agent_b, key_b, 1)
    leaves_c = _leaves_for_agent(agent_c, key_c, 4)

    results = anchor_batch_per_agent(_settings(anvil_chain), leaves_a + leaves_b + leaves_c)

    anchor = fixture_contract(anvil_chain, "action_anchor")
    signer = Account.from_key(anvil_chain["signer_private_key"]).address
    for agent_id, leaves in ((agent_a, leaves_a), (agent_b, leaves_b), (agent_c, leaves_c)):
        result = results[agent_id]
        hashes = [leaf.leaf_hash for leaf in leaves]
        for index, leaf in enumerate(hashes):
            proof = merkle_proof(hashes, index) + result.proof
            assert anchor.functions.verifyLeaf(signer, leaf, proof).call(), (agent_id, index)
        if len(hashes) > 1:
            # The batch path alone is not enough: the leaf's sub-tree proof is part of the claim.
            assert not anchor.functions.verifyLeaf(signer, hashes[0], result.proof).call()

    receipt = anvil_chain["w3"].eth.get_transaction_receipt(results[agent_a].tx_hash)
    events = anchor.events.RootAnchored().process_receipt(receipt)
    assert len(events) == 1
    assert events[0]["args"]["agent"] == signer
    assert events[0]["args"]["root"] == results[agent_a].batch_root


def test_nothing_is_anchored_when_no_action_anchor_is_configured(tmp_path):
    """With no `ActionAnchor` entry, every agent in the batch fails uniformly and nothing is sent."""
    agent_id, private_key = new_agent()
    settings = Settings(rpc_url="http://127.0.0.1:1", deployments_file=str(tmp_path / "missing.json"))

    results = anchor_batch_per_agent(settings, _leaves_for_agent(agent_id, private_key, 1))

    assert not results[agent_id].submitted
    assert results[agent_id].tx_hash is None
    assert "ActionAnchor" in results[agent_id].detail
