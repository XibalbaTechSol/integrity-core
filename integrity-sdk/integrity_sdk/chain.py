"""
Agent-side on-chain client: funding, direct contract deployment, and
primitive registration against the Integrity Protocol contracts.

This is the agent's own equivalent of what `bcc_middleware/app/chain.py` +
`anchor.py` already do for the *middleware's* signer — real web3.py
transactions against whatever EVM node `RPC_URL` points at, no mocked
transport. The difference is whose key signs: bcc_middleware signs as the
protocol's own anchor/oracle signer; every function below (except
`fund_agent_wallet`/`mint_testnet_itk`, which are explicitly the funder
wallet's actions) signs as the *agent's own* wallet (see wallet.py) — that
distinction is the entire point of the self-sovereign registration model
documented in docs/INTERFACE_CONTRACT.md's "Agent Primitives" section: an
agent's identity/anchor contracts are deployed by a transaction the agent
itself signed, not one the protocol signed on its behalf.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from eth_account.signers.local import LocalAccount
from eth_utils import keccak
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import ContractCustomError

_ABIS_DIR = Path(__file__).resolve().parent / "abis"


@lru_cache(maxsize=8)
def get_w3(rpc_url: str) -> Web3:
    """Cached per rpc_url, same rationale as bcc_middleware's `get_w3`: this
    gets called repeatedly across one registration sequence's several
    transactions, and there's no reason to reopen the HTTP provider each time."""
    return Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))


@lru_cache(maxsize=8)
def _load_artifact(contract_name: str) -> dict:
    """Loads the trimmed {abi, bytecode} JSON synced from contracts/out/ via
    `make sync-abis` (see scripts/sync_abis.py) — never reads contracts/out/
    directly, so this package stays usable without a Foundry toolchain present."""
    path = _ABIS_DIR / f"{contract_name}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"No synced ABI for {contract_name!r} at {path}. Run `make sync-abis` "
            f"from the repo root after building contracts/."
        )
    return json.loads(path.read_text())


def _contract(w3: Web3, contract_name: str, address: Optional[str] = None) -> Contract:
    artifact = _load_artifact(contract_name)
    if address is not None:
        return w3.eth.contract(address=Web3.to_checksum_address(address), abi=artifact["abi"])
    return w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"])


class DeploymentsFileMissing(RuntimeError):
    pass


def load_deployments(path: str) -> dict:
    """
    Reads the genesis deployments file written by `contracts/script/Deploy.s.sol`
    (see docs/INTERFACE_CONTRACT.md §6 for the exact nested shape —
    `singletons` / `cloneTemplates` / `protocolAddresses` / `domains`).

    Deliberately raises rather than returning `{}` on a missing file (unlike
    bcc_middleware's best-effort `Settings.load_deployments`): every caller
    of this function is about to sign and broadcast a real transaction that
    needs a real address from this file, so silently proceeding with an
    empty dict would just produce a much more confusing `KeyError` several
    lines later instead of a clear one here.
    """
    p = Path(path)
    if not p.exists():
        raise DeploymentsFileMissing(
            f"{path} does not exist — run `forge script script/Deploy.s.sol "
            f"--broadcast` (see contracts/README.md) before registering any agent."
        )
    return json.loads(p.read_text())


def _wait(w3: Web3, tx_hash: bytes, *, action: str):
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt.status != 1:
        raise RuntimeError(f"{action} transaction reverted (tx {tx_hash.hex()})")
    return receipt


def fund_agent_wallet(w3: Web3, funder: LocalAccount, agent_address: str, amount_wei: int, chain_id: int) -> str:
    """
    Sends `amount_wei` of native ETH from the protocol's funder wallet to a
    freshly-generated agent wallet, so that wallet can sign its own
    deployment transactions (§ "Wallet & funding flow" in the interface
    contract). This is the ONE step in the whole registration sequence
    signed by a key other than the agent's own — by construction, since a
    wallet with zero balance cannot pay for the transaction that would fund it.
    """
    tx = {
        "from": funder.address,
        "to": Web3.to_checksum_address(agent_address),
        "value": amount_wei,
        "nonce": w3.eth.get_transaction_count(funder.address),
        "chainId": chain_id,
        "gas": 21_000,
        "gasPrice": w3.eth.gas_price,
    }
    signed = funder.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    _wait(w3, tx_hash, action="fund_agent_wallet")
    return tx_hash.hex()


