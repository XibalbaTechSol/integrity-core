"""
Real on-chain tests for app/quarantine.py (Slasher.lockedStakeOf eth_call) — the Active
Quarantine Enforcement gap closed in PRODUCTION_GAPS.md §5. Run against the same real local
`anvil` + MockSlasher fixture app/reputation.py's tests use (see tests/conftest.py's
`anvil_chain` fixture and tests/fixtures/foundry/src/MockSlasher.sol).
"""

from __future__ import annotations

import json

import pytest
import respx
from eth_account import Account

from app.config import Settings
from app.quarantine import QuarantineStatus, check_quarantine_status
from tests.helpers import mock_oracle_agent_resolution, new_agent

_ORACLE_URL = "http://oracle.test"


# --- unit-level: check_quarantine_status --------------------------------------


def test_clear_when_no_stake_locked(anvil_chain):
    with respx.mock(assert_all_called=False, assert_all_mocked=False) as mock:
        settings = Settings(rpc_url=anvil_chain["rpc_url"], oracle_url=_ORACLE_URL)
        agent_id, _ = new_agent()
        agent_address = Account.create().address
        mock_oracle_agent_resolution(
            mock, _ORACLE_URL, agent_id, agent_address, slasher_address=anvil_chain["slasher_address"],
        )

        status, detail = check_quarantine_status(settings, agent_id)

        assert status is QuarantineStatus.CLEAR
        assert "== 0" in detail


def test_quarantined_after_a_real_dispute_locks_stake(anvil_chain):
    """
    Seeds stake and raises a real dispute against the fixture MockSlasher (the same
    real-transaction path app/reputation.py::raise_dispute uses), then confirms
    check_quarantine_status sees the locked stake and reports QUARANTINED.
    """
    w3 = anvil_chain["w3"]
    account = Account.from_key(anvil_chain["signer_private_key"])
    contract = w3.eth.contract(address=anvil_chain["slasher_address"], abi=anvil_chain["slasher_abi"])
    agent_address = Account.create().address

    def _send(fn):
        tx = fn.build_transaction(
            {"from": account.address, "nonce": w3.eth.get_transaction_count(account.address), "chainId": anvil_chain["chain_id"]}
        )
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=15)
        assert receipt.status == 1

    _send(contract.functions.seedStake(agent_address, 1000))
    _send(contract.functions.raiseDispute(agent_address, 500, "flagged telemetry ratio exceeded threshold"))

    with respx.mock(assert_all_called=False, assert_all_mocked=False) as mock:
        settings = Settings(rpc_url=anvil_chain["rpc_url"], oracle_url=_ORACLE_URL)
        agent_id, _ = new_agent()
        mock_oracle_agent_resolution(
            mock, _ORACLE_URL, agent_id, agent_address, slasher_address=anvil_chain["slasher_address"],
        )

        status, detail = check_quarantine_status(settings, agent_id)

        assert status is QuarantineStatus.QUARANTINED
        assert "500" in detail


def test_cannot_verify_when_no_slasher_primitive(anvil_chain):
    with respx.mock(assert_all_called=False, assert_all_mocked=False) as mock:
        settings = Settings(rpc_url=anvil_chain["rpc_url"], oracle_url=_ORACLE_URL)
        agent_id, _ = new_agent()
        agent_address = Account.create().address
        # No "slasher" key at all -- an agent registered before this primitive existed,
        # or an oracle response missing the field.
        mock_oracle_agent_resolution(mock, _ORACLE_URL, agent_id, agent_address)

        status, detail = check_quarantine_status(settings, agent_id)

        assert status is QuarantineStatus.CANNOT_VERIFY
        assert "slasher" in detail


def test_cannot_verify_when_rpc_unreachable():
    settings = Settings(rpc_url="http://127.0.0.1:1", oracle_url=_ORACLE_URL)  # nothing listens on port 1
    with respx.mock(assert_all_called=False, assert_all_mocked=False) as mock:
        agent_id, _ = new_agent()
        agent_address = Account.create().address
        mock_oracle_agent_resolution(
            mock, _ORACLE_URL, agent_id, agent_address,
            slasher_address="0x0000000000000000000000000000000000000001",
        )

        status, detail = check_quarantine_status(settings, agent_id)

        assert status is QuarantineStatus.CANNOT_VERIFY
        assert "unreachable" in detail


def test_cannot_verify_when_agent_unresolvable():
    settings = Settings(rpc_url="http://127.0.0.1:1", oracle_url=_ORACLE_URL)
    # No respx mock registered at all -- resolve_agent_primitives itself fails.
    with respx.mock() as mock:
        import httpx

        mock.get(f"{_ORACLE_URL}/v1/agent/unresolvable-agent").mock(side_effect=httpx.ConnectError("refused"))

        status, detail = check_quarantine_status(settings, "unresolvable-agent")

        assert status is QuarantineStatus.CANNOT_VERIFY


# --- Full flow: run_intercept denies a quarantined agent before OPA ever runs -----


@pytest.mark.asyncio
async def test_full_intercept_flow_denies_a_quarantined_agent(anvil_chain, real_opa_server, monkeypatch):
    """
    End-to-end: a real dispute locks stake for a real agent address, and the identical
    commitment shape that would otherwise pass OPA/BAA/etc is denied with
    AGENT_QUARANTINED before OPA is even evaluated.
    """
    import app.main as main_module
    from tests.helpers import make_commitment_model, sign_commitment

    w3 = anvil_chain["w3"]
    account = Account.from_key(anvil_chain["signer_private_key"])
    contract = w3.eth.contract(address=anvil_chain["slasher_address"], abi=anvil_chain["slasher_abi"])
    agent_id, private_key = new_agent()
    agent_address = Account.create().address

    def _send(fn):
        tx = fn.build_transaction(
            {"from": account.address, "nonce": w3.eth.get_transaction_count(account.address), "chainId": anvil_chain["chain_id"]}
        )
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=15)
        assert receipt.status == 1

    _send(contract.functions.seedStake(agent_address, 1000))
    _send(contract.functions.raiseDispute(agent_address, 250, "test dispute"))

    primitives = {"sovereign_agent": agent_address, "slasher": anvil_chain["slasher_address"]}
    monkeypatch.setattr("app.chain.resolve_agent_primitives", lambda oracle_url, aid: primitives)
    monkeypatch.setattr("app.quarantine.resolve_agent_primitives", lambda oracle_url, aid: primitives)

    settings = Settings(opa_url=real_opa_server, rpc_url=anvil_chain["rpc_url"], oracle_url=_ORACLE_URL)

    payload = sign_commitment(private_key, agent_id=agent_id, intent_type="claude_tool:read_file", nonce=1)
    commitment = make_commitment_model(**payload)

    denied = await main_module.run_intercept(commitment, settings)

    assert denied.authorized is False
    assert "AGENT_QUARANTINED" in denied.reason
