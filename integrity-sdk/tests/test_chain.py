"""
Real, end-to-end test of the self-sovereign registration sequence against a
live (test-session) anvil chain running the actual Deploy.s.sol genesis —
no mocked web3 provider, no stubbed contract calls. This is the same
sequence integrity-sdk's registration.py performs against real Base Sepolia;
proving it here against real anvil-deployed bytecode is what makes that
later real-network run trustworthy.
"""

from __future__ import annotations

import os

import pytest
from eth_utils import keccak
from web3 import Web3

from integrity_sdk import chain, wallet

os.environ.setdefault("INTEGRITY_WALLET_PASSWORD", "test-only-password")

# Deploy.s.sol bootstraps this domain (Open join mode) at genesis — see
# contracts/script/Deploy.s.sol::_bootstrapDomains.
GENERAL_DOMAIN_ID = keccak(text="general.integrity")


@pytest.fixture
def agent_account(tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_WALLET_HOME", str(tmp_path / "wallets"))
    return wallet.generate_or_load_evm_wallet("test-agent")


def _register_agent(deployed_chain, agent_id: str, agent_account) -> chain.PrimitivesRegistered:
    """The real 6-transaction self-sovereign registration sequence, exactly
    as integrity-sdk's registration.py will perform it: fund -> mint ITK ->
    deploy SovereignAgent -> deploy StateAnchor -> grant ANCHOR_ROLE via
    execute -> registerPrimitives."""
    w3 = deployed_chain["w3"]
    chain_id = deployed_chain["chain_id"]
    funder = deployed_chain["funder"]
    addr = deployed_chain["addresses"]

    chain.fund_agent_wallet(w3, funder, agent_account.address, Web3.to_wei(1, "ether"), chain_id)

    did = f"did:integrity:{agent_id}"
    oracle_signer = funder.address  # Deploy.s.sol defaults ORACLE_SIGNER_ADDRESS to the deployer/funder.

    sovereign_agent = chain.deploy_sovereign_agent(w3, agent_account, did, oracle_signer, chain_id)
    state_anchor = chain.deploy_state_anchor(w3, agent_account, sovereign_agent, chain_id)
    chain.grant_anchor_role(w3, agent_account, sovereign_agent, state_anchor, oracle_signer, chain_id)
    chain.anchor_genesis_root(w3, agent_account, sovereign_agent, state_anchor, chain_id)

    chain.mint_testnet_itk(
        w3, funder, addr["IntegrityToken"], sovereign_agent, Web3.to_wei(10_000, "ether"), chain_id
    )
    chain.approve_factory_bond(
        w3, agent_account, sovereign_agent, addr["IntegrityToken"], addr["AgentPrimitivesFactory"], Web3.to_wei(100, "ether"), chain_id
    )

    return chain.register_primitives(
        w3,
        agent_account,
        addr["AgentPrimitivesFactory"],
        sovereign_agent,
        state_anchor,
        did,
        GENERAL_DOMAIN_ID,
        0,  # ComplianceGate.Vertical.None
        "ipfs://test-profile",
        chain_id,
    )


def test_full_registration_sequence(deployed_chain, agent_account):
    result = _register_agent(deployed_chain, "test-full-flow", agent_account)

    zero_address = "0x0000000000000000000000000000000000000000"
    assert result.controller == agent_account.address
    for primitive_address in (
        result.sovereign_agent,
        result.state_anchor,
        result.reputation_registry,
        result.slasher,
        result.verifier_registry,
        result.compliance_gate,
        result.agent_profile,
    ):
        assert Web3.to_checksum_address(primitive_address) != Web3.to_checksum_address(zero_address)

    # ITK balance survives the whole sequence minus the 100 ITK registration bond.
    w3 = deployed_chain["w3"]
    addr = deployed_chain["addresses"]
    itk_artifact = chain._load_artifact("IntegrityToken")
    itk = w3.eth.contract(address=addr["IntegrityToken"], abi=itk_artifact["abi"])
    assert itk.functions.balanceOf(result.sovereign_agent).call() == Web3.to_wei(9_900, "ether")


def test_controller_pins_zk_identity_via_sovereign_agent(deployed_chain, agent_account):
    result = _register_agent(deployed_chain, "test-zk-identity", agent_account)
    commitment = bytes.fromhex("12" * 32)

    chain.set_zk_identity_commitment(
        deployed_chain["w3"],
        agent_account,
        result.sovereign_agent,
        result.reputation_registry,
        commitment,
        deployed_chain["chain_id"],
    )

    registry = chain._contract(
        deployed_chain["w3"], "ReputationRegistry", address=result.reputation_registry
    )
    assert registry.functions.zkIdentityCommitment().call() == commitment


@pytest.mark.parametrize("commitment", [b"", bytes(32), bytes(31)])
def test_zk_identity_commitment_rejects_invalid_bytes(deployed_chain, agent_account, commitment):
    with pytest.raises(ValueError, match="non-zero 32-byte"):
        chain.set_zk_identity_commitment(
            deployed_chain["w3"],
            agent_account,
            Web3.to_checksum_address("0x" + "11" * 20),
            Web3.to_checksum_address("0x" + "22" * 20),
            commitment,
            deployed_chain["chain_id"],
        )


def test_two_agents_get_independent_primitives(deployed_chain, tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_WALLET_HOME", str(tmp_path / "wallets"))
    agent_one = wallet.generate_or_load_evm_wallet("agent-one")
    agent_two = wallet.generate_or_load_evm_wallet("agent-two")

    r1 = _register_agent(deployed_chain, "agent-one", agent_one)
    r2 = _register_agent(deployed_chain, "agent-two", agent_two)

    assert r1.sovereign_agent != r2.sovereign_agent
    assert r1.reputation_registry != r2.reputation_registry
    assert r1.slasher != r2.slasher
    assert r1.compliance_gate != r2.compliance_gate