def mint_testnet_itk(
    w3: Web3, funder: LocalAccount, itk_address: str, agent_address: str, amount_wei: int, chain_id: int
) -> str:
    """
    Mints `amount_wei` of $ITK directly to a freshly-registered agent's
    wallet, so it has stake-ready collateral for `Slasher`/`SmartBAA`
    without a separate manual step during testing. Requires `funder` to hold
    `MINTER_ROLE` on `IntegrityToken` — true for the deploy script's default
    single-operator testnet setup (see contracts/script/Deploy.s.sol), NOT
    something to rely on in a production deployment where minting should be
    a deliberately separate, audited action, not an automatic side effect of
    registration. Testnet-only convenience — not part of the core
    registration invariants documented in the interface contract.
    """
    itk = _contract(w3, "IntegrityToken", address=itk_address)
    tx = itk.functions.mint(Web3.to_checksum_address(agent_address), amount_wei).build_transaction(
        {
            "from": funder.address,
            "nonce": w3.eth.get_transaction_count(funder.address),
            "chainId": chain_id,
        }
    )
    signed = funder.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    _wait(w3, tx_hash, action="mint_testnet_itk")
    return tx_hash.hex()


def mint_testnet_itk_from_treasury(
    w3: Web3,
    controller: LocalAccount,
    itk_address: str,
    treasury_sovereign_agent: str,
    recipient_address: str,
    amount_wei: int,
    chain_id: int,
) -> str:
    """
    Mints `amount_wei` of $ITK to `recipient_address` **through the liquidity agent's own
    SovereignAgent**, rather than from the protocol funder EOA.

    This is the "single source of ITK liquidity" path: the liquidity agent
    (`xibalba.integrity`, `SovereignAgent 0x360E2a56…` on Base Sepolia) holds `MINTER_ROLE`
    on `IntegrityToken`, so the mint call is routed `SovereignAgent.execute -> ITK.mint`,
    signed by that agent's controller. The resulting mint is attributable on-chain to the
    agent, not to an operator key — the same self-sovereign routing every other agent-owned
    state change in this codebase uses (see `grant_anchor_role`, `anchor_genesis_root`).

    `controller` must be the liquidity agent's controller wallet (it holds
    `DEFAULT_ADMIN_ROLE` on that SovereignAgent), NOT the recipient's.

    Testnet-only, exactly as `mint_testnet_itk` was: minting on a production deployment
    should be a deliberate, audited action, never an automatic side effect of registration.
    """
    itk = _contract(w3, "IntegrityToken", address=itk_address)
    mint_calldata = itk.functions.mint(
        Web3.to_checksum_address(recipient_address), amount_wei
    ).build_transaction({"gas": 0})["data"]

    sovereign_agent = _contract(w3, "SovereignAgent", address=treasury_sovereign_agent)
    tx = sovereign_agent.functions.execute(
        Web3.to_checksum_address(itk_address), 0, mint_calldata
    ).build_transaction(
        {
            "from": controller.address,
            "nonce": w3.eth.get_transaction_count(controller.address),
            "chainId": chain_id,
        }
    )
    signed = controller.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    _wait(w3, tx_hash, action="mint_testnet_itk_from_treasury")
    return tx_hash.hex()


