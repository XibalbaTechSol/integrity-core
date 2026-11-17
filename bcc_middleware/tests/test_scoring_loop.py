"""
Tests for app/scoring_loop.py: list agents from the oracle, post each one's AIS to the real fixture
`AISRegistry` as a checkpoint, and raise real `StakeVault` disputes on a flagged-telemetry threshold.

The oracle's HTTP surface is mocked with respx (there is no real integrity-oracle in this suite).
Actor resolution and every chain write are REAL calls against the session anvil fixtures: the
agent's actor comes from the fixture `AgentRegistry` (`bind_actor`), not from the oracle.
"""

from __future__ import annotations

import math

import pytest
import respx
from eth_account import Account
from httpx import Response

from app.config import Settings
from app.reputation import get_available_stake
from app.scoring_loop import _last_disputed_at, _last_pushed, _score_bps_from_ais_response, run_sync_cycle, sync_one_agent
from tests.helpers import bind_actor, chain_settings, fixture_contract, new_agent, send_tx

_ORACLE_URL = "http://oracle.test"


@pytest.fixture(autouse=True)
def _reset_loop_state():
    _last_pushed.clear()
    _last_disputed_at.clear()
    yield
    _last_pushed.clear()
    _last_disputed_at.clear()


def _ais_response(ais: float = 700.0, **extra) -> dict:
    return {
        "agent_id": "unused",
        "ais": ais,
        "components": {"entropy": 800.0, "grounding": 700.0, "sacrifice": 600.0, "compliance": 1000.0},
        "weights": {"entropy": 0.30, "grounding": 0.30, "sacrifice": 0.20, "compliance": 0.20},
        "period_start": "2026-01-01T00:00:00Z",
        "period_end": "2026-01-02T00:00:00Z",
        "event_count": 10,
        **extra,
    }


def _volume(total: int, flagged: int) -> list[dict]:
    if total == 0:
        return []
    return [{"bucket_start": "2026-01-01T00:00:00Z", "count": total, "flagged_count": flagged}]


def _mock_oracle(respx_mock: respx.MockRouter, agent_id: str, *, ais: dict | None = None, volume: list[dict] | None = None) -> None:
    """Stubs the oracle's AIS and telemetry-volume routes (no volume = no events, so no dispute)."""
    if ais is not None:
        respx_mock.get(f"{_ORACLE_URL}/v1/agent/{agent_id}/ais").mock(return_value=Response(200, json=ais))
    respx_mock.get(f"{_ORACLE_URL}/v1/agent/{agent_id}/telemetry/volume").mock(return_value=Response(200, json=volume or []))


def _agent(anvil_chain) -> tuple[str, str]:
    agent_id, _ = new_agent()
    actor = Account.create().address
    bind_actor(anvil_chain, agent_id, actor)
    return agent_id, actor


def _settings(anvil_chain, **overrides) -> Settings:
    base = {
        "oracle_url": _ORACLE_URL,
        "anchor_signer_private_key": anvil_chain["signer_private_key"],
        "dispute_min_events": 5,
        "dispute_flagged_ratio_threshold": 0.5,
        "dispute_stake_bps": 1000,
        "dispute_cooldown_seconds": 3600,
    }
    return chain_settings(anvil_chain, **{**base, **overrides})


def _checkpoint(anvil_chain, actor: str) -> tuple[int, int, bytes]:
    return tuple(fixture_contract(anvil_chain, "ais_registry").functions.latest(actor).call())


def _seed_stake(anvil_chain, actor: str, amount: int) -> None:
    send_tx(anvil_chain, fixture_contract(anvil_chain, "stake_vault").functions.seedStake(actor, amount))


# --- _score_bps_from_ais_response ------------------------------------------------


def test_score_bps_scales_oracle_ais_to_basis_points():
    assert _score_bps_from_ais_response({"ais": 850.0}) == 8500
    assert _score_bps_from_ais_response({"ais": 0.0}) == 0
    assert _score_bps_from_ais_response({"ais": 1000.0}) == 10_000
    assert _score_bps_from_ais_response({"ais": 612.34}) == 6123


def test_score_bps_ignores_the_dropped_zk_boost():
    """Owner question 2: the boost is gone, so `zk_boost` no longer divides anything out."""
    assert _score_bps_from_ais_response({"ais": 690.0, "zk_boost": 1.15}) == 6900


def test_score_bps_preserves_oracle_tier_ceiling():
    assert _score_bps_from_ais_response({"ais": 600.0, "tier_ceiling": 600.0}) == 6000
    assert _score_bps_from_ais_response({"ais": 601.0, "tier_ceiling": 600.0}) is None


