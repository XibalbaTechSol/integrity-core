"""
Real, end-to-end tests of markets.py's low-level chain calls against the
session anvil chain (real MarketFactory/IntegrityMarket/A2ACapitalPool
bytecode, deployed by the real contracts/script/DeployMarkets.s.sol -- see
conftest.py). The high-level BCC-integrated flows (enter_prediction,
enter_binary_option, allocate_capital) are unit-tested separately with
requests.post patched, since exercising them for real would require a live
bcc_middleware + OPA server -- that boundary already has its own real
integration coverage in bcc_middleware/tests/.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from eth_utils import keccak
from web3 import Web3

from integrity_sdk import chain, markets, wallet

GENERAL_DOMAIN_ID = keccak(text="general.integrity")


def _register_agent(deployed_chain, agent_id: str, agent_account) -> chain.PrimitivesRegistered:
    """
    Mirrors registration.py's real (now-reordered) sequence -- SovereignAgent
    deploy BEFORE the ITK mint, minted to the CONTRACT address, not the
    wallet. This is what makes the market tests below realistic: an
    IntegrityMarket/A2ACapitalPool call from an agent is execute-routed
    through its SovereignAgent contract (see markets.py's
    `_execute_via_agent`), which can only pull ITK it actually holds.
    """
    w3 = deployed_chain["w3"]
    chain_id = deployed_chain["chain_id"]
    funder = deployed_chain["funder"]
    addr = deployed_chain["addresses"]

    chain.fund_agent_wallet(w3, funder, agent_account.address, Web3.to_wei(1, "ether"), chain_id)

    did = f"did:integrity:{agent_id}"
    oracle_signer = funder.address

    sovereign_agent = chain.deploy_sovereign_agent(w3, agent_account, did, oracle_signer, chain_id)
    state_anchor = chain.deploy_state_anchor(w3, agent_account, sovereign_agent, chain_id)
    chain.mint_testnet_itk(w3, funder, addr["IntegrityToken"], sovereign_agent, Web3.to_wei(10_000, "ether"), chain_id)
    chain.set_execution_policy(w3, agent_account, sovereign_agent, addr["ConstraintExecutionPolicy"], chain_id)
    chain.grant_anchor_role(w3, agent_account, sovereign_agent, state_anchor, oracle_signer, chain_id)
    chain.anchor_genesis_root(w3, agent_account, sovereign_agent, state_anchor, chain_id)
    chain.set_anchor_policy(w3, agent_account, sovereign_agent, state_anchor, addr["AllowlistAnchorPolicy"], chain_id)
    chain.approve_factory_bond(
        w3,
        agent_account,
        sovereign_agent,
        addr["IntegrityToken"],
        addr["AgentPrimitivesFactory"],
        Web3.to_wei(100, "ether"),
        chain_id,
    )

    return chain.register_primitives(
        w3, agent_account, addr["AgentPrimitivesFactory"], sovereign_agent, state_anchor, did, GENERAL_DOMAIN_ID, 0, "", chain_id
    )


def _set_score(deployed_chain, reputation_registry_address: str, agent_address: str, score: int) -> None:
    """Deploy.s.sol grants ORACLE_ROLE on every clone's implementation params
    to the funder/oracleSigner -- push a score directly, same shortcut
    test_chain.py-adjacent tests use rather than running a real telemetry
    pipeline just to move a number for a contract-level test."""
    w3 = deployed_chain["w3"]
    funder = deployed_chain["funder"]
    from web3 import Web3 as _W3

    rep = w3.eth.contract(address=_W3.to_checksum_address(reputation_registry_address), abi=_REPUTATION_ABI)
    tx = rep.functions.updateScore(_W3.to_checksum_address(agent_address), score).build_transaction(
        {"from": funder.address, "nonce": w3.eth.get_transaction_count(funder.address), "chainId": deployed_chain["chain_id"]}
    )
    signed = funder.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)


_REPUTATION_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "agent", "type": "address"}, {"internalType": "uint256", "name": "baseScore", "type": "uint256"}],
        "name": "updateScore",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]


@pytest.fixture
def two_agents(deployed_chain, tmp_path, monkeypatch, request):
    monkeypatch.setenv("INTEGRITY_WALLET_HOME", str(tmp_path / "wallets"))
    monkeypatch.setenv("INTEGRITY_WALLET_PASSWORD", "test-only-password")
    # `deployed_chain` is session-scoped (one real anvil for the whole test
    # session, see conftest.py) but this fixture is function-scoped -- a
    # fixed agent_id string would collide with XibalbaAgentRegistry's real
    # `AlreadyRegistered()` revert the second time any test using this
    # fixture runs, since the DID it derives from agent_id would already be
    # registered on that same long-lived chain. Suffix with the test's own
    # node name (unique per test function) instead of a fixed literal.
    suffix = request.node.name
    alice_wallet = wallet.generate_or_load_evm_wallet(f"market-alice-{suffix}")
    bob_wallet = wallet.generate_or_load_evm_wallet(f"market-bob-{suffix}")
    alice = _register_agent(deployed_chain, f"market-alice-{suffix}", alice_wallet)
    bob = _register_agent(deployed_chain, f"market-bob-{suffix}", bob_wallet)
    _set_score(deployed_chain, alice.reputation_registry, alice.sovereign_agent, 900)
    _set_score(deployed_chain, bob.reputation_registry, bob.sovereign_agent, 900)
    return {"alice_wallet": alice_wallet, "alice": alice, "bob_wallet": bob_wallet, "bob": bob}


def test_deploy_market_agent_owns_it(deployed_chain, two_agents):
    w3 = deployed_chain["w3"]
    addr = deployed_chain["addresses"]
    chain_id = deployed_chain["chain_id"]
    resolver = deployed_chain["funder"].address

    # markets.deploy_market execute-routes through Alice's own SovereignAgent
    # contract (see markets.py's `_execute_via_agent`) -- Alice's wallet
    # signs, but MarketFactory sees msg.sender == her SovereignAgent
    # contract address, which is what `isRegisteredAgent` actually resolves.
    market_address = markets.deploy_market(
        w3, two_agents["alice_wallet"], two_agents["alice"].sovereign_agent, addr["MarketFactory"],
        "Will it rain tomorrow?", 2, 0, w3.eth.get_block("latest")["timestamp"] + 3600, resolver, chain_id,
    )
    assert market_address.startswith("0x")

    market = w3.eth.contract(address=market_address, abi=chain._load_artifact("IntegrityMarket")["abi"])
    assert market.functions.creator().call() == two_agents["alice"].sovereign_agent
    assert market.functions.question().call() == "Will it rain tomorrow?"


def test_deploy_market_rejects_unregistered_wallet(deployed_chain, two_agents):
    w3 = deployed_chain["w3"]
    addr = deployed_chain["addresses"]
    chain_id = deployed_chain["chain_id"]
    from eth_account import Account

    # A self-deployed SovereignAgent that was NEVER passed through
    # AgentPrimitivesFactory.registerPrimitives -- real contract (so
    # execute() itself works, proving the rejection comes from
    # MarketFactory's own isRegisteredAgent check, not a routing failure),
    # just not indexed in XibalbaAgentRegistry.
    stranger = Account.create()
    chain.fund_agent_wallet(w3, deployed_chain["funder"], stranger.address, Web3.to_wei(1, "ether"), chain_id)
    unregistered_sovereign_agent = chain.deploy_sovereign_agent(
        w3, stranger, "did:integrity:never-registered", deployed_chain["funder"].address, chain_id
    )

    with pytest.raises(Exception):
        markets.deploy_market(
            w3, stranger, unregistered_sovereign_agent, addr["MarketFactory"], "unregistered question", 2, 0,
            w3.eth.get_block("latest")["timestamp"] + 3600, deployed_chain["funder"].address, chain_id,
        )


def test_full_market_flow_enter_resolve_claim(deployed_chain, two_agents):
    w3 = deployed_chain["w3"]
    addr = deployed_chain["addresses"]
    chain_id = deployed_chain["chain_id"]
    funder = deployed_chain["funder"]

    market_address = markets.deploy_market(
        w3, two_agents["alice_wallet"], two_agents["alice"].sovereign_agent, addr["MarketFactory"],
        "Binary test market", 2, 0, w3.eth.get_block("latest")["timestamp"] + 3600, funder.address, chain_id,
    )

    markets.enter_position(
        w3, two_agents["alice_wallet"], two_agents["alice"].sovereign_agent, market_address, 0,
        Web3.to_wei(100, "ether"), b"\x11" * 32, chain_id,
    )
    markets.enter_position(
        w3, two_agents["bob_wallet"], two_agents["bob"].sovereign_agent, market_address, 1,
        Web3.to_wei(100, "ether"), b"\x22" * 32, chain_id,
    )

    markets.resolve_market(w3, funder, market_address, 0, chain_id)

    # Balances checked on the SovereignAgent CONTRACT, not the wallet --
    # enter_position pulled ITK from (and claimPayout pays out to) whichever
    # address actually called the market, which is the contract (see
    # markets.py's `_execute_via_agent`).
    itk = w3.eth.contract(address=addr["IntegrityToken"], abi=chain._load_artifact("IntegrityToken")["abi"])
    balance_before = itk.functions.balanceOf(two_agents["alice"].sovereign_agent).call()
    markets.claim_payout(w3, two_agents["alice_wallet"], two_agents["alice"].sovereign_agent, market_address, chain_id)
    balance_after = itk.functions.balanceOf(two_agents["alice"].sovereign_agent).call()
    assert balance_after - balance_before == Web3.to_wei(200, "ether")

    with pytest.raises(Exception):
        markets.claim_payout(w3, two_agents["bob_wallet"], two_agents["bob"].sovereign_agent, market_address, chain_id)


def test_allocate_release_and_clawback(deployed_chain, two_agents):
    w3 = deployed_chain["w3"]
    addr = deployed_chain["addresses"]
    chain_id = deployed_chain["chain_id"]
    funder = deployed_chain["funder"]

    # Funder acts as a non-agent (human investor) allocator here -- exactly
    # the case allocate_capital_onchain exists for (no DID to sign a BCC
    # commitment with). Deploy.s.sol mints ZERO initial ITK supply (see its
    # own comment on why), so the funder -- despite holding MINTER_ROLE --
    # has no ITK of its own to allocate until it mints itself some, same as
    # any other "human investor" wallet in a real deployment would need to
    # acquire ITK before it could allocate.
    chain.mint_testnet_itk(w3, funder, addr["IntegrityToken"], funder.address, Web3.to_wei(1_000, "ether"), chain_id)

    allocation_id = markets.allocate_capital_onchain(
        w3, funder, addr["A2ACapitalPool"], addr["IntegrityToken"], two_agents["alice"].sovereign_agent,
        Web3.to_wei(500, "ether"), 700, chain_id,
    )

    itk = w3.eth.contract(address=addr["IntegrityToken"], abi=chain._load_artifact("IntegrityToken")["abi"])
    balance_before = itk.functions.balanceOf(two_agents["alice"].sovereign_agent).call()
    markets.release_allocation(w3, funder, addr["A2ACapitalPool"], allocation_id, chain_id)
    balance_after = itk.functions.balanceOf(two_agents["alice"].sovereign_agent).call()
    assert balance_after - balance_before == Web3.to_wei(500, "ether")


def test_clawback_returns_escrowed_funds(deployed_chain, two_agents):
    w3 = deployed_chain["w3"]
    addr = deployed_chain["addresses"]
    chain_id = deployed_chain["chain_id"]
    funder = deployed_chain["funder"]

    chain.mint_testnet_itk(w3, funder, addr["IntegrityToken"], funder.address, Web3.to_wei(1_000, "ether"), chain_id)

    allocation_id = markets.allocate_capital_onchain(
        w3, funder, addr["A2ACapitalPool"], addr["IntegrityToken"], two_agents["bob"].sovereign_agent,
        Web3.to_wei(300, "ether"), 700, chain_id,
    )

    itk = w3.eth.contract(address=addr["IntegrityToken"], abi=chain._load_artifact("IntegrityToken")["abi"])
    balance_before = itk.functions.balanceOf(funder.address).call()
    markets.clawback_allocation(w3, funder, addr["A2ACapitalPool"], allocation_id, chain_id)
    balance_after = itk.functions.balanceOf(funder.address).call()
    assert balance_after - balance_before == Web3.to_wei(300, "ether")


# --- high-level BCC-integrated flows (unit-tested, requests.post patched) ---------


class _FakeResponse:
    def __init__(self, payload: dict, status: int = 200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_enter_prediction_raises_and_never_submits_onchain_when_denied(deployed_chain, two_agents, tmp_path, monkeypatch):
    from integrity_sdk import did

    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "dids"))
    monkeypatch.setenv("RPC_URL", deployed_chain["rpc_url"])
    agent_did, keypair, _doc = did.load_or_create_did("prediction-denied-agent")

    with patch("integrity_sdk.markets.requests.post", return_value=_FakeResponse({"authorized": False, "reason": "OPA_REJECTION: test denial"})):
        with patch("integrity_sdk.markets.enter_position") as mock_enter:
            with pytest.raises(markets.MarketInterceptDenied, match="OPA_REJECTION"):
                markets.enter_prediction(
                    agent_id=agent_did, keypair=keypair, evm_account=two_agents["alice_wallet"],
                    sovereign_agent_address=two_agents["alice"].sovereign_agent,
                    market_address="0x0000000000000000000000000000000000000001", outcome_index=0,
                    amount_wei=Web3.to_wei(10, "ether"), nonce=1,
                )
            mock_enter.assert_not_called()


def test_enter_prediction_submits_onchain_with_commitment_hash_when_authorized(deployed_chain, two_agents, tmp_path, monkeypatch):
    from integrity_sdk import did

    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "dids"))
    monkeypatch.setenv("RPC_URL", deployed_chain["rpc_url"])
    agent_did, keypair, _doc = did.load_or_create_did("prediction-authorized-agent")

    with patch("integrity_sdk.markets.requests.post", return_value=_FakeResponse({"authorized": True, "verification_token": "tok123"})):
        with patch("integrity_sdk.markets.enter_position", return_value="0xdeadbeef") as mock_enter:
            result = markets.enter_prediction(
                agent_id=agent_did, keypair=keypair, evm_account=two_agents["alice_wallet"],
                sovereign_agent_address=two_agents["alice"].sovereign_agent,
                market_address="0x0000000000000000000000000000000000000001", outcome_index=0,
                amount_wei=Web3.to_wei(10, "ether"), nonce=1,
            )

    assert result.verification_token == "tok123"
    assert result.tx_hash == "0xdeadbeef"
    mock_enter.assert_called_once()
    call_args = mock_enter.call_args[0]
    # (w3, evm_account, sovereign_agent_address, market_address, outcome_index, amount_wei, commitment_hash, chain_id)
    assert call_args[2] == two_agents["alice"].sovereign_agent
    assert call_args[4] == 0
    assert call_args[5] == Web3.to_wei(10, "ether")
    assert isinstance(call_args[6], bytes) and len(call_args[6]) == 32
