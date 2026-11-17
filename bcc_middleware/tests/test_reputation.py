"""
Real on-chain tests for app/reputation.py: `AISRegistry.postCheckpoint` and `StakeVault.raiseDispute`
transactions and the `StakeVault.availableOf` read, against the session `anvil` and the v3 fixture
mocks (tests/conftest.py's `anvil_chain`). The middleware calls the mocks through the canonical ABIs
in integrity_sdk/abis/, so a selector or tuple-shape drift from the real contracts fails here.
"""

from __future__ import annotations

from eth_account import Account

from app.config import Settings
from app.reputation import get_available_stake, post_checkpoint, raise_dispute
from tests.helpers import bind_actor, chain_settings, fixture_contract, new_agent, send_tx


def _settings(anvil_chain, **overrides) -> Settings:
    return chain_settings(anvil_chain, **{"anchor_signer_private_key": anvil_chain["signer_private_key"], **overrides})


def _registered_actor(anvil_chain) -> str:
    agent_id, _ = new_agent()
    actor = Account.create().address
    bind_actor(anvil_chain, agent_id, actor)
    return actor


def _seed_stake(anvil_chain, actor: str, amount: int) -> None:
    send_tx(anvil_chain, fixture_contract(anvil_chain, "stake_vault").functions.seedStake(actor, amount))


# --- post_checkpoint ------------------------------------------------------------


def test_post_checkpoint_submits_a_real_transaction(anvil_chain):
    actor = _registered_actor(anvil_chain)

    result = post_checkpoint(_settings(anvil_chain), anvil_chain["ais_registry_address"], actor, 7420, 1_000_000)

    assert result.submitted, result.detail
    assert result.tx_hash is not None
    ais = fixture_contract(anvil_chain, "ais_registry")
    score, window_end, evidence_root = ais.functions.latest(actor).call()
    assert (score, window_end, evidence_root) == (7420, 1_000_000, b"\x00" * 32)
    assert ais.functions.lastReleasable(actor).call() == 0


def test_post_checkpoint_uses_dedicated_reputation_signer_when_set(anvil_chain):
    """A distinct REPUTATION_SIGNER_PRIVATE_KEY, when set, takes priority over the anchor signer."""
    settings = _settings(
        anvil_chain,
        anchor_signer_private_key="0x" + "11" * 32,  # unfunded and not a scorer: must NOT be used
        reputation_signer_private_key=anvil_chain["signer_private_key"],
    )

    result = post_checkpoint(settings, anvil_chain["ais_registry_address"], _registered_actor(anvil_chain), 5000, 1)

    assert result.submitted, result.detail


def test_post_checkpoint_fails_for_an_actor_the_registry_does_not_list(anvil_chain):
    result = post_checkpoint(_settings(anvil_chain), anvil_chain["ais_registry_address"], Account.create().address, 5000, 1)

    assert not result.submitted
    assert "failed" in result.detail or "reverted" in result.detail


def test_post_checkpoint_refuses_a_score_outside_basis_points(anvil_chain):
    result = post_checkpoint(_settings(anvil_chain), anvil_chain["ais_registry_address"], _registered_actor(anvil_chain), 10_001, 1)

    assert not result.submitted
    assert "0..10000" in result.detail


def test_post_checkpoint_is_best_effort_when_no_signer_configured(anvil_chain):
    settings = _settings(anvil_chain, anchor_signer_private_key=None, reputation_signer_private_key=None)
    result = post_checkpoint(settings, anvil_chain["ais_registry_address"], Account.create().address, 100, 1)
    assert not result.submitted
    assert "signer" in result.detail


def test_post_checkpoint_is_best_effort_when_rpc_unreachable():
    settings = Settings(rpc_url="http://127.0.0.1:1", anchor_signer_private_key="0x" + "22" * 32)
    result = post_checkpoint(settings, "0x" + "00" * 20, Account.create().address, 100, 1)
    assert not result.submitted
    assert "unreachable" in result.detail


# --- get_available_stake / raise_dispute -----------------------------------------


def test_get_available_stake_is_availableOf(anvil_chain):
    actor = Account.create().address
    _seed_stake(anvil_chain, actor, 1_000)
    send_tx(anvil_chain, fixture_contract(anvil_chain, "stake_vault").functions.setActionLock(actor, 300))

    # availableOf nets out the action lock; stakeOf().amount alone would say 1000.
    assert get_available_stake(_settings(anvil_chain), anvil_chain["stake_vault_address"], actor) == 700


def test_get_available_stake_returns_none_when_rpc_unreachable():
    settings = Settings(rpc_url="http://127.0.0.1:1")
    assert get_available_stake(settings, "0x" + "00" * 20, Account.create().address) is None


def test_raise_dispute_submits_a_real_transaction_and_holds_stake(anvil_chain):
    settings = _settings(anvil_chain)
    actor = Account.create().address
    _seed_stake(anvil_chain, actor, 1_000)

    result = raise_dispute(settings, anvil_chain["stake_vault_address"], actor, 100, "oracle-flagged telemetry ratio 6/10 (60%)")

    assert result.submitted, result.detail
    assert result.tx_hash is not None
    # dispute ids count up on the shared, session-scoped fixture vault.
    assert isinstance(result.dispute_id, int) and result.dispute_id >= 0
    assert fixture_contract(anvil_chain, "stake_vault").functions.disputeLockedOf(actor).call() == 100
    assert get_available_stake(settings, anvil_chain["stake_vault_address"], actor) == 900


def test_raise_dispute_fails_when_amount_exceeds_available_stake(anvil_chain):
    actor = Account.create().address
    _seed_stake(anvil_chain, actor, 50)

    result = raise_dispute(_settings(anvil_chain), anvil_chain["stake_vault_address"], actor, 100, "insufficient stake case")

    assert not result.submitted


def test_raise_dispute_is_best_effort_when_no_signer_configured(anvil_chain):
    settings = _settings(anvil_chain, anchor_signer_private_key=None, reputation_signer_private_key=None)
    result = raise_dispute(settings, anvil_chain["stake_vault_address"], Account.create().address, 100, "no signer case")
    assert not result.submitted
    assert "signer" in result.detail