def test_score_bps_rejects_missing_invalid_or_out_of_range_values():
    assert _score_bps_from_ais_response({}) is None
    assert _score_bps_from_ais_response({"ais": "x"}) is None
    assert _score_bps_from_ais_response({"ais": math.nan}) is None
    assert _score_bps_from_ais_response({"ais": -1.0}) is None
    assert _score_bps_from_ais_response({"ais": 1000.1}) is None


# --- sync_one_agent: checkpoint post ----------------------------------------------


def test_sync_one_agent_posts_ais_850_as_8500_bps(anvil_chain):
    """
    The plan's score test: an Oracle AIS of 850 (0..1000) lands on AISRegistry as 8500 bps.

    Mutation proof: posting the raw 850 stores 850, so the readback assertion fails.
    """
    agent_id, actor = _agent(anvil_chain)

    with respx.mock as respx_mock:
        _mock_oracle(respx_mock, agent_id, ais=_ais_response(850.0))
        result = sync_one_agent(_settings(anvil_chain), agent_id, now=1_000_000.0)

    assert result.score_pushed, result.score_detail
    score, window_end, evidence_root = _checkpoint(anvil_chain, actor)
    assert score == 8500
    assert window_end == 1_000_000
    assert evidence_root == b"\x00" * 32


def test_sync_one_agent_skips_an_agent_with_no_actor_without_any_transaction(anvil_chain):
    """
    Owner question 8b: an agent the registry binds no actor to is skipped with NO_ACTOR, and no
    transaction leaves the signer (its nonce is unchanged) and no checkpoint is written. The oracle
    is not even asked for the AIS: respx has no route for it and would raise if it were called.
    """
    agent_id, _ = new_agent()
    bind_actor(anvil_chain, agent_id, None)
    w3 = anvil_chain["w3"]
    signer = Account.from_key(anvil_chain["signer_private_key"]).address
    nonce_before = w3.eth.get_transaction_count(signer)
    count_before = fixture_contract(anvil_chain, "ais_registry").functions.checkpointCount().call()

    with respx.mock:
        result = sync_one_agent(_settings(anvil_chain), agent_id, now=1_000_000.0)

    assert not result.score_pushed
    assert result.score_detail.startswith("NO_ACTOR")
    assert w3.eth.get_transaction_count(signer) == nonce_before
    assert fixture_contract(anvil_chain, "ais_registry").functions.checkpointCount().call() == count_before


def test_sync_one_agent_skips_when_no_ais_registry_is_deployed(anvil_chain, tmp_path):
    import json

    agent_id, _ = _agent(anvil_chain)
    partial = tmp_path / "deployments.json"
    singletons = json.loads(open(anvil_chain["deployments_file"]).read())["singletons"]
    singletons.pop("AISRegistry")
    partial.write_text(json.dumps({"singletons": singletons}))

    result = sync_one_agent(_settings(anvil_chain, deployments_file=str(partial)), agent_id, now=1_000_000.0)

    assert not result.score_pushed
    assert "AISRegistry" in result.score_detail


def test_sync_one_agent_fails_gracefully_for_a_malformed_did(anvil_chain):
    with respx.mock:
        result = sync_one_agent(_settings(anvil_chain), "did:integrity:unknown", now=1_000_000.0)

    assert not result.score_pushed
    assert not result.dispute_raised


def test_sync_one_agent_skips_the_post_when_the_score_is_unchanged(anvil_chain):
    """A second cycle with the identical score must NOT send a second transaction."""
    agent_id, actor = _agent(anvil_chain)
    ais = fixture_contract(anvil_chain, "ais_registry")

    with respx.mock as respx_mock:
        _mock_oracle(respx_mock, agent_id, ais=_ais_response(700.0))
        first = sync_one_agent(_settings(anvil_chain), agent_id, now=1_000_000.0)
        count_after_first = ais.functions.checkpointCount().call()
        second = sync_one_agent(_settings(anvil_chain), agent_id, now=1_000_100.0)

    assert first.score_pushed
    assert not second.score_pushed
    assert "unchanged" in second.score_detail
    assert ais.functions.checkpointCount().call() == count_after_first
    assert _checkpoint(anvil_chain, actor)[1] == 1_000_000  # the window end of the FIRST post


def test_sync_one_agent_posts_again_when_the_score_changes(anvil_chain):
    agent_id, actor = _agent(anvil_chain)

    with respx.mock as respx_mock:
        _mock_oracle(respx_mock, agent_id, ais=_ais_response(700.0))
        first = sync_one_agent(_settings(anvil_chain), agent_id, now=1_000_000.0)
    with respx.mock as respx_mock:
        _mock_oracle(respx_mock, agent_id, ais=_ais_response(420.0))
        second = sync_one_agent(_settings(anvil_chain), agent_id, now=1_000_100.0)

    assert first.score_pushed and second.score_pushed
    assert _checkpoint(anvil_chain, actor)[:2] == (4200, 1_000_100)


