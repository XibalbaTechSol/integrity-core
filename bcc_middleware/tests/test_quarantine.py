"""
Real on-chain tests for app/quarantine.py: `StakeVault.disputeLockedOf(actor)`, with the actor read
from `AgentRegistry.resolveDID(did).actor` and the vault from `AgentRegistry.trustConfig()` ->
`TrustConfig.stakeVault()` (v2 graph deletion slice D2). Run against the session `anvil` and the v3
fixture mocks (tests/conftest.py's `anvil_chain`, tests/fixtures/foundry/src/MockV3Singletons.sol).
"""

from __future__ import annotations

import pytest
import respx
from eth_account import Account

from app.config import Settings
from app.quarantine import QuarantineStatus, check_quarantine_status, fail_closed_for_intent
from tests.helpers import bind_actor, chain_settings, fixture_contract, mock_oracle_agent, new_agent, send_tx

_ORACLE_URL = "http://oracle.test"


def _bound_agent(anvil_chain) -> tuple[str, str]:
    agent_id, _ = new_agent()
    actor = Account.create().address
    bind_actor(anvil_chain, agent_id, actor)
    return agent_id, actor


def test_quarantine_unavailability_is_scoped_by_intent_class():
    settings = Settings()

    assert fail_closed_for_intent(settings, "claude_tool:Bash:chain_write")
    assert fail_closed_for_intent(settings, "EMR_WRITE")
    assert not fail_closed_for_intent(settings, "claude_tool:read_file")


# --- unit-level: check_quarantine_status --------------------------------------


def test_clear_when_no_dispute_is_open(anvil_chain):
    agent_id, actor = _bound_agent(anvil_chain)

    status, detail = check_quarantine_status(chain_settings(anvil_chain), agent_id)

    assert status is QuarantineStatus.CLEAR
    assert f"disputeLockedOf({actor}) == 0" in detail


def test_open_dispute_with_no_action_locks_is_quarantined(anvil_chain):
    """
    The plan's quarantine test: `disputeLockedOf(actor) = 1` with `stakeOf(actor).locked = 0`.

    Mutation proof: reading `stakeOf(actor).locked` instead (per-action locks only) sees 0 here and
    answers CLEAR, so this assertion fails.
    """
    agent_id, actor = _bound_agent(anvil_chain)
    vault = fixture_contract(anvil_chain, "stake_vault")
    send_tx(anvil_chain, vault.functions.seedStake(actor, 10))
    send_tx(anvil_chain, vault.functions.raiseDispute(actor, 1, "flagged telemetry ratio exceeded threshold"))
    assert vault.functions.disputeLockedOf(actor).call() == 1
    assert vault.functions.stakeOf(actor).call()[1] == 0  # no per-action lock

    status, detail = check_quarantine_status(chain_settings(anvil_chain), agent_id)

    assert status is QuarantineStatus.QUARANTINED
    assert "== 1 (active dispute)" in detail


def test_action_lock_alone_is_not_a_quarantine(anvil_chain):
    """The converse: a per-action lock with no dispute must not quarantine the agent."""
    agent_id, actor = _bound_agent(anvil_chain)
    vault = fixture_contract(anvil_chain, "stake_vault")
    send_tx(anvil_chain, vault.functions.seedStake(actor, 10))
    send_tx(anvil_chain, vault.functions.setActionLock(actor, 5))

    status, _ = check_quarantine_status(chain_settings(anvil_chain), agent_id)

    assert status is QuarantineStatus.CLEAR


def test_definite_status_when_the_oracle_returns_no_primitives(anvil_chain):
    """
    Ordering guard (D2 must merge before 4.6): with the oracle answering in 4.6's shape (no
    `primitives` object), quarantine still returns a definite status. On the pre-D2 code, which
    resolved the v2 dispute contract through the oracle's `primitives`, this returned CANNOT_VERIFY.
    """
    agent_id, _ = _bound_agent(anvil_chain)
    with respx.mock(assert_all_called=False, assert_all_mocked=False) as mock:
        mock_oracle_agent(mock, _ORACLE_URL, agent_id)
        settings = chain_settings(anvil_chain, oracle_url=_ORACLE_URL)

        status, detail = check_quarantine_status(settings, agent_id)

    assert status is QuarantineStatus.CLEAR, detail


