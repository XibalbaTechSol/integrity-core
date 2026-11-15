"""
Real, end-to-end test of health.py's chain calls against the session anvil
chain (real CoveredEntityRegistry/SmartBAAFactory/SmartBAA/ComplianceGate/
EHRGate bytecode, deployed by the real contracts/script/Deploy.s.sol -- see
conftest.py). health.py was written but never exercised against real
deployed contracts (PRODUCTION_GAPS.md §3) -- this walks the full happy
path (register covered entity -> create BAA -> agent signs BAA -> patient
grants EHR access -> agent's AISRegistry checkpoint clears the threshold ->
access check passes) plus one denial case,
proving every calldata/signer-role choice in health.py actually works
against the real contracts, not just that it imports.

Registration v3 Phase 3: EHRGate reads the v3 `AgentRegistry` and AIS (basis points) from
`AISRegistry` checkpoints, so the business associate is a v3-bound agent (see v3_onchain.py),
not a held-factory agent with a ReputationRegistry score.
"""

from __future__ import annotations

import os

import pytest
from eth_account import Account
from eth_utils import keccak
from web3 import Web3

import v3_onchain
from integrity_sdk import chain, health, wallet

# EHRGate's minAisThreshold in Deploy.s.sol, in basis points.
EHR_THRESHOLD_BPS = 8000


@pytest.fixture
def health_scenario(deployed_chain, tmp_path, monkeypatch):
    """
    Registers one real agent (the business associate) and generates two
    plain EOA wallets (covered entity, patient) -- covered entities and
    patients are never agents in this vertical (see health.py's module
    docstring), so they get a bare `eth_account` keypair, not a full
    registration flow.
    """
    monkeypatch.setenv("INTEGRITY_WALLET_HOME", str(tmp_path / "wallets"))
    monkeypatch.setenv("INTEGRITY_WALLET_PASSWORD", "test-only-password")

    w3 = deployed_chain["w3"]
    chain_id = deployed_chain["chain_id"]
    funder = deployed_chain["funder"]
    addr = deployed_chain["addresses"]

    agent_wallet_id = f"health-agent-{os.urandom(4).hex()}"
    agent_account = wallet.generate_or_load_evm_wallet(agent_wallet_id)
    chain.fund_agent_wallet(w3, funder, agent_account.address, Web3.to_wei(1, "ether"), chain_id)

    did = f"did:integrity:{agent_wallet_id}"
    sovereign_agent = v3_onchain.deploy_canonical_agent(w3, chain_id, agent_account, addr["AgentRegistry"], did)
    v3_onchain.bind(w3, chain_id, funder, agent_account, addr["AgentRegistry"], sovereign_agent)
    # BAA collateral is pulled from the SovereignAgent contract (it signs via its own execute).
    chain.mint_testnet_itk(w3, funder, addr["IntegrityToken"], sovereign_agent, Web3.to_wei(10_000, "ether"), chain_id)

    covered_entity_account = Account.create()
    chain.fund_agent_wallet(w3, funder, covered_entity_account.address, Web3.to_wei(1, "ether"), chain_id)

    patient_account = Account.create()
    chain.fund_agent_wallet(w3, funder, patient_account.address, Web3.to_wei(1, "ether"), chain_id)

    return {
        "w3": w3,
        "chain_id": chain_id,
        "addr": addr,
        "agent_account": agent_account,
        "sovereign_agent": sovereign_agent,
        "covered_entity_account": covered_entity_account,
        "patient_account": patient_account,
    }


def test_full_health_flow_grants_and_verifies_ehr_access(deployed_chain, health_scenario):
    s = health_scenario
    w3, chain_id, addr = s["w3"], s["chain_id"], s["addr"]
    funder = deployed_chain["funder"]

    health.register_covered_entity(
        w3,
        funder,
        addr["CoveredEntityRegistry"],
        s["covered_entity_account"].address,
        health.ENTITY_TYPE_COVERED_ENTITY,
        "ipfs://covered-entity-metadata",
        chain_id,
    )

    required_collateral = Web3.to_wei(100, "ether")
    agreement_hash = keccak(text="test-baa-agreement")
    baa_address = health.create_baa(
        w3,
        s["covered_entity_account"],
        addr["SmartBAAFactory"],
        s["sovereign_agent"],
        agreement_hash,
        required_collateral,
        chain_id,
    )
    assert Web3.is_address(baa_address)

    # Access must be denied before the patient has granted anything -- proves
    # check_ehr_access isn't a rubber stamp before we go on to prove the
    # positive path too.
    denied_before_grant = health.check_ehr_access(
        w3, addr["EHRGate"], s["sovereign_agent"], s["patient_account"].address, keccak(text="record-1")
    )
    assert denied_before_grant is False

    health.sign_baa(
        w3, s["agent_account"], s["sovereign_agent"], baa_address, addr["IntegrityToken"], required_collateral, chain_id
    )

    v3_onchain.post_ais(w3, chain_id, deployed_chain["funder"], addr["AISRegistry"], s["sovereign_agent"], 9000)

    record_hash = keccak(text="record-1")
    health.grant_ehr_access(
        w3, s["patient_account"], addr["EHRGate"], record_hash, s["sovereign_agent"], s["covered_entity_account"].address, chain_id
    )

    granted = health.check_ehr_access(w3, addr["EHRGate"], s["sovereign_agent"], s["patient_account"].address, record_hash)
    assert granted is True

    tx_hash = health.verify_and_log_access(
        w3, s["agent_account"], s["sovereign_agent"], addr["EHRGate"], s["patient_account"].address, record_hash, chain_id
    )
    receipt = w3.eth.get_transaction_receipt(tx_hash)
    assert receipt["status"] == 1


def test_ehr_access_denied_when_ais_below_threshold(deployed_chain, health_scenario):
    """Consent + an active BAA aren't enough on their own -- the reputation
    gate is a real, independently-enforced third condition, not decorative."""
    s = health_scenario
    w3, chain_id, addr = s["w3"], s["chain_id"], s["addr"]
    funder = deployed_chain["funder"]

    health.register_covered_entity(
        w3, funder, addr["CoveredEntityRegistry"], s["covered_entity_account"].address,
        health.ENTITY_TYPE_COVERED_ENTITY, "ipfs://covered-entity-metadata", chain_id,
    )
    required_collateral = Web3.to_wei(100, "ether")
    baa_address = health.create_baa(
        w3, s["covered_entity_account"], addr["SmartBAAFactory"], s["sovereign_agent"],
        keccak(text="baa-2"), required_collateral, chain_id,
    )
    health.sign_baa(w3, s["agent_account"], s["sovereign_agent"], baa_address, addr["IntegrityToken"], required_collateral, chain_id)
    # Deliberately do NOT post a checkpoint above the 8000 bps threshold -- AIS stays at
    # AISRegistry's zero default.

    record_hash = keccak(text="record-2")
    health.grant_ehr_access(
        w3, s["patient_account"], addr["EHRGate"], record_hash, s["sovereign_agent"], s["covered_entity_account"].address, chain_id
    )

    granted = health.check_ehr_access(w3, addr["EHRGate"], s["sovereign_agent"], s["patient_account"].address, record_hash)
    assert granted is False
