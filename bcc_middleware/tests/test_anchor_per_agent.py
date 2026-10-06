"""
Tests for app/anchor.py::anchor_batch_per_agent's per-agent root reporting
(PRODUCTION_GAPS.md §5): `POST /v1/bcc/anchor/flush` used to return the
full-batch root, which is computed then DISCARDED in favor of real,
separately-anchored per-agent sub-roots -- the returned value matched
nothing actually on-chain. `AnchorResult.root` now carries the real
sub-root that was anchored (or attempted) for each agent.

Updated for docs/EXECUTION_PLAN.md B4: the sub-roots now anchor to one
configured, dedicated protocol evidence StateAnchor (settings.contract_address
via the deployments file), not to each agent's own memory StateAnchor resolved
through the oracle -- that old target was the exact contract C2 registration
reads `latestRoot()` from as the memory root, so a batch anchor and a
memory-root anchor were racing for the same slot.
"""

from __future__ import annotations

import json

from app.anchor import anchor_batch_per_agent
from app.config import Settings
from app.merkle import BatchLeaf, leaf_hash, merkle_root
from tests.helpers import new_agent, sign_commitment


def _leaves_for_agent(agent_id: str, private_key, count: int, *, start_nonce: int = 1) -> list[BatchLeaf]:
    leaves = []
    for i in range(count):
        commitment_dict = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=start_nonce + i)
        from app.schemas import BCCCommitment

        commitment = BCCCommitment(**commitment_dict)
        leaves.append(BatchLeaf(commitment=commitment, leaf_hash=leaf_hash(commitment)))
    return leaves


def _settings_with_evidence_anchor(tmp_path, anvil_chain) -> Settings:
    deployments_file = tmp_path / "deployments.local.json"
    deployments_file.write_text(json.dumps({"singletons": {"ProtocolEvidenceAnchor": anvil_chain["anchor_address"]}}))
    return Settings(
        rpc_url=anvil_chain["rpc_url"],
        anchor_signer_private_key=anvil_chain["signer_private_key"],
        deployments_file=str(deployments_file),
    )


def test_anchor_batch_per_agent_returns_the_real_anchored_sub_root(anvil_chain, tmp_path):
    """The root returned for an agent must be the actual sub-root computed
    over just THAT agent's leaves -- independently recomputed here and
    compared, not just asserted non-null."""
    agent_id, private_key = new_agent()
    settings = _settings_with_evidence_anchor(tmp_path, anvil_chain)

    agent_leaves = _leaves_for_agent(agent_id, private_key, 3)
    expected_sub_root = merkle_root([leaf.leaf_hash for leaf in agent_leaves])

    results = anchor_batch_per_agent(settings, agent_leaves)

    assert results[agent_id].submitted, results[agent_id].detail
    assert results[agent_id].root == expected_sub_root


def test_anchor_batch_per_agent_gives_each_agent_its_own_distinct_root(anvil_chain, tmp_path):
    """Two agents in the same flushed batch must get two DIFFERENT roots
    (each over only their own leaves) -- proves this isn't accidentally
    returning one shared/global root relabeled per agent, even though both
    now anchor to the same dedicated evidence contract."""
    agent_a, key_a = new_agent()
    agent_b, key_b = new_agent()

    leaves_a = _leaves_for_agent(agent_a, key_a, 2)
    leaves_b = _leaves_for_agent(agent_b, key_b, 5)
    all_leaves = leaves_a + leaves_b

    settings = _settings_with_evidence_anchor(tmp_path, anvil_chain)
    results = anchor_batch_per_agent(settings, all_leaves)

    assert results[agent_a].root == merkle_root([leaf.leaf_hash for leaf in leaves_a])
    assert results[agent_b].root == merkle_root([leaf.leaf_hash for leaf in leaves_b])
    assert results[agent_a].root != results[agent_b].root
    assert results[agent_a].submitted and results[agent_b].submitted


def test_anchor_batch_per_agent_root_is_none_when_no_evidence_anchor_configured():
    """With no `ProtocolEvidenceAnchor` entry in the deployments file, every
    agent in the batch fails uniformly -- `root` stays None rather than a
    stale/misleading value, and nothing is anchored anywhere."""
    agent_id, private_key = new_agent()
    settings = Settings(rpc_url="http://127.0.0.1:1", deployments_file="/nonexistent/deployments.json")
    leaves = _leaves_for_agent(agent_id, private_key, 1)

    results = anchor_batch_per_agent(settings, leaves)

    assert not results[agent_id].submitted
    assert results[agent_id].root is None
    assert "ProtocolEvidenceAnchor" in results[agent_id].detail