def test_no_actor_when_the_registry_binds_none(anvil_chain):
    """Owner question 8b: an agent with no actor (Claude today) gets NO_ACTOR, not an error."""
    agent_id, _ = new_agent()
    bind_actor(anvil_chain, agent_id, None)

    status, detail = check_quarantine_status(chain_settings(anvil_chain), agent_id)

    assert status is QuarantineStatus.NO_ACTOR
    assert "NO_ACTOR" in detail


def test_no_actor_for_a_did_the_registry_has_never_seen(anvil_chain):
    agent_id, _ = new_agent()

    status, _ = check_quarantine_status(chain_settings(anvil_chain), agent_id)

    assert status is QuarantineStatus.NO_ACTOR


def test_cannot_verify_for_a_retired_agent(anvil_chain):
    agent_id, _ = new_agent()
    bind_actor(anvil_chain, agent_id, Account.create().address, retired=True)

    status, detail = check_quarantine_status(chain_settings(anvil_chain), agent_id)

    assert status is QuarantineStatus.CANNOT_VERIFY
    assert "retired" in detail


def test_cannot_verify_for_a_malformed_did(anvil_chain):
    """The registry reverts `InvalidDid` on anything but `did:integrity:<64 hex>`."""
    status, _ = check_quarantine_status(chain_settings(anvil_chain), "did:integrity:not-hex")

    assert status is QuarantineStatus.CANNOT_VERIFY


def test_cannot_verify_when_no_agent_registry_is_configured(anvil_chain, tmp_path):
    agent_id, _ = _bound_agent(anvil_chain)
    settings = chain_settings(anvil_chain, deployments_file=str(tmp_path / "missing.json"))

    status, detail = check_quarantine_status(settings, agent_id)

    assert status is QuarantineStatus.CANNOT_VERIFY
    assert "AgentRegistry" in detail


def test_cannot_verify_posture_on_an_unreachable_registry(anvil_chain):
    """
    Pins the caller-visible posture on an unreachable registry RPC: CANNOT_VERIFY, never CLEAR.
    The plan says this behaviour is unchanged by D2; this test records what it is.
    """
    agent_id, _ = new_agent()
    settings = chain_settings(anvil_chain, rpc_url="http://127.0.0.1:1")  # nothing listens on port 1

    status, detail = check_quarantine_status(settings, agent_id)

    assert status is QuarantineStatus.CANNOT_VERIFY
    assert "unreachable" in detail


# --- Full flow: run_intercept ---------------------------------------------------


@pytest.mark.asyncio
async def test_full_intercept_flow_denies_a_quarantined_agent(anvil_chain, real_opa_server):
    """
    End-to-end: a real dispute holds stake for a real actor, and the identical commitment shape
    that would otherwise pass OPA/BAA/etc is denied with AGENT_QUARANTINED before OPA runs.
    """
    import app.main as main_module
    from tests.helpers import make_commitment_model, sign_commitment

    agent_id, private_key = new_agent()
    actor = Account.create().address
    bind_actor(anvil_chain, agent_id, actor)
    vault = fixture_contract(anvil_chain, "stake_vault")
    send_tx(anvil_chain, vault.functions.seedStake(actor, 1000))
    send_tx(anvil_chain, vault.functions.raiseDispute(actor, 250, "test dispute"))

    settings = chain_settings(anvil_chain, opa_url=real_opa_server, oracle_url=_ORACLE_URL)
    payload = sign_commitment(private_key, agent_id=agent_id, intent_type="claude_tool:read_file", nonce=1)

    denied = await main_module.run_intercept(make_commitment_model(**payload), settings)

    assert denied.authorized is False
    assert "AGENT_QUARANTINED" in denied.reason


@pytest.mark.asyncio
async def test_no_actor_denies_fail_closed_intents_like_cannot_verify(anvil_chain, real_opa_server):
    """NO_ACTOR keeps today's CANNOT_VERIFY posture: a fail-closed intent is denied."""
    import app.main as main_module
    from tests.helpers import make_commitment_model, sign_commitment

    agent_id, private_key = new_agent()
    bind_actor(anvil_chain, agent_id, None)
    settings = chain_settings(anvil_chain, opa_url=real_opa_server, oracle_url=_ORACLE_URL)
    payload = sign_commitment(private_key, agent_id=agent_id, intent_type="claude_tool:Bash:chain_write", nonce=1)

    denied = await main_module.run_intercept(make_commitment_model(**payload), settings)

    assert denied.authorized is False
    assert "QUARANTINE_CANNOT_VERIFY" in denied.reason
    assert "NO_ACTOR" in denied.reason
