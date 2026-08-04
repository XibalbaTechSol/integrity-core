"""
Real, end-to-end test of health.py's chain calls against the session anvil
chain (real CoveredEntityRegistry/SmartBAAFactory/SmartBAA/ComplianceGate/
EHRGate bytecode, deployed by the real contracts/script/Deploy.s.sol -- see
conftest.py). health.py was written but never exercised against real
deployed contracts (PRODUCTION_GAPS.md §3) -- this walks the full happy
path (register covered entity -> create BAA -> agent signs BAA -> agent
self-declares compliance -> patient grants EHR access -> agent's on-chain
AIS clears the threshold -> access check passes) plus one denial case,
proving every calldata/signer-role choice in health.py actually works
against the real contracts, not just that it imports.
"""

from __future__ import annotations

import os

import pytest
from eth_account import Account
from eth_utils import keccak
from web3 import Web3

from integrity_sdk import chain, health, wallet

GENERAL_DOMAIN_ID = keccak(text="general.integrity")

_REPUTATION_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "agent", "type": "address"},
            {"internalType": "uint256", "name": "baseScore", "type": "uint256"},
        ],
        "name": "updateScore",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]


def _push_score(deployed_chain, reputation_registry_address: str, agent_address: str, score: int) -> None:
    """Deploy.s.sol grants ORACLE_ROLE on every clone to the funder -- same
    shortcut test_markets.py's `_set_score` uses to move a real on-chain
    number without running a full telemetry pipeline."""
    w3 = deployed_chain["w3"]
    funder = deployed_chain["funder"]
    rep = w3.eth.contract(
        address=Web3.to_checksum_address(reputation_registry_address), abi=_REPUTATION_ABI
    )
    tx = rep.functions.updateScore(Web3.to_checksum_address(agent_address), score).build_transaction(
        {"from": funder.address, "nonce": w3.eth.get_transaction_count(funder.address), "chainId": deployed_chain["chain_id"]}
    )
    signed = funder.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)


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
    oracle_signer = funder.address
    sovereign_agent = chain.deploy_sovereign_agent(w3, agent_account, did, oracle_signer, chain_id)
    state_anchor = chain.deploy_state_anchor(w3, agent_account, sovereign_agent, chain_id)
    chain.mint_testnet_itk(w3, funder, addr["IntegrityToken"], sovereign_agent, Web3.to_wei(10_000, "ether"), chain_id)
    chain.grant_anchor_role(w3, agent_account, sovereign_agent, state_anchor, oracle_signer, chain_id)
    primitives = chain.register_primitives(
        w3, agent_account, addr["AgentPrimitivesFactory"], sovereign_agent, state_anchor, did, GENERAL_DOMAIN_ID, 0, "", chain_id
    )

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
        "primitives": primitives,
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

    health.set_self_declared_compliance(
        w3,
        s["agent_account"],
        s["sovereign_agent"],
        s["primitives"].compliance_gate,
        True,
        True,
        False,
        "us-east",
        chain_id,
    )

    _push_score(deployed_chain, s["primitives"].reputation_registry, s["sovereign_agent"], 900)

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
    # Deliberately do NOT push a score above the 800 threshold -- it stays at
    # the registry's zero default.

    record_hash = keccak(text="record-2")
    health.grant_ehr_access(
        w3, s["patient_account"], addr["EHRGate"], record_hash, s["sovereign_agent"], s["covered_entity_account"].address, chain_id
    )

    granted = health.check_ehr_access(w3, addr["EHRGate"], s["sovereign_agent"], s["patient_account"].address, record_hash)
    assert granted is False
