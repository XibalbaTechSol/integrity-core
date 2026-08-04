"""
Real on-chain tests for app/baa.py (isBAAActive eth_call) and app/anchor.py
(anchorRoot eth_sendTransaction), run against a real local `anvil` instance
with the minimal fixture contracts in tests/fixtures/foundry/src/ actually
deployed to it (see the `anvil_chain` fixture in conftest.py).

This is the "prove the eth_call/eth_sendTransaction code path for real
before contracts/ exists" requirement: once `contracts/` deploys the real
SmartBAA / StateAnchor, only the address changes -- this exact code is what
runs against them.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from httpx import Response

from eth_account import Account

from app.baa import BAAStatus, check_baa_status
from app.anchor import anchor_root
from app.chain import agent_id_to_address, resolve_verification_tier
from app.config import Settings
from tests.helpers import mock_oracle_agent_resolution, new_agent

_ORACLE_URL = "http://oracle.test"


# --- verification tier resolution ---------------------------------------------


def test_resolve_verification_tier_returns_oracle_value():
    with respx.mock(assert_all_called=False, assert_all_mocked=False) as mock:
        agent_id, _ = new_agent()
        mock_oracle_agent_resolution(mock, _ORACLE_URL, agent_id, Account.create().address, verification_tier=1)

        assert resolve_verification_tier(agent_id, oracle_url=_ORACLE_URL) == 1


def test_resolve_verification_tier_fails_closed_to_zero_when_oracle_unreachable():
    # No respx mock registered for this agent_id -- respx raises on the
    # unmatched request (assert_all_mocked defaults True), which resolve_
    # verification_tier must catch and turn into tier 0, not propagate.
    with respx.mock() as mock:
        mock.get(f"{_ORACLE_URL}/v1/agent/some_unresolvable_agent").mock(side_effect=httpx.ConnectError("connection refused"))

        assert resolve_verification_tier("some_unresolvable_agent", oracle_url=_ORACLE_URL) == 0


def test_resolve_verification_tier_fails_closed_to_zero_on_malformed_response():
    with respx.mock() as mock:
        agent_id = "some_agent_with_bad_response"
        mock.get(f"{_ORACLE_URL}/v1/agent/{agent_id}").mock(return_value=Response(200, json={"id": agent_id}))  # no verification_tier field

        assert resolve_verification_tier(agent_id, oracle_url=_ORACLE_URL) == 0


def _dummy_covered_entity() -> str:
    """
    A fresh, real EVM address to stand in for "the hospital" in tests that
    only care about the mock registry's active/inactive flag, not about
    real CoveredEntityRegistry/SmartBAAFactory semantics (see
    tests/test_baa_health_integration.py for that). Generated fresh per
    call so tests don't accidentally share state through a shared address.
    """
    return Account.create().address


# --- BAA on-chain check -------------------------------------------------------


def test_baa_inactive_by_default(anvil_chain):
    with respx.mock(assert_all_called=False, assert_all_mocked=False) as mock:
        settings = Settings(rpc_url=anvil_chain["rpc_url"], oracle_url=_ORACLE_URL)
        agent_id, _ = new_agent()
        mock_oracle_agent_resolution(mock, _ORACLE_URL, agent_id, Account.create().address)
        covered_entity = _dummy_covered_entity()

        status, detail = check_baa_status(settings, agent_id, covered_entity, contract_address=anvil_chain["baa_address"])

        assert status is BAAStatus.INACTIVE
        assert "isBAAActive" in detail


def test_baa_active_after_setActive_transaction(anvil_chain):
    """
    Actually sends a real `setActive` transaction (fixture-only setter, not
    part of the real interface) to flip the on-chain flag, then confirms
    our real `isBAAActive` eth_call sees the updated state.

    Real SmartBAAFactory.isBAAActive is keyed on the (coveredEntity,
    businessAssociate) PAIR (see app/baa.py's module docstring on why this
    fixture and the ABI it's called with are both two-argument now), so
    this also proves flipping the flag for a *different* covered entity
    against the same agent does NOT make this pair active.
    """
    with respx.mock(assert_all_called=False, assert_all_mocked=False) as mock:
        w3 = anvil_chain["w3"]
        agent_id, private_key = new_agent()
        agent_address = Account.create().address
        mock_oracle_agent_resolution(mock, _ORACLE_URL, agent_id, agent_address)
        covered_entity = _dummy_covered_entity()
        other_covered_entity = _dummy_covered_entity()

        account = Account.from_key(anvil_chain["signer_private_key"])
        contract = w3.eth.contract(address=anvil_chain["baa_address"], abi=anvil_chain["baa_abi"])
        tx = contract.functions.setActive(covered_entity, agent_address, True).build_transaction(
            {"from": account.address, "nonce": w3.eth.get_transaction_count(account.address), "chainId": anvil_chain["chain_id"]}
        )
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=15)
        assert receipt.status == 1

        settings = Settings(rpc_url=anvil_chain["rpc_url"], oracle_url=_ORACLE_URL)
        status, detail = check_baa_status(settings, agent_id, covered_entity, contract_address=anvil_chain["baa_address"])
        assert status is BAAStatus.ACTIVE

        # A BAA active with `covered_entity` says nothing about `other_covered_entity`.
        other_status, _ = check_baa_status(settings, agent_id, other_covered_entity, contract_address=anvil_chain["baa_address"])
        assert other_status is BAAStatus.INACTIVE


def test_baa_cannot_verify_when_no_contract_configured(anvil_chain):
    # Explicit, nonexistent deployments_file: without this, Settings() would
    # fall back to the real repo-root deployments.local.json, which (as of
    # this repo's real Base Sepolia + local anvil deploys) genuinely HAS a
    # SmartBAAFactory entry -- silently defeating the "nothing configured"
    # scenario this test means to exercise.
    settings = Settings(rpc_url=anvil_chain["rpc_url"], deployments_file="/nonexistent/deployments.json")
    agent_id, _ = new_agent()

    status, detail = check_baa_status(settings, agent_id, _dummy_covered_entity(), contract_address=None)

    assert status is BAAStatus.CANNOT_VERIFY
    assert "no " in detail


def test_baa_cannot_verify_when_rpc_unreachable():
    settings = Settings(rpc_url="http://127.0.0.1:1")  # nothing listens on port 1
    agent_id, _ = new_agent()

    status, detail = check_baa_status(
        settings, agent_id, _dummy_covered_entity(), contract_address="0x0000000000000000000000000000000000000001"
    )

    assert status is BAAStatus.CANNOT_VERIFY
    assert "unreachable" in detail


def test_baa_cannot_verify_when_covered_entity_address_missing(anvil_chain):
    """
    Fail-closed per app/baa.py: a healthcare-vertical commitment that never
    got a covered_entity_address (e.g. an old/misbehaving client, or a
    schema mismatch) must never fall back to "assume compliant" -- there's
    no address to even attempt an eth_call with.
    """
    settings = Settings(rpc_url=anvil_chain["rpc_url"])
    agent_id, _ = new_agent()

    status, detail = check_baa_status(settings, agent_id, None, contract_address=anvil_chain["baa_address"])

    assert status is BAAStatus.CANNOT_VERIFY
    assert "covered_entity_address" in detail


# --- Merkle root anchoring -----------------------------------------------------


def test_anchor_root_submits_a_real_transaction(anvil_chain):
    settings = Settings(rpc_url=anvil_chain["rpc_url"], anchor_signer_private_key=anvil_chain["signer_private_key"])
    fake_root = b"\x11" * 32

    result = anchor_root(settings, fake_root, contract_address=anvil_chain["anchor_address"])

    assert result.submitted is True
    assert result.tx_hash is not None

    # Confirm the transaction actually changed on-chain state, not just that
    # send_raw_transaction didn't throw.
    w3 = anvil_chain["w3"]
    root_bytes = w3.eth.call(
        {
            "to": anvil_chain["anchor_address"],
            "data": w3.keccak(text="lastRoot()")[:4],
        }
    )
    assert root_bytes == fake_root


def test_anchor_root_is_best_effort_when_contract_not_configured(anvil_chain):
    settings = Settings(rpc_url=anvil_chain["rpc_url"], anchor_signer_private_key=anvil_chain["signer_private_key"])

    result = anchor_root(settings, b"\x22" * 32, contract_address=None)

    assert result.submitted is False
    assert "no " in result.detail


def test_anchor_root_is_best_effort_when_signer_not_configured(anvil_chain):
    settings = Settings(rpc_url=anvil_chain["rpc_url"], anchor_signer_private_key=None)

    result = anchor_root(settings, b"\x33" * 32, contract_address=anvil_chain["anchor_address"])

    assert result.submitted is False
    assert "ANCHOR_SIGNER_PRIVATE_KEY" in result.detail


# --- Full flow: run_intercept wiring OPA's requires_baa into the real chain check ---


@pytest.mark.asyncio
async def test_full_intercept_flow_gates_on_real_on_chain_baa_status(
    anvil_chain, always_allow_requires_baa_opa_server, tmp_path, monkeypatch
):
    """
    End-to-end: real signature + a real (trivial) OPA server that always
    says allow=true/requires_baa=true + a real deployed MockBAARegistry
    that starts inactive. First attempt must be denied (BAA inactive);
    after a real setActive transaction, the identical commitment shape
    (fresh nonce) must be authorized. Also exercises real anchoring by
    setting merkle_batch_size=1 so the approved commitment flushes and
    anchors on-chain immediately.
    """
    import app.main as main_module
    from app.merkle import MerkleBatcher, merkle_root, leaf_hash
    from tests.helpers import make_commitment_model, mock_oracle_agent_resolution, sign_commitment

    deployments_file = tmp_path / "deployments.local.json"
    deployments_file.write_text(
        json.dumps(
            {
                "chainId": anvil_chain["chain_id"],
                "singletons": {"SmartBAAFactory": anvil_chain["baa_address"]},
            }
        )
    )

    settings = Settings(
        opa_url=always_allow_requires_baa_opa_server,
        rpc_url=anvil_chain["rpc_url"],
        oracle_url=_ORACLE_URL,
        deployments_file=str(deployments_file),
        anchor_signer_private_key=anvil_chain["signer_private_key"],
        merkle_batch_size=1,
    )
    # `batcher` is a process-wide singleton whose batch_size is fixed at
    # startup (see app/main.py) -- `settings.merkle_batch_size` above only
    # documents intent for this test, it doesn't retroactively resize the
    # shared batcher. Swap in a fresh batch_size=1 instance so this test's
    # single approved commitment actually triggers an immediate flush, and
    # so we're not reading batch state left over from other tests sharing
    # the (session-scoped) anvil_chain fixture.
    monkeypatch.setattr(main_module, "batcher", MerkleBatcher(batch_size=1))

    w3 = anvil_chain["w3"]

    def _read_anchor_state():
        last_root = w3.eth.call({"to": anvil_chain["anchor_address"], "data": w3.keccak(text="lastRoot()")[:4]})
        root_count = w3.eth.call({"to": anvil_chain["anchor_address"], "data": w3.keccak(text="rootCount()")[:4]})
        return last_root, int.from_bytes(root_count, "big")

    _, root_count_before = _read_anchor_state()

    agent_id, private_key = new_agent()
    agent_address = Account.create().address
    covered_entity = Account.create().address

    # This test exercises a REAL OPA server over real HTTP (see
    # always_allow_requires_baa_opa_server) in the same code path as the
    # oracle's agent-resolution lookup, so wrapping both in one respx.mock()
    # context is fragile -- respx intercepting/passing-through the OPA
    # traffic alongside a mocked oracle route proved to make the real OPA
    # call come back with an empty, non-JSON body. Since the only thing this
    # test needs from the oracle is a canned primitive-address lookup (it
    # isn't testing the oracle boundary itself -- that's
    # mock_oracle_agent_resolution's job in the other tests in this file),
    # monkeypatch resolve_agent_primitives directly instead. It's imported by
    # value into both app.chain (via check_baa_status -> agent_id_to_address)
    # and app.anchor (via `from app.chain import resolve_agent_primitives`),
    # so both bindings must be patched or per-agent anchoring in step 3 would
    # hit the real (unmocked) oracle URL and silently no-op.
    primitives = {"sovereign_agent": agent_address, "state_anchor": anvil_chain["anchor_address"]}

    def _fake_resolve(oracle_url: str, agent_id_: str) -> dict:
        return primitives

    monkeypatch.setattr("app.chain.resolve_agent_primitives", _fake_resolve)
    monkeypatch.setattr("app.anchor.resolve_agent_primitives", _fake_resolve)

    # 1. BAA inactive -> denied. `covered_entity_address` is set (a real
    #    healthcare-vertical commitment always carries it -- see
    #    schemas.py), so this exercises "contract reachable, pair just
    #    isn't active yet", not the separate CANNOT_VERIFY-missing-field
    #    path covered by test_baa_cannot_verify_when_covered_entity_address_missing.
    payload = sign_commitment(
        private_key, agent_id=agent_id, intent_type="EMR_WRITE", nonce=1, covered_entity_address=covered_entity
    )
    commitment = make_commitment_model(**payload)
    denied = await main_module.run_intercept(commitment, settings)
    assert denied.authorized is False
    assert "BAA_INACTIVE" in denied.reason

    # 2. Activate BAA on-chain for real, for this exact (coveredEntity,
    #    businessAssociate) pair -- the real SmartBAAFactory.isBAAActive
    #    signature (see app/baa.py) takes both. `agent_address` here is the
    #    exact address the stubbed resolver maps `agent_id` to (see above),
    #    matching what `check_baa_status` inside `run_intercept` will query.
    account = Account.from_key(anvil_chain["signer_private_key"])
    contract = w3.eth.contract(address=anvil_chain["baa_address"], abi=anvil_chain["baa_abi"])
    tx = contract.functions.setActive(covered_entity, agent_address, True).build_transaction(
        {"from": account.address, "nonce": w3.eth.get_transaction_count(account.address), "chainId": anvil_chain["chain_id"]}
    )
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    w3.eth.wait_for_transaction_receipt(tx_hash, timeout=15)

    # 3. Same agent + covered entity, fresh nonce -> now authorized, and the
    #    batch (size 1) should flush + anchor immediately.
    payload2 = sign_commitment(
        private_key, agent_id=agent_id, intent_type="EMR_WRITE", nonce=2, covered_entity_address=covered_entity
    )
    commitment2 = make_commitment_model(**payload2)
    approved = await main_module.run_intercept(commitment2, settings)

    assert approved.authorized is True
    assert approved.verification_token

    # Precise checks, not just "root is non-zero" -- the anchor contract is
    # shared (session-scoped anvil_chain) with other tests in this file, so
    # a weak non-zero check could pass even if THIS test's anchor call never
    # happened. Confirm rootCount advanced by exactly one and the anchored
    # root matches the exact single-leaf root we expect for commitment2.
    expected_root = merkle_root([leaf_hash(commitment2)])
    last_root, root_count_after = _read_anchor_state()
    assert root_count_after == root_count_before + 1
    assert last_root == expected_root
