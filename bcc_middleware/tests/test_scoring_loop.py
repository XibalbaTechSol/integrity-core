"""
Tests for app/scoring_loop.py -- the orchestration layer that lists agents
from the oracle, pushes AIS scores to a real ReputationRegistry, and
raises real Slasher disputes on a flagged-telemetry threshold.

The oracle's HTTP surface is mocked with respx (there is no real
integrity-oracle in this test suite's fixture set -- same boundary
test_chain_baa_anchor.py and test_reputation.py mock via
mock_oracle_agent_resolution). The actual chain writes this module
triggers are REAL eth_sendTransaction calls against the same anvil_chain
fixture (MockReputationRegistry / MockSlasher) test_reputation.py uses --
only the oracle HTTP boundary is faked, not the on-chain behavior.
"""

from __future__ import annotations

import respx
from eth_account import Account
from httpx import Response

from app.chain import resolve_agent_primitives
from app.config import Settings
from app.reputation import get_available_stake
from app.scoring_loop import _base_score_from_ais_response, _last_disputed_at, _last_pushed_score, run_sync_cycle, sync_one_agent
from tests.helpers import new_agent

_ORACLE_URL = "http://oracle.test"


def _ais_response(*, entropy=800.0, grounding=700.0, sacrifice=600.0, compliance=1000.0, zk_boost=1.0) -> dict:
    return {
        "agent_id": "unused",
        "ais": (entropy * 0.30 + grounding * 0.30 + sacrifice * 0.20 + compliance * 0.20) * zk_boost,
        "components": {"entropy": entropy, "grounding": grounding, "sacrifice": sacrifice, "compliance": compliance},
        "weights": {"entropy": 0.30, "grounding": 0.30, "sacrifice": 0.20, "compliance": 0.20},
        "zk_boost": zk_boost,
        "zk_proof_verified": zk_boost != 1.0,
        "period_start": "2026-01-01T00:00:00Z",
        "period_end": "2026-01-02T00:00:00Z",
        "event_count": 10,
        "onchain_zk_boost_consistent": None,
    }


def _volume(total: int, flagged: int) -> list[dict]:
    if total == 0:
        return []
    return [{"bucket_start": "2026-01-01T00:00:00Z", "count": total, "flagged_count": flagged}]


def _mock_agent(
    respx_mock: respx.MockRouter,
    agent_id: str,
    *,
    sovereign_agent: str,
    reputation_registry: str | None,
    slasher: str | None = None,
    ais: dict | None = None,
    volume: list[dict] | None = None,
) -> None:
    primitives = {"sovereign_agent": sovereign_agent}
    if reputation_registry:
        primitives["reputation_registry"] = reputation_registry
    if slasher:
        primitives["slasher"] = slasher
    respx_mock.get(f"{_ORACLE_URL}/v1/agent/{agent_id}").mock(
        return_value=Response(200, json={"id": agent_id, "verification_tier": 1, "primitives": primitives})
    )
    resolve_agent_primitives.cache_clear()
    if ais is not None:
        respx_mock.get(f"{_ORACLE_URL}/v1/agent/{agent_id}/ais").mock(return_value=Response(200, json=ais))
    if volume is not None:
        respx_mock.get(f"{_ORACLE_URL}/v1/agent/{agent_id}/telemetry/volume").mock(return_value=Response(200, json=volume))


def _settings(anvil_chain, **overrides) -> Settings:
    return Settings(
        rpc_url=anvil_chain["rpc_url"],
        oracle_url=_ORACLE_URL,
        anchor_signer_private_key=anvil_chain["signer_private_key"],
        dispute_min_events=5,
        dispute_flagged_ratio_threshold=0.5,
        dispute_stake_bps=1000,
        dispute_cooldown_seconds=3600,
        **overrides,
    )


# --- _base_score_from_ais_response ------------------------------------------------


def test_base_score_recomputed_from_components_and_weights():
    ais = _ais_response(entropy=1000.0, grounding=1000.0, sacrifice=1000.0, compliance=1000.0, zk_boost=1.15)
    # weighted sum of an all-1000 agent is 1000 regardless of the boost.
    assert _base_score_from_ais_response(ais) == 1000


def test_base_score_none_when_components_missing():
    assert _base_score_from_ais_response({"weights": {}}) is None
    assert _base_score_from_ais_response({"components": {}}) is None


# --- sync_one_agent: score push ----------------------------------------------------


def test_sync_one_agent_pushes_real_base_score(anvil_chain):
    agent_id, _ = new_agent()
    sovereign_agent = Account.create().address
    settings = _settings(anvil_chain)

    with respx.mock as respx_mock:
        _mock_agent(
            respx_mock,
            agent_id,
            sovereign_agent=sovereign_agent,
            reputation_registry=anvil_chain["reputation_registry_address"],
            ais=_ais_response(entropy=900.0, grounding=900.0, sacrifice=900.0, compliance=900.0),
        )
        result = sync_one_agent(settings, agent_id, now=1_000_000.0)

    assert result.score_pushed, result.score_detail
    w3 = anvil_chain["w3"]
    contract = w3.eth.contract(address=anvil_chain["reputation_registry_address"], abi=anvil_chain["reputation_registry_abi"])
    assert contract.functions.baseScoreOf(sovereign_agent).call() == 900


