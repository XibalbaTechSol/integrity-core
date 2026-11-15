"""
The genesis deploy must ship the v2 trust layer WIRED, not inert.

Runs against the session anvil chain that `conftest.py` stands up with the real
`contracts/script/Deploy.s.sol`. Before the deploy script wired the trust layer,
the agent registry's `trustConfig()` was zero, so every registered agent's
execute gate resolved to nothing: no freeze, no policy, no stake lock
(final-fix re-review, Important-2).

The last test is the one that matters: it drives the whole chain of custody —
scorer posts a failing AIS checkpoint -> vault latches the freeze -> the SDK's
own `execute_via_agent` reverts `Frozen` for an agent bound in the v3 `AgentRegistry`.

Registration v3 Phase 3 (PR 3.2): the gate reads `AgentRegistry`, not the held
`XibalbaAgentRegistry`. Deploy.s.sol still deploys the held graph (unwired) until PR 3.4
moves SDK onboarding over, so this test binds its agent through `AgentRegistry` directly.
"""

from __future__ import annotations

import json

import pytest
from eth_utils import keccak
from eth_account import Account
from web3 import Web3
from web3.exceptions import ContractCustomError

import v3_onchain
from integrity_sdk import chain

ZERO = "0x0000000000000000000000000000000000000000"

TRUST_CONTRACTS = (
    "ITK",
    "TrustConfig",
    "StakeVault",
    "PolicyRegistry",
    "OpenPolicyModule",
    "AISRegistry",
    "RewardRegistry",
    "DiscountRewardModule",
    "ActionAnchor",
)


def _fn(name, inputs=(), outputs=(), mutability="view"):
    return {
        "type": "function",
        "name": name,
        "stateMutability": mutability,
        "inputs": [{"name": f"a{i}", "type": t} for i, t in enumerate(inputs)],
        "outputs": [{"name": "", "type": t} for t in outputs],
    }


_ABI = [
    _fn("trustConfig", outputs=["address"]),
    _fn("stakeVault", outputs=["address"]),
    _fn("policyRegistry", outputs=["address"]),
    _fn("rewardDiscountModule", outputs=["address"]),
    _fn("rewardRegistry", outputs=["address"]),
    _fn("agentRegistry", outputs=["address"]),
    _fn("itk", outputs=["address"]),
    _fn("freezeThreshold", outputs=["uint32"]),
    _fn("unbondingDelay", outputs=["uint256"]),
    _fn("moduleOf", ["bytes32"], ["address"]),
    _fn("hasRole", ["bytes32", "address"], ["bool"]),
    _fn("isRegisteredAgent", ["address"], ["bool"]),
    {
        "type": "function",
        "name": "stakeOf",
        "stateMutability": "view",
        "inputs": [{"name": "agent", "type": "address"}],
        "outputs": [
            {
                "name": "",
                "type": "tuple",
                "components": [
                    {"name": "amount", "type": "uint256"},
                    {"name": "locked", "type": "uint256"},
                    {"name": "frozen", "type": "bool"},
                ],
            }
        ],
    },
    _fn("postCheckpoint", ["address", "uint32", "uint64", "bytes32", "uint256"], mutability="nonpayable"),
]


def _role(name: str) -> bytes:
    return keccak(text=name)


@pytest.fixture
def trust(deployed_chain):
    addr = deployed_chain["addresses"]
    missing = [name for name in TRUST_CONTRACTS if name not in addr]
    assert not missing, f"Deploy.s.sol did not deploy: {missing}"
    w3 = deployed_chain["w3"]
    return {name: w3.eth.contract(address=addr[name], abi=_ABI) for name in (*TRUST_CONTRACTS, "AgentRegistry")}


def test_registry_points_at_the_deployed_trust_config(trust):
    assert trust["AgentRegistry"].functions.trustConfig().call() == trust["TrustConfig"].address


def test_trust_config_pins_all_three_gate_modules(trust):
    cfg = trust["TrustConfig"].functions
    assert cfg.stakeVault().call() == trust["StakeVault"].address
    assert cfg.policyRegistry().call() == trust["PolicyRegistry"].address
    assert cfg.rewardDiscountModule().call() == trust["DiscountRewardModule"].address


