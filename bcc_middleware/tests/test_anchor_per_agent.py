"""
Tests for app/anchor.py::anchor_batch_per_agent's per-agent root reporting
(PRODUCTION_GAPS.md §5): `POST /v1/bcc/anchor/flush` used to return the
full-batch root, which is computed then DISCARDED in favor of real,
separately-anchored per-agent sub-roots -- the returned value matched
nothing actually on-chain. `AnchorResult.root` now carries the real
sub-root that was anchored (or attempted) for each agent.
"""

from __future__ import annotations

import respx
from eth_account import Account
from httpx import Response

from app.anchor import anchor_batch_per_agent
from app.chain import resolve_agent_primitives
from app.config import Settings
from app.merkle import BatchLeaf, leaf_hash, merkle_root
from tests.helpers import new_agent, sign_commitment

_ORACLE_URL = "http://oracle.test"


def _leaves_for_agent(agent_id: str, private_key, count: int, *, start_nonce: int = 1) -> list[BatchLeaf]:
    leaves = []
    for i in range(count):
        commitment_dict = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=start_nonce + i)
        from app.schemas import BCCCommitment

        commitment = BCCCommitment(**commitment_dict)
        leaves.append(BatchLeaf(commitment=commitment, leaf_hash=leaf_hash(commitment)))
    return leaves


def test_anchor_batch_per_agent_returns_the_real_anchored_sub_root(anvil_chain):
    """The root returned for an agent must be the actual sub-root computed
    over just THAT agent's leaves -- independently recomputed here and
    compared, not just asserted non-null."""
    agent_id, private_key = new_agent()
    sovereign_agent = Account.create().address
    settings = Settings(rpc_url=anvil_chain["rpc_url"], anchor_signer_private_key=anvil_chain["signer_private_key"])

    agent_leaves = _leaves_for_agent(agent_id, private_key, 3)
    expected_sub_root = merkle_root([leaf.leaf_hash for leaf in agent_leaves])

    with respx.mock as respx_mock:
        respx_mock.get(f"{_ORACLE_URL}/v1/agent/{agent_id}").mock(
            return_value=Response(
                200,
                json={
                    "id": agent_id,
                    "verification_tier": 1,
                    "primitives": {"sovereign_agent": sovereign_agent, "state_anchor": anvil_chain["anchor_address"]},
                },
            )
        )
        resolve_agent_primitives.cache_clear()
        settings = Settings(
            rpc_url=anvil_chain["rpc_url"], anchor_signer_private_key=anvil_chain["signer_private_key"], oracle_url=_ORACLE_URL
        )
        results = anchor_batch_per_agent(settings, agent_leaves)

    assert results[agent_id].submitted, results[agent_id].detail
    assert results[agent_id].root == expected_sub_root


def test_anchor_batch_per_agent_gives_each_agent_its_own_distinct_root(anvil_chain):
    """Two agents in the same flushed batch must get two DIFFERENT roots
    (each over only their own leaves) -- proves this isn't accidentally
    returning one shared/global root relabeled per agent."""
    agent_a, key_a = new_agent()
    agent_b, key_b = new_agent()
    sovereign_a = Account.create().address
    sovereign_b = Account.create().address

    leaves_a = _leaves_for_agent(agent_a, key_a, 2)
    leaves_b = _leaves_for_agent(agent_b, key_b, 5)
    all_leaves = leaves_a + leaves_b

    with respx.mock as respx_mock:
        for agent_id, sovereign in ((agent_a, sovereign_a), (agent_b, sovereign_b)):
            respx_mock.get(f"{_ORACLE_URL}/v1/agent/{agent_id}").mock(
                return_value=Response(
                    200,
                    json={
                        "id": agent_id,
                        "verification_tier": 1,
                        "primitives": {"sovereign_agent": sovereign, "state_anchor": anvil_chain["anchor_address"]},
                    },
                )
            )
        resolve_agent_primitives.cache_clear()
        settings = Settings(
            rpc_url=anvil_chain["rpc_url"], anchor_signer_private_key=anvil_chain["signer_private_key"], oracle_url=_ORACLE_URL
        )
        results = anchor_batch_per_agent(settings, all_leaves)

    assert results[agent_a].root == merkle_root([leaf.leaf_hash for leaf in leaves_a])
    assert results[agent_b].root == merkle_root([leaf.leaf_hash for leaf in leaves_b])
    assert results[agent_a].root != results[agent_b].root


def test_anchor_batch_per_agent_root_is_none_when_agent_cannot_be_resolved():
    """An agent the oracle doesn't know about never gets as far as computing
    a sub-root -- `root` stays None rather than a stale/misleading value."""
    agent_id, private_key = new_agent()
    settings = Settings(rpc_url="http://127.0.0.1:1", oracle_url="http://127.0.0.1:1")
    leaves = _leaves_for_agent(agent_id, private_key, 1)

    results = anchor_batch_per_agent(settings, leaves)

    assert not results[agent_id].submitted
    assert results[agent_id].root is None