def test_sync_one_agent_skips_push_when_primitives_missing_reputation_registry(anvil_chain):
    agent_id, _ = new_agent()
    settings = _settings(anvil_chain)

    with respx.mock as respx_mock:
        _mock_agent(respx_mock, agent_id, sovereign_agent=Account.create().address, reputation_registry=None)
        result = sync_one_agent(settings, agent_id, now=1_000_000.0)

    assert not result.score_pushed
    assert "reputation_registry" in result.score_detail


def test_sync_one_agent_fails_gracefully_when_agent_unknown_to_oracle(anvil_chain):
    settings = _settings(anvil_chain)
    with respx.mock as respx_mock:
        respx_mock.get(f"{_ORACLE_URL}/v1/agent/did:integrity:unknown").mock(return_value=Response(404))
        resolve_agent_primitives.cache_clear()
        result = sync_one_agent(settings, "did:integrity:unknown", now=1_000_000.0)

    assert not result.score_pushed
    assert not result.dispute_raised


# --- sync_one_agent: dispute logic --------------------------------------------------


def test_sync_one_agent_does_not_dispute_below_min_events(anvil_chain):
    agent_id, _ = new_agent()
    sovereign_agent = Account.create().address
    settings = _settings(anvil_chain)

    with respx.mock as respx_mock:
        _mock_agent(
            respx_mock, agent_id, sovereign_agent=sovereign_agent,
            reputation_registry=anvil_chain["reputation_registry_address"],
            slasher=anvil_chain["slasher_address"],
            ais=_ais_response(),
            volume=_volume(total=3, flagged=3),  # 100% flagged, but below dispute_min_events=5
        )
        result = sync_one_agent(settings, agent_id, now=1_000_000.0)

    assert not result.dispute_raised


def test_sync_one_agent_does_not_dispute_below_ratio_threshold(anvil_chain):
    agent_id, _ = new_agent()
    sovereign_agent = Account.create().address
    settings = _settings(anvil_chain)

    with respx.mock as respx_mock:
        _mock_agent(
            respx_mock, agent_id, sovereign_agent=sovereign_agent,
            reputation_registry=anvil_chain["reputation_registry_address"],
            slasher=anvil_chain["slasher_address"],
            ais=_ais_response(),
            volume=_volume(total=10, flagged=2),  # 20% flagged, below 0.5 threshold
        )
        result = sync_one_agent(settings, agent_id, now=1_000_000.0)

    assert not result.dispute_raised


def test_sync_one_agent_raises_real_dispute_above_threshold_with_stake(anvil_chain):
    agent_id, _ = new_agent()
    sovereign_agent = Account.create().address
    settings = _settings(anvil_chain)

    w3 = anvil_chain["w3"]
    slasher = w3.eth.contract(address=anvil_chain["slasher_address"], abi=anvil_chain["slasher_abi"])
    account = Account.from_key(anvil_chain["signer_private_key"])
    tx = slasher.functions.seedStake(sovereign_agent, 1_000).build_transaction(
        {"from": account.address, "nonce": w3.eth.get_transaction_count(account.address), "chainId": anvil_chain["chain_id"]}
    )
    signed = account.sign_transaction(tx)
    w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction), timeout=30)

    with respx.mock as respx_mock:
        _mock_agent(
            respx_mock, agent_id, sovereign_agent=sovereign_agent,
            reputation_registry=anvil_chain["reputation_registry_address"],
            slasher=anvil_chain["slasher_address"],
            ais=_ais_response(),
            volume=_volume(total=10, flagged=6),  # 60% flagged, at/above 0.5 threshold
        )
        result = sync_one_agent(settings, agent_id, now=1_000_000.0)

    assert result.dispute_raised, result.dispute_detail
    # dispute_stake_bps=1000 (10%) of 1000 available stake = 100 locked.
    assert get_available_stake(settings, anvil_chain["slasher_address"], sovereign_agent) == 900


def test_sync_one_agent_respects_dispute_cooldown(anvil_chain):
    agent_id, _ = new_agent()
    sovereign_agent = Account.create().address
    settings = _settings(anvil_chain)
    _last_disputed_at.pop(agent_id, None)

    w3 = anvil_chain["w3"]
    slasher = w3.eth.contract(address=anvil_chain["slasher_address"], abi=anvil_chain["slasher_abi"])
    account = Account.from_key(anvil_chain["signer_private_key"])
    tx = slasher.functions.seedStake(sovereign_agent, 1_000).build_transaction(
        {"from": account.address, "nonce": w3.eth.get_transaction_count(account.address), "chainId": anvil_chain["chain_id"]}
    )
    signed = account.sign_transaction(tx)
    w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction), timeout=30)

    with respx.mock as respx_mock:
        _mock_agent(
            respx_mock, agent_id, sovereign_agent=sovereign_agent,
            reputation_registry=anvil_chain["reputation_registry_address"],
            slasher=anvil_chain["slasher_address"],
            ais=_ais_response(),
            volume=_volume(total=10, flagged=6),
        )
        first = sync_one_agent(settings, agent_id, now=1_000_000.0)
        second = sync_one_agent(settings, agent_id, now=1_000_100.0)  # 100s later, well inside the 1h cooldown

    assert first.dispute_raised
    assert not second.dispute_raised
    _last_disputed_at.pop(agent_id, None)