def approve_erc20(w3: Web3, owner: LocalAccount, token_address: str, spender: str, amount_wei: int, chain_id: int) -> str:
    """
    Generic ERC20 `approve`, signed by `owner`. Shared by every market/pool
    interaction that needs to let a spender contract pull ITK
    (`IntegrityMarket.enterPosition`, `A2ACapitalPool.allocate`) — kept here
    rather than duplicated in markets.py since it's not market-specific.
    """
    token = _contract(w3, "IntegrityToken", address=token_address)
    tx = token.functions.approve(Web3.to_checksum_address(spender), amount_wei).build_transaction(
        {
            "from": owner.address,
            "nonce": w3.eth.get_transaction_count(owner.address),
            "chainId": chain_id,
        }
    )
    signed = owner.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    _wait(w3, tx_hash, action="approve_erc20")
    return tx_hash.hex()


def deploy_sovereign_agent(
    w3: Web3, agent: LocalAccount, did: str, oracle_signer: str, chain_id: int
) -> str:
    """
    The agent's own wallet directly deploys its SovereignAgent identity
    contract — `controller_` is the agent's own address, so this one wallet
    is simultaneously the deployer (proving self-sovereign creation) and the
    ongoing controller (able to call `execute`/`rotateController` later).
    Returns the deployed contract's checksummed address.
    """
    factory = _contract(w3, "SovereignAgent")
    tx = factory.constructor(did, agent.address, oracle_signer, "0x0000000000000000000000000000000000000000").build_transaction(
        {
            "from": agent.address,
            "nonce": w3.eth.get_transaction_count(agent.address),
            "chainId": chain_id,
        }
    )
    signed = agent.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = _wait(w3, tx_hash, action="deploy_sovereign_agent")
    return receipt.contractAddress


def deploy_state_anchor(w3: Web3, agent: LocalAccount, sovereign_agent_address: str, chain_id: int) -> str:
    """
    The agent's own wallet directly deploys its StateAnchor instance, with
    `admin` set to the just-deployed SovereignAgent contract address (not
    the raw EOA) — per the protocol's call-routing convention, every
    subsequent state change on this StateAnchor (e.g. granting the oracle
    ANCHOR_ROLE, see `grant_anchor_role`) must be routed through
    `SovereignAgent.execute`.
    """
    factory = _contract(w3, "StateAnchor")
    tx = factory.constructor(Web3.to_checksum_address(sovereign_agent_address)).build_transaction(
        {
            "from": agent.address,
            "nonce": w3.eth.get_transaction_count(agent.address),
            "chainId": chain_id,
        }
    )
    signed = agent.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = _wait(w3, tx_hash, action="deploy_state_anchor")
    return receipt.contractAddress


def grant_anchor_role(
    w3: Web3,
    agent: LocalAccount,
    sovereign_agent_address: str,
    state_anchor_address: str,
    oracle_signer: str,
    chain_id: int,
) -> str:
    """
    Grants the protocol's oracle signer ANCHOR_ROLE on this agent's own
    StateAnchor, so the oracle can later submit Merkle roots on the agent's
    behalf (see the oracle's per-agent anchoring tradeoff, documented in
    docs/INTERFACE_CONTRACT.md §6.6-adjacent telemetry section). Routed
    through `SovereignAgent.execute` — StateAnchor's admin is the
    SovereignAgent contract, not this raw EOA, so a direct `grantRole` call
    from the EOA would revert.
    """
    state_anchor = _contract(w3, "StateAnchor", address=state_anchor_address)
    anchor_role = state_anchor.functions.ANCHOR_ROLE().call()
    grant_calldata = state_anchor.functions.grantRole(anchor_role, Web3.to_checksum_address(oracle_signer)).build_transaction(
        {"gas": 0}
    )["data"]

    sovereign_agent = _contract(w3, "SovereignAgent", address=sovereign_agent_address)
    tx = sovereign_agent.functions.execute(
        Web3.to_checksum_address(state_anchor_address), 0, grant_calldata
    ).build_transaction(
        {
            "from": agent.address,
            "nonce": w3.eth.get_transaction_count(agent.address),
            "chainId": chain_id,
        }
    )
    signed = agent.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    _wait(w3, tx_hash, action="grant_anchor_role")
    return tx_hash.hex()