def test_sync_one_agent_posts_again_after_the_actor_is_rebound(anvil_chain):
    """The dedupe key includes the actor: a rebound agent gets a checkpoint under its new actor."""
    agent_id, first_actor = _agent(anvil_chain)

    with respx.mock as respx_mock:
        _mock_oracle(respx_mock, agent_id, ais=_ais_response(700.0))
        assert sync_one_agent(_settings(anvil_chain), agent_id, now=1_000_000.0).score_pushed
        second_actor = Account.create().address
        bind_actor(anvil_chain, agent_id, second_actor)
        assert sync_one_agent(_settings(anvil_chain), agent_id, now=1_000_100.0).score_pushed

    assert _checkpoint(anvil_chain, second_actor)[0] == 7000
    assert _checkpoint(anvil_chain, first_actor)[0] == 7000


# --- sync_one_agent: dispute logic --------------------------------------------------


def test_sync_one_agent_does_not_dispute_below_min_events(anvil_chain):
    agent_id, _ = _agent(anvil_chain)
    with respx.mock as respx_mock:
        _mock_oracle(respx_mock, agent_id, ais=_ais_response(), volume=_volume(total=3, flagged=3))
        result = sync_one_agent(_settings(anvil_chain), agent_id, now=1_000_000.0)

    assert not result.dispute_raised


def test_sync_one_agent_does_not_dispute_below_ratio_threshold(anvil_chain):
    agent_id, _ = _agent(anvil_chain)
    with respx.mock as respx_mock:
        _mock_oracle(respx_mock, agent_id, ais=_ais_response(), volume=_volume(total=10, flagged=2))
        result = sync_one_agent(_settings(anvil_chain), agent_id, now=1_000_000.0)

    assert not result.dispute_raised


def test_sync_one_agent_raises_real_dispute_above_threshold_with_stake(anvil_chain):
    agent_id, actor = _agent(anvil_chain)
    _seed_stake(anvil_chain, actor, 1_000)
    settings = _settings(anvil_chain)

    with respx.mock as respx_mock:
        _mock_oracle(respx_mock, agent_id, ais=_ais_response(), volume=_volume(total=10, flagged=6))
        result = sync_one_agent(settings, agent_id, now=1_000_000.0)

    assert result.dispute_raised, result.dispute_detail
    # dispute_stake_bps=1000 (10%) of 1000 available = 100 held, on the ACTOR.
    assert fixture_contract(anvil_chain, "stake_vault").functions.disputeLockedOf(actor).call() == 100
    assert get_available_stake(settings, anvil_chain["stake_vault_address"], actor) == 900


def test_sync_one_agent_respects_dispute_cooldown(anvil_chain):
    agent_id, actor = _agent(anvil_chain)
    _seed_stake(anvil_chain, actor, 1_000)

    with respx.mock as respx_mock:
        _mock_oracle(respx_mock, agent_id, ais=_ais_response(), volume=_volume(total=10, flagged=6))
        first = sync_one_agent(_settings(anvil_chain), agent_id, now=1_000_000.0)
        second = sync_one_agent(_settings(anvil_chain), agent_id, now=1_000_100.0)

    assert first.dispute_raised
    assert not second.dispute_raised


def test_sync_one_agent_never_disputes_when_disabled(anvil_chain):
    agent_id, actor = _agent(anvil_chain)
    _seed_stake(anvil_chain, actor, 1_000)

    with respx.mock as respx_mock:
        _mock_oracle(respx_mock, agent_id, ais=_ais_response(), volume=_volume(total=10, flagged=10))
        result = sync_one_agent(_settings(anvil_chain, dispute_enabled=False), agent_id, now=1_000_000.0)

    assert result.score_pushed
    assert not result.dispute_raised


# --- run_sync_cycle -----------------------------------------------------------------


def test_run_sync_cycle_aggregates_across_agents(anvil_chain):
    (agent_a, _), (agent_b, _) = _agent(anvil_chain), _agent(anvil_chain)

    with respx.mock as respx_mock:
        respx_mock.get(f"{_ORACLE_URL}/v1/agents").mock(
            return_value=Response(200, json=[{"id": agent_a, "verification_tier": 1}, {"id": agent_b, "verification_tier": 1}])
        )
        for agent_id in (agent_a, agent_b):
            _mock_oracle(respx_mock, agent_id, ais=_ais_response())
        result = run_sync_cycle(_settings(anvil_chain), now=1_000_000.0)

    assert result.agents_seen == 2
    assert len(result.results) == 2
    assert all(r.score_pushed for r in result.results)


def test_run_sync_cycle_records_error_when_oracle_unreachable():
    settings = Settings(rpc_url="http://127.0.0.1:1", oracle_url="http://127.0.0.1:1")
    result = run_sync_cycle(settings, now=1_000_000.0)
    assert result.agents_seen == 0
    assert result.errors