def test_sync_one_agent_never_disputes_when_disabled(anvil_chain):
    agent_id, _ = new_agent()
    sovereign_agent = Account.create().address
    settings = _settings(anvil_chain, dispute_enabled=False)

    with respx.mock as respx_mock:
        _mock_agent(
            respx_mock, agent_id, sovereign_agent=sovereign_agent,
            reputation_registry=anvil_chain["reputation_registry_address"],
            slasher=anvil_chain["slasher_address"],
            ais=_ais_response(),
            volume=_volume(total=10, flagged=10),
        )
        result = sync_one_agent(settings, agent_id, now=1_000_000.0)

    assert result.score_pushed
    assert not result.dispute_raised


# --- run_sync_cycle -----------------------------------------------------------------


def test_run_sync_cycle_aggregates_across_agents(anvil_chain):
    agent_a, _ = new_agent()
    agent_b, _ = new_agent()
    settings = _settings(anvil_chain)

    with respx.mock as respx_mock:
        respx_mock.get(f"{_ORACLE_URL}/v1/agents").mock(
            return_value=Response(200, json=[{"id": agent_a, "verification_tier": 1}, {"id": agent_b, "verification_tier": 1}])
        )
        for agent_id in (agent_a, agent_b):
            _mock_agent(
                respx_mock, agent_id, sovereign_agent=Account.create().address,
                reputation_registry=anvil_chain["reputation_registry_address"],
                ais=_ais_response(),
            )
        result = run_sync_cycle(settings, now=1_000_000.0)

    assert result.agents_seen == 2
    assert len(result.results) == 2
    assert all(r.score_pushed for r in result.results)


def test_run_sync_cycle_records_error_when_oracle_unreachable():
    settings = Settings(rpc_url="http://127.0.0.1:1", oracle_url="http://127.0.0.1:1")
    result = run_sync_cycle(settings, now=1_000_000.0)
    assert result.agents_seen == 0
    assert result.errors


# --- unchanged-score push skipping (PRODUCTION_GAPS.md §5) ---------------------------


def test_sync_one_agent_skips_the_real_push_when_score_is_unchanged(anvil_chain):
    """Real regression test: a second cycle with the identical base_score
    must NOT submit a second on-chain transaction -- confirmed by reading
    back the ReputationRegistry's own tx-count-independent state (the
    `score_pushed` flag plus a distinguishable 'unchanged' detail), not just
    by asserting on in-memory bookkeeping."""
    agent_id, _ = new_agent()
    sovereign_agent = Account.create().address
    settings = _settings(anvil_chain)
    _last_pushed_score.pop(agent_id, None)

    with respx.mock as respx_mock:
        _mock_agent(
            respx_mock, agent_id, sovereign_agent=sovereign_agent,
            reputation_registry=anvil_chain["reputation_registry_address"],
            ais=_ais_response(),
        )
        first = sync_one_agent(settings, agent_id, now=1_000_000.0)
        second = sync_one_agent(settings, agent_id, now=1_000_100.0)

    assert first.score_pushed
    assert not second.score_pushed
    assert "unchanged" in second.score_detail
    _last_pushed_score.pop(agent_id, None)


def test_sync_one_agent_pushes_again_when_score_changes(anvil_chain):
    agent_id, _ = new_agent()
    sovereign_agent = Account.create().address
    settings = _settings(anvil_chain)
    _last_pushed_score.pop(agent_id, None)

    with respx.mock as respx_mock:
        _mock_agent(
            respx_mock, agent_id, sovereign_agent=sovereign_agent,
            reputation_registry=anvil_chain["reputation_registry_address"],
            ais=_ais_response(entropy=800.0),
        )
        first = sync_one_agent(settings, agent_id, now=1_000_000.0)

    with respx.mock as respx_mock:
        _mock_agent(
            respx_mock, agent_id, sovereign_agent=sovereign_agent,
            reputation_registry=anvil_chain["reputation_registry_address"],
            ais=_ais_response(entropy=200.0),  # genuinely different base_score
        )
        second = sync_one_agent(settings, agent_id, now=1_000_100.0)

    assert first.score_pushed
    assert second.score_pushed
    assert "unchanged" not in second.score_detail

    w3 = anvil_chain["w3"]
    contract = w3.eth.contract(address=anvil_chain["reputation_registry_address"], abi=anvil_chain["reputation_registry_abi"])
    on_chain_score = contract.functions.baseScoreOf(sovereign_agent).call()
    assert on_chain_score == round(200.0 * 0.30 + 700.0 * 0.30 + 600.0 * 0.20 + 1000.0 * 0.20)
    _last_pushed_score.pop(agent_id, None)