def test_vault_stakes_the_v2_token_and_can_actually_freeze(trust):
    vault = trust["StakeVault"].functions
    assert vault.itk().call() == trust["ITK"].address
    # A zero threshold can never freeze anyone: `score < 0` is unsatisfiable.
    assert vault.freezeThreshold().call() > 0
    assert vault.unbondingDelay().call() == 7 * 24 * 3600


def test_ais_registry_holds_the_roles_its_checkpoint_needs(trust, deployed_chain):
    ais = trust["AISRegistry"]
    assert ais.functions.stakeVault().call() == trust["StakeVault"].address
    assert ais.functions.rewardRegistry().call() == trust["RewardRegistry"].address
    assert ais.functions.agentRegistry().call() == trust["AgentRegistry"].address
    assert trust["StakeVault"].functions.hasRole(_role("AIS_REGISTRY_ROLE"), ais.address).call()
    assert trust["RewardRegistry"].functions.hasRole(_role("NOTIFIER_ROLE"), ais.address).call()
    # Local chain: the oracle signer defaults to the deployer/funder.
    assert ais.functions.hasRole(_role("SCORER_ROLE"), deployed_chain["funder"].address).call()


def test_bootstrap_domains_have_a_policy_and_a_reward_module(trust):
    """A registered agent in a domain with no policy module fail-closes (bricks)."""
    for name in ("general.integrity", "healthcare.integrity"):
        domain_id = keccak(text=name)
        assert trust["PolicyRegistry"].functions.moduleOf(domain_id).call() == trust["OpenPolicyModule"].address, name
        assert trust["RewardRegistry"].functions.moduleOf(domain_id).call() == trust["DiscountRewardModule"].address, name


def _bind_v3_agent(w3, chain_id, funder, registry_address, domain_name):
    controller = Account.create()
    v3_onchain.fund(w3, funder, controller.address, chain_id)
    agent = v3_onchain.deploy_canonical_agent(w3, chain_id, controller, registry_address, "did:integrity:freeze-e2e")
    v3_onchain.bind(w3, chain_id, funder, controller, registry_address, agent, domain_name)
    return agent, controller


def test_failing_checkpoint_freezes_a_v3_bound_agent(trust, deployed_chain):
    w3 = deployed_chain["w3"]
    chain_id = deployed_chain["chain_id"]
    funder = deployed_chain["funder"]

    registry = trust["AgentRegistry"]
    agent, controller = _bind_v3_agent(w3, chain_id, funder, registry.address, "general.integrity")
    assert registry.functions.isRegisteredAgent(agent).call()

    probe = registry.encode_abi("isRegisteredAgent", args=[agent])

    # Live gate, healthy agent: the open policy module lets the call through.
    chain.execute_via_agent(w3, controller, agent, registry.address, probe, chain_id)
    assert trust["StakeVault"].functions.stakeOf(agent).call()[2] is False

    # The scorer posts a checkpoint below the freeze threshold.
    v3_onchain.post_ais(w3, chain_id, funder, trust["AISRegistry"].address, agent, 0)
    assert trust["StakeVault"].functions.stakeOf(agent).call()[2] is True

    frozen_selector = "0x" + keccak(text="Frozen()")[:4].hex()
    with pytest.raises(ContractCustomError) as excinfo:
        chain.execute_via_agent(w3, controller, agent, registry.address, probe, chain_id)
    assert frozen_selector in str(excinfo.value)


def test_checkpoint_for_an_unbound_agent_is_rejected(trust, deployed_chain):
    """AISRegistry fails closed once an AgentRegistry is wired: no scores for unbound addresses."""
    w3 = deployed_chain["w3"]
    funder = deployed_chain["funder"]
    stranger = Account.create().address
    fn = trust["AISRegistry"].functions.postCheckpoint(stranger, 9000, 1, b"\x22" * 32, 0)
    with pytest.raises(ContractCustomError) as excinfo:
        fn.call({"from": funder.address})
    assert "0x" + keccak(text="NotRegisteredAgent(address)")[:4].hex() in str(excinfo.value)