#: Seed for the "initialized but empty Trust Vault" genesis root — see
#: docs/INTERFACE_CONTRACT.md §4.4a. Hashed, never hardcoded as a hex literal, so every
#: package that needs this value derives the same bytes from the same ASCII string.
GENESIS_VAULT_SEED = "integrity.trust-vault.genesis.v1"


def genesis_vault_root() -> bytes:
    """`keccak256("integrity.trust-vault.genesis.v1")` — the canonical non-zero root
    meaning "vault initialized, nothing in it yet" (spec v0.3 §4.1: an
    empty-but-initialized vault is valid at birth, but `anchorRoot` reverts on
    `bytes32(0)`, so "empty" needs a defined non-zero representation)."""
    return keccak(text=GENESIS_VAULT_SEED)


def anchor_genesis_root(
    w3: Web3,
    agent: LocalAccount,
    sovereign_agent_address: str,
    state_anchor_address: str,
    chain_id: int,
    root: Optional[bytes] = None,
) -> str:
    """
    Anchors the agent's genesis memory root (epoch 0 -> 1) on its own StateAnchor.

    Spec v0.3 §7.2: the genesis root MUST be agent-authorized -- the controller, or
    `SovereignAgent.execute`. This routes through `execute` for exactly the same reason
    `grant_anchor_role` does: StateAnchor's admin is the SovereignAgent *contract*, which
    the constructor also grants ANCHOR_ROLE, so the raw EOA calling `anchorRoot` directly
    would revert. No Solidity change is needed to satisfy §7.2 -- what is still
    [PLANNED] (Appendix A gap 2) is *enforcement* that the protocol's ANCHOR_ROLE signer
    cannot anchor epoch 1 instead.

    Defaults to the empty-vault sentinel; pass `root` to anchor a real vault root when the
    agent already has entries at birth.
    """
    root = root or genesis_vault_root()
    state_anchor = _contract(w3, "StateAnchor", address=state_anchor_address)
    anchor_calldata = state_anchor.functions.anchorRoot(root).build_transaction({"gas": 0})["data"]

    sovereign_agent = _contract(w3, "SovereignAgent", address=sovereign_agent_address)
    tx = sovereign_agent.functions.execute(
        Web3.to_checksum_address(state_anchor_address), 0, anchor_calldata
    ).build_transaction(
        {
            "from": agent.address,
            "nonce": w3.eth.get_transaction_count(agent.address),
            "chainId": chain_id,
        }
    )
    signed = agent.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    _wait(w3, tx_hash, action="anchor_genesis_root")
    return tx_hash.hex()


@dataclass
class PrimitivesRegistered:
    did_hash: str
    sovereign_agent: str
    controller: str
    state_anchor: str
    reputation_registry: str
    slasher: str
    verifier_registry: str
    compliance_gate: str
    agent_profile: str
    domain_id: str


_UNKNOWN_DID_SELECTOR = "0x" + keccak(text="UnknownDID()")[:4].hex()


