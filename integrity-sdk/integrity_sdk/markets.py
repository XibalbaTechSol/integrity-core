"""
Agent-side client for the market/application layer: `MarketFactory` +
`IntegrityMarket` (prediction markets and binary options — the same on-chain
primitive, see contracts/src/markets/IntegrityMarket.sol's NatSpec) and
`A2ACapitalPool` (agent-to-agent capital allocation).

This is the direct extension of chain.py's registration flow to the
application layer: the same "agent's own wallet signs the real transaction"
posture, now applied to deploying/using a market instead of deploying an
identity primitive. Two layers of function live here:

  - Low-level chain calls (`deploy_market`, `enter_position`, `resolve_market`,
    `claim_payout`, `allocate_capital_onchain`, `release_allocation`,
    `clawback_allocation`) — thin web3.py wrappers, one real transaction each,
    mirroring chain.py's style exactly.
  - High-level, BCC-integrated flows (`enter_prediction`, `enter_binary_option`,
    `allocate_capital`) — build a real, signed BCC commitment (bcc.py), route
    it through bcc_middleware's `POST /v1/bcc/intercept` pre-execution gate
    (§4.2 of the interface contract), and ONLY THEN submit the on-chain call,
    carrying the commitment's hash so the on-chain position is provably bound
    to the off-chain intent the agent committed to first. This is the actual
    point of BCC for a trading/financial vertical: the agent cannot silently
    change its position after seeing new information post-commitment, because
    the intent hash is fixed and signed before the on-chain action lands.

`allocate_capital` is deliberately agent-attributable (built around a DID +
keypair, same as the market functions) — the protocol's "delegate money to a
trustworthy agent" story is agent-to-agent. A human/non-agent allocator has
no DID to sign a BCC commitment with, and should call `allocate_capital_onchain`
directly instead (no commitment, no middleware round-trip).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import requests
from eth_account.signers.local import LocalAccount
from web3 import Web3

from . import chain
from .bcc import build_bcc_commitment
from .did import Keypair

_DEFAULT_BCC_MIDDLEWARE_URL = "http://localhost:8000"


class MarketInterceptDenied(RuntimeError):
    """Raised when bcc_middleware denies the pre-execution commitment for a
    market/allocation action. The action is NEVER submitted on-chain in this
    case -- carries the middleware's own denial reason so the caller knows
    exactly why (expired commitment, OPA rejection, replayed nonce, etc)."""


# --- low-level chain calls --------------------------------------------------------


def _execute_via_agent(
    w3: Web3, controller: LocalAccount, sovereign_agent_address: str, target: str, calldata: bytes, chain_id: int
) -> dict:
    """
    Routes a call through `SovereignAgent(sovereign_agent_address).execute(target, 0,
    calldata)`, signed by `controller` (the agent's own wallet). Every
    application-layer contract that gates on agent identity
    (`agentRegistry.isRegisteredAgent(msg.sender)` /
    `agentRegistry.resolveAgent(msg.sender)`) resolves `msg.sender` against
    the SovereignAgent CONTRACT address, never the raw controller wallet --
    see XibalbaAgentRegistry.sol (`didHashOf` is keyed on
    `primitives.sovereignAgent`) and EHRGate.sol's identical convention. A
    direct call from the wallet to `MarketFactory`/`IntegrityMarket` would
    revert with `AgentNotRegistered`/`AgentNotRegistered` even for a fully
    registered agent, for exactly this reason -- this helper is what makes
    every market/pool interaction below actually work end-to-end, mirroring
    chain.py's `grant_anchor_role` (the one place this pattern was already
    proven before markets.py existed).
    """
    sovereign_agent = chain._contract(w3, "SovereignAgent", address=sovereign_agent_address)
    tx = sovereign_agent.functions.execute(Web3.to_checksum_address(target), 0, calldata).build_transaction(
        {
            "from": controller.address,
            "nonce": w3.eth.get_transaction_count(controller.address),
            "chainId": chain_id,
        }
    )
    signed = controller.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return chain._wait(w3, tx_hash, action=f"execute_via_agent({target})")


def deploy_market(
    w3: Web3,
    controller: LocalAccount,
    sovereign_agent_address: str,
    market_factory_address: str,
    question: str,
    outcome_count: int,
    min_ais_to_enter: int,
    resolve_deadline: int,
    resolver: str,
    chain_id: int,
) -> str:
    """
    Calls `MarketFactory.deployMarket`, routed through the calling agent's
    own `SovereignAgent.execute` (see `_execute_via_agent`) so the deployed
    market's `creator` -- and the caller `MarketFactory.isRegisteredAgent`
    checks -- is the agent's real, registered SovereignAgent contract
    address, not its raw controller wallet. `controller` signs; the market
    ends up owned by `sovereign_agent_address`. Returns the deployed market
    clone's checksummed address, parsed from the real `MarketDeployed`
    event rather than predicted client-side (same rationale as
    chain.register_primitives) -- since the call is now an internal call
    from SovereignAgent, the event is on a log emitted mid-transaction, but
    `process_receipt` finds it identically either way.
    """
    factory = chain._contract(w3, "MarketFactory", address=market_factory_address)
    calldata = factory.functions.deployMarket(
        question, outcome_count, min_ais_to_enter, resolve_deadline, Web3.to_checksum_address(resolver)
    ).build_transaction({"gas": 0})["data"]

    receipt = _execute_via_agent(w3, controller, sovereign_agent_address, market_factory_address, calldata, chain_id)

    factory_logs = [log for log in receipt["logs"] if log["address"] == factory.address]
    events = factory.events.MarketDeployed().process_receipt({**receipt, "logs": factory_logs})
    if not events:
        raise RuntimeError("deploy_market transaction succeeded but emitted no MarketDeployed event")
    return events[0]["args"]["market"]


def enter_position(
    w3: Web3,
    controller: LocalAccount,
    sovereign_agent_address: str,
    market_address: str,
    outcome_index: int,
    amount_wei: int,
    bcc_commitment_hash: bytes,
    chain_id: int,
) -> str:
    """
    Two execute-routed transactions, both signed by `controller` but
    submitted as the agent's SovereignAgent contract (see
    `_execute_via_agent`): first `IntegrityToken.approve` (the market must
    pull ITK FROM the SAME address that calls `enterPosition` -- i.e. the
    contract, which is where registration.py now mints testnet ITK
    collateral, see registration.py's step 7), then
    `IntegrityMarket.enterPosition` itself. Reverts on-chain (not caught
    here) if the agent's live AIS is below the market's `minAisToEnter`, if
    the caller isn't a registered agent, or if the contract's ITK balance is
    insufficient -- see IntegrityMarket.sol.
    """
    market = chain._contract(w3, "IntegrityMarket", address=market_address)
    itk_address = market.functions.itk().call()
    itk = chain._contract(w3, "IntegrityToken", address=itk_address)

    approve_calldata = itk.functions.approve(Web3.to_checksum_address(market_address), amount_wei).build_transaction(
        {"gas": 0}
    )["data"]
    _execute_via_agent(w3, controller, sovereign_agent_address, itk_address, approve_calldata, chain_id)

    enter_calldata = market.functions.enterPosition(outcome_index, amount_wei, bcc_commitment_hash).build_transaction(
        {"gas": 0}
    )["data"]
    receipt = _execute_via_agent(w3, controller, sovereign_agent_address, market_address, enter_calldata, chain_id)
    return receipt["transactionHash"].hex()


def resolve_market(w3: Web3, resolver: LocalAccount, market_address: str, winning_outcome: int, chain_id: int) -> str:
    """Calls `IntegrityMarket.resolve` -- only the address holding
    RESOLVER_ROLE on this market (set at deploy time) can call this
    successfully. See IntegrityMarket.sol's NatSpec on the resolver trust
    boundary this represents for the investor/developer MVP."""
    market = chain._contract(w3, "IntegrityMarket", address=market_address)
    tx = market.functions.resolve(winning_outcome).build_transaction(
        {
            "from": resolver.address,
            "nonce": w3.eth.get_transaction_count(resolver.address),
            "chainId": chain_id,
        }
    )
    signed = resolver.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    chain._wait(w3, tx_hash, action="resolve_market")
    return tx_hash.hex()


from .telemetry.core import get_tracer
from .telemetry.conventions import EconomicAttributes

def claim_payout(w3: Web3, controller: LocalAccount, sovereign_agent_address: str, market_address: str, chain_id: int) -> str:
    """
    Calls `IntegrityMarket.claimPayout`, execute-routed through
    `sovereign_agent_address` -- required even though `claimPayout` itself
    has no `agentRegistry` check, because `positions[msg.sender]` was
    written by `enter_position` under the SAME contract address (see that
    function). Calling directly from the raw wallet here would look up an
    empty position and revert `NoPosition`, not because of a registry gate
    but because it's simply the wrong key. Reverts if the market isn't
    resolved yet, the agent has no position, already claimed, or was on the
    losing outcome (see IntegrityMarket.sol).
    """
    tracer = get_tracer("integrity_sdk.markets")
    with tracer.start_as_current_span("integrity.markets.claim_payout") as span:
        market = chain._contract(w3, "IntegrityMarket", address=market_address)
        calldata = market.functions.claimPayout().build_transaction({"gas": 0})["data"]
        receipt = _execute_via_agent(w3, controller, sovereign_agent_address, market_address, calldata, chain_id)
        
        market_logs = [log for log in receipt["logs"] if log["address"] == market.address]
        events = market.events.PayoutClaimed().process_receipt({**receipt, "logs": market_logs})
        if events:
            payout = events[0]["args"]["amount"]
            span.set_attribute(EconomicAttributes.MARKETS_TRADE_YIELD, payout)
            span.set_attribute(EconomicAttributes.ITK_BALANCE_DELTA, payout)
            
        return receipt["transactionHash"].hex()


def allocate_capital_onchain(
    w3: Web3,
    allocator: LocalAccount,
    capital_pool_address: str,
    itk_address: str,
    agent_address: str,
    amount_wei: int,
    min_ais_to_maintain: int,
    chain_id: int,
) -> int:
    """
    Raw on-chain allocation -- no BCC commitment, usable by a non-agent
    allocator (a human investor's own wallet) that has no DID to sign with.
    Approves `amount_wei` ITK to the pool, then calls `A2ACapitalPool.allocate`.
    Returns the new allocation's id, parsed from the `Allocated` event.
    """
    chain.approve_erc20(w3, allocator, itk_address, capital_pool_address, amount_wei, chain_id)

    pool = chain._contract(w3, "A2ACapitalPool", address=capital_pool_address)
    tx = pool.functions.allocate(
        Web3.to_checksum_address(agent_address), amount_wei, min_ais_to_maintain
    ).build_transaction(
        {
            "from": allocator.address,
            "nonce": w3.eth.get_transaction_count(allocator.address),
            "chainId": chain_id,
        }
    )
    signed = allocator.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = chain._wait(w3, tx_hash, action="allocate_capital_onchain")

    pool_logs = [log for log in receipt["logs"] if log["address"] == pool.address]
    events = pool.events.Allocated().process_receipt({**receipt, "logs": pool_logs})
    if not events:
        raise RuntimeError("allocate transaction succeeded but emitted no Allocated event")
    return events[0]["args"]["allocationId"]


def allocate_capital_via_agent(
    w3: Web3,
    controller: LocalAccount,
    sovereign_agent_address: str,
    capital_pool_address: str,
    itk_address: str,
    target_agent_address: str,
    amount_wei: int,
    min_ais_to_maintain: int,
    chain_id: int,
) -> int:
    """
    Same as `allocate_capital_onchain`, but for an ALLOCATOR that is itself
    a registered agent: execute-routed through `sovereign_agent_address` (see
    `_execute_via_agent`) so the ITK pulled comes from the agent's
    SovereignAgent contract balance -- where registration.py now mints
    testnet ITK collateral (step 7), not the raw controller wallet, which
    typically holds none. `A2ACapitalPool.allocate` itself has no
    `agentRegistry` check on the allocator (only on the target `agent`
    param, see A2ACapitalPool.sol) -- this function exists purely to move
    the token pull to wherever the calling agent's real balance lives, not
    because the contract requires the allocator to be a SovereignAgent.
    """
    market = chain._contract(w3, "A2ACapitalPool", address=capital_pool_address)
    itk = chain._contract(w3, "IntegrityToken", address=itk_address)

    approve_calldata = itk.functions.approve(
        Web3.to_checksum_address(capital_pool_address), amount_wei
    ).build_transaction({"gas": 0})["data"]
    _execute_via_agent(w3, controller, sovereign_agent_address, itk_address, approve_calldata, chain_id)

    allocate_calldata = market.functions.allocate(
        Web3.to_checksum_address(target_agent_address), amount_wei, min_ais_to_maintain
    ).build_transaction({"gas": 0})["data"]
    receipt = _execute_via_agent(w3, controller, sovereign_agent_address, capital_pool_address, allocate_calldata, chain_id)

    pool_logs = [log for log in receipt["logs"] if log["address"] == market.address]
    events = market.events.Allocated().process_receipt({**receipt, "logs": pool_logs})
    if not events:
        raise RuntimeError("allocate transaction succeeded but emitted no Allocated event")
    return events[0]["args"]["allocationId"]


def release_allocation(w3: Web3, allocator: LocalAccount, capital_pool_address: str, allocation_id: int, chain_id: int) -> str:
    """Calls `A2ACapitalPool.release` -- only the original allocator may call
    this, and only while the target agent's live AIS still clears the
    threshold set at allocation time (see A2ACapitalPool.sol)."""
    pool = chain._contract(w3, "A2ACapitalPool", address=capital_pool_address)
    tx = pool.functions.release(allocation_id).build_transaction(
        {
            "from": allocator.address,
            "nonce": w3.eth.get_transaction_count(allocator.address),
            "chainId": chain_id,
        }
    )
    signed = allocator.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    chain._wait(w3, tx_hash, action="release_allocation")
    return tx_hash.hex()


def clawback_allocation(w3: Web3, allocator: LocalAccount, capital_pool_address: str, allocation_id: int, chain_id: int) -> str:
    """Calls `A2ACapitalPool.clawback` -- only reclaims funds still escrowed
    (pre-release); see A2ACapitalPool.sol's documented post-release limitation."""
    pool = chain._contract(w3, "A2ACapitalPool", address=capital_pool_address)
    tx = pool.functions.clawback(allocation_id).build_transaction(
        {
            "from": allocator.address,
            "nonce": w3.eth.get_transaction_count(allocator.address),
            "chainId": chain_id,
        }
    )
    signed = allocator.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    chain._wait(w3, tx_hash, action="clawback_allocation")
    return tx_hash.hex()


# --- high-level, BCC-integrated flows ---------------------------------------------


@dataclass
class MarketEntryResult:
    tx_hash: str
    verification_token: str
    bcc_commitment_hash: str


def _intercept(
    *,
    agent_id: str,
    intent_type: str,
    intent_payload: dict,
    nonce: int,
    keypair: Keypair,
    chain_id: int,
    verifying_contract: str,
    bcc_middleware_url: str,
) -> tuple[dict, str]:
    """
    Shared helper: builds+signs a BCC commitment for `intent_payload`, POSTs
    it to bcc_middleware's pre-execution gate via bcc.submit_commitment, and returns
    (commitment, verification_token) on success. Raises MarketInterceptDenied
    on any denial -- the caller must never fall through to the on-chain
    action if this raises, since that would defeat the entire point of a
    pre-execution commitment gate.
    """
    commitment = build_bcc_commitment(
        agent_id=agent_id,
        intent_type=intent_type,
        intent_payload=intent_payload,
        nonce=nonce,
        keypair=keypair,
        chain_id=chain_id,
        verifying_contract=verifying_contract,
    )
    
    import requests
    from .bcc import submit_commitment
    try:
        result = submit_commitment(commitment, bcc_middleware_url)
    except requests.RequestException as exc:
        raise MarketInterceptDenied(f"bcc_middleware at {bcc_middleware_url} unreachable: {exc}") from exc

    if not result.get("authorized"):
        raise MarketInterceptDenied(f"bcc_middleware denied commitment: {result.get('reason')}")

    return commitment, result["verification_token"]


def _commitment_hash(commitment: dict) -> bytes:
    """The on-chain `bccCommitmentHash` binding a position to its
    off-chain-committed intent: keccak256 of the commitment's own signature
    bytes, which is unique per commitment (nonce+timestamp+payload all feed
    into the signature) without needing a second hash of the full JSON."""
    sig_hex = commitment["signature"]
    return Web3.keccak(hexstr=sig_hex)


def enter_prediction(
    *,
    agent_id: str,
    keypair: Keypair,
    evm_account: LocalAccount,
    sovereign_agent_address: str,
    market_address: str,
    outcome_index: int,
    amount_wei: int,
    nonce: int,
    rpc_url: Optional[str] = None,
    deployments_file: Optional[str] = None,
    bcc_middleware_url: Optional[str] = None,
) -> MarketEntryResult:
    """
    Full BCC-gated prediction-market entry: sign a commitment declaring
    intent to stake `amount_wei` on `outcome_index` of `market_address`,
    get it past bcc_middleware's pre-execution gate, then submit the real
    `enterPosition` transaction (execute-routed through
    `sovereign_agent_address`, see `enter_position`) carrying the
    commitment's hash. See module docstring for why the gate runs BEFORE the
    on-chain call, not after.
    """
    rpc_url = rpc_url or os.getenv("RPC_URL", "http://localhost:8545")
    deployments_file = deployments_file or os.getenv("DEPLOYMENTS_FILE", "../deployments.local.json")
    bcc_middleware_url = bcc_middleware_url or os.getenv("BCC_MIDDLEWARE_URL", _DEFAULT_BCC_MIDDLEWARE_URL)
    w3 = chain.get_w3(rpc_url)
    chain_id = w3.eth.chain_id
    # docs/plans/2026-08-18-phase1-canonical-intent-encoding-proposal.md: every
    # BCC commitment now binds the registry address it was signed against.
    verifying_contract = chain.load_deployments(deployments_file)["singletons"]["XibalbaAgentRegistry"]

    intent_payload = {
        "action": "enter_prediction_market",
        "market_address": market_address,
        "outcome_index": outcome_index,
        "amount_wei": str(amount_wei),
    }
    commitment, verification_token = _intercept(
        agent_id=agent_id,
        intent_type="PREDICTION_MARKET_ENTRY",
        intent_payload=intent_payload,
        nonce=nonce,
        keypair=keypair,
        chain_id=chain_id,
        verifying_contract=verifying_contract,
        bcc_middleware_url=bcc_middleware_url,
    )

    commitment_hash = _commitment_hash(commitment)
    tx_hash = enter_position(
        w3, evm_account, sovereign_agent_address, market_address, outcome_index, amount_wei, commitment_hash, chain_id
    )
    return MarketEntryResult(tx_hash=tx_hash, verification_token=verification_token, bcc_commitment_hash=commitment_hash.hex())


def enter_binary_option(
    *,
    agent_id: str,
    keypair: Keypair,
    evm_account: LocalAccount,
    sovereign_agent_address: str,
    market_address: str,
    outcome_yes: bool,
    amount_wei: int,
    nonce: int,
    rpc_url: Optional[str] = None,
    deployments_file: Optional[str] = None,
    bcc_middleware_url: Optional[str] = None,
) -> MarketEntryResult:
    """
    Same on-chain mechanism as `enter_prediction` (a binary option is just a
    2-outcome IntegrityMarket -- see IntegrityMarket.sol's NatSpec), but a
    distinct BCC `intent_type` ("BINARY_OPTION_ENTRY" vs
    "PREDICTION_MARKET_ENTRY") so bcc_middleware's OPA policy, the dashboard,
    and the oracle's telemetry can distinguish the two verticals even though
    they share one contract. `outcome_yes=True` maps to outcome index 0
    (YES), `False` to index 1 (NO) -- the convention every binary-option
    market deployed via this SDK should follow.
    """
    rpc_url = rpc_url or os.getenv("RPC_URL", "http://localhost:8545")
    deployments_file = deployments_file or os.getenv("DEPLOYMENTS_FILE", "../deployments.local.json")
    bcc_middleware_url = bcc_middleware_url or os.getenv("BCC_MIDDLEWARE_URL", _DEFAULT_BCC_MIDDLEWARE_URL)
    w3 = chain.get_w3(rpc_url)
    chain_id = w3.eth.chain_id
    # docs/plans/2026-08-18-phase1-canonical-intent-encoding-proposal.md: every
    # BCC commitment now binds the registry address it was signed against.
    verifying_contract = chain.load_deployments(deployments_file)["singletons"]["XibalbaAgentRegistry"]

    outcome_index = 0 if outcome_yes else 1
    intent_payload = {
        "action": "enter_binary_option",
        "market_address": market_address,
        "outcome_yes": outcome_yes,
        "amount_wei": str(amount_wei),
    }
    commitment, verification_token = _intercept(
        agent_id=agent_id,
        intent_type="BINARY_OPTION_ENTRY",
        intent_payload=intent_payload,
        nonce=nonce,
        keypair=keypair,
        chain_id=chain_id,
        verifying_contract=verifying_contract,
        bcc_middleware_url=bcc_middleware_url,
    )

    commitment_hash = _commitment_hash(commitment)
    tx_hash = enter_position(
        w3, evm_account, sovereign_agent_address, market_address, outcome_index, amount_wei, commitment_hash, chain_id
    )
    return MarketEntryResult(tx_hash=tx_hash, verification_token=verification_token, bcc_commitment_hash=commitment_hash.hex())


def allocate_capital(
    *,
    allocator_agent_id: str,
    keypair: Keypair,
    evm_account: LocalAccount,
    allocator_sovereign_agent_address: str,
    capital_pool_address: str,
    itk_address: str,
    target_agent_address: str,
    amount_wei: int,
    min_ais_to_maintain: int,
    nonce: int,
    rpc_url: Optional[str] = None,
    deployments_file: Optional[str] = None,
    bcc_middleware_url: Optional[str] = None,
) -> tuple[int, str]:
    """
    Full BCC-gated agent-to-agent capital allocation: sign a commitment
    declaring intent to allocate `amount_wei` ITK to `target_agent_address`
    (gated on that agent's live AIS staying >= `min_ais_to_maintain`), get it
    past bcc_middleware, then submit the real `A2ACapitalPool.allocate` call
    execute-routed through the allocator's own SovereignAgent contract (see
    `allocate_capital_via_agent`) -- the allocating agent's ITK lives there,
    not on its raw wallet. Returns (allocation_id, verification_token).

    A non-agent (human investor) caller with no DID has no commitment to
    sign and should call `allocate_capital_onchain` directly instead -- see
    module docstring. NOTE: `release_allocation`/`clawback_allocation` below
    are not yet execute-routed -- they assume a human/EOA allocator calling
    directly (matching `A2ACapitalPool.allocate`'s `msg.sender == allocator`
    check). An agent-attributed allocation made via THIS function currently
    has no matching agent-routed release/clawback path; that's an honest,
    documented gap for a follow-up, not a silent one -- releasing/clawing
    back an agent-made allocation today requires extending those two
    functions the same way `enter_position`/`claim_payout` were.
    """
    rpc_url = rpc_url or os.getenv("RPC_URL", "http://localhost:8545")
    deployments_file = deployments_file or os.getenv("DEPLOYMENTS_FILE", "../deployments.local.json")
    bcc_middleware_url = bcc_middleware_url or os.getenv("BCC_MIDDLEWARE_URL", _DEFAULT_BCC_MIDDLEWARE_URL)
    w3 = chain.get_w3(rpc_url)
    chain_id = w3.eth.chain_id
    # docs/plans/2026-08-18-phase1-canonical-intent-encoding-proposal.md: every
    # BCC commitment now binds the registry address it was signed against.
    verifying_contract = chain.load_deployments(deployments_file)["singletons"]["XibalbaAgentRegistry"]

    intent_payload = {
        "action": "allocate_capital",
        "target_agent_address": target_agent_address,
        "amount_wei": str(amount_wei),
        "min_ais_to_maintain": min_ais_to_maintain,
    }
    _commitment, verification_token = _intercept(
        agent_id=allocator_agent_id,
        intent_type="CAPITAL_ALLOCATION",
        intent_payload=intent_payload,
        nonce=nonce,
        keypair=keypair,
        chain_id=chain_id,
        verifying_contract=verifying_contract,
        bcc_middleware_url=bcc_middleware_url,
    )

    allocation_id = allocate_capital_via_agent(
        w3,
        evm_account,
        allocator_sovereign_agent_address,
        capital_pool_address,
        itk_address,
        target_agent_address,
        amount_wei,
        min_ais_to_maintain,
        chain_id,
    )
    return allocation_id, verification_token