def resolve_did(w3: Web3, registry_address: str, did: str) -> Optional[PrimitivesRegistered]:
    """
    Reads `XibalbaAgentRegistry.resolveDID(did)`. Unlike `isRegisteredAgent`
    (a plain bool getter), `resolveDID` genuinely REVERTS with the custom
    error `UnknownDID()` for a DID that was never registered -- confirmed by
    reading the contract source directly (`XibalbaAgentRegistry.sol`:
    `if (!record.exists) revert UnknownDID();`), not assumed from the ABI
    alone (the ABI's `view` mutability says nothing about whether the
    function can revert). Returns `None` for that case rather than letting
    the revert propagate; returns the full 7-primitive set (plus
    controller/domain) if the DID is already registered. Any OTHER revert
    (unexpected selector, RPC error) is re-raised, not swallowed.

    Exists so `registration.register_agent` can check BEFORE doing any
    work whether this DID already has a real on-chain registration, and
    short-circuit instead of deploying a second, orphaned
    SovereignAgent/StateAnchor pair that `registerPrimitives` would just
    revert `AlreadyRegistered()` on anyway at the very last step -- after
    already spending gas and testnet ITK on the throwaway pair. See
    `registration.py`'s module docstring for the idempotency contract this
    enables.
    """
    registry = _contract(w3, "XibalbaAgentRegistry", address=registry_address)
    try:
        record = registry.functions.resolveDID(did).call()
    except ContractCustomError as exc:
        selector = exc.args[0] if exc.args else None
        if selector == _UNKNOWN_DID_SELECTOR:
            return None
        raise
    # ABI-decoded tuple shape: (primitives_tuple, controller, domainId, registeredAt, exists)
    primitives, controller, domain_id, _registered_at, exists = record
    if not exists:
        return None
    sovereign_agent, state_anchor, reputation_registry, slasher, verifier_registry, compliance_gate, agent_profile = primitives
    return PrimitivesRegistered(
        did_hash=registry.functions.didHash(did).call().hex(),
        sovereign_agent=sovereign_agent,
        controller=controller,
        state_anchor=state_anchor,
        reputation_registry=reputation_registry,
        slasher=slasher,
        verifier_registry=verifier_registry,
        compliance_gate=compliance_gate,
        agent_profile=agent_profile,
        domain_id=domain_id.hex(),
    )


def register_primitives(
    w3: Web3,
    agent: LocalAccount,
    factory_address: str,
    sovereign_agent_address: str,
    state_anchor_address: str,
    did: str,
    domain_id: bytes,
    vertical: int,
    profile_uri: str,
    chain_id: int,
) -> PrimitivesRegistered:
    """
    Calls `AgentPrimitivesFactory.registerPrimitives`, the step that clones
    and initializes the 5 remaining primitives and atomically registers the
    full 7-address set. `vertical` is the `ComplianceGate.Vertical` enum's
    raw uint8 value (0 = None, 1 = Healthcare — see registration.py for the
    string-to-int mapping callers actually use).

    Parses the real `PrimitivesRegistered` event out of the transaction
    receipt rather than trying to predict clone addresses client-side
    (`Clones.clone`'s CREATE-based address depends on the factory's own
    nonce at call time, which this client doesn't track) — the event is the
    authoritative source for what the factory actually deployed.
    """
    factory = _contract(w3, "AgentPrimitivesFactory", address=factory_address)
    tx = factory.functions.registerPrimitives(
        Web3.to_checksum_address(sovereign_agent_address),
        Web3.to_checksum_address(state_anchor_address),
        did,
        domain_id,
        vertical,
        profile_uri,
    ).build_transaction(
        {
            "from": agent.address,
            "nonce": w3.eth.get_transaction_count(agent.address),
            "chainId": chain_id,
        }
    )
    signed = agent.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = _wait(w3, tx_hash, action="register_primitives")

    # `registerPrimitives` triggers many events across the 5 newly-cloned
    # contracts (their own Initialized/RoleGranted events, etc) in the same
    # receipt. process_receipt tries to decode every log against
    # PrimitivesRegistered's signature and warns loudly for each one that
    # doesn't match — pre-filtering to logs from the factory's own address
    # avoids that noise without changing which event we actually decode.
    factory_logs = [log for log in receipt["logs"] if log["address"] == factory.address]
    events = factory.events.PrimitivesRegistered().process_receipt({**receipt, "logs": factory_logs})
    if not events:
        raise RuntimeError(
            "register_primitives transaction succeeded but emitted no "
            "PrimitivesRegistered event — this should be impossible given "
            "AgentPrimitivesFactory.sol always emits it on success."
        )
    args = events[0]["args"]
    return PrimitivesRegistered(
        did_hash=args["didHash"].hex(),
        sovereign_agent=args["sovereignAgent"],
        controller=args["controller"],
        state_anchor=args["stateAnchor"],
        reputation_registry=args["reputationRegistry"],
        slasher=args["slasher"],
        verifier_registry=args["verifierRegistry"],
        compliance_gate=args["complianceGate"],
        agent_profile=args["agentProfile"],
        domain_id=args["domainId"].hex(),
    )
