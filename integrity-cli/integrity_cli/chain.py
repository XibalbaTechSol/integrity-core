"""
Agent-side on-chain client: funding, direct contract deployment, and
primitive registration against the Integrity Protocol contracts.

CLI-local reimplementation of integrity_sdk.chain -- same real web3.py calls
against whatever EVM node RPC_URL points at (no mocked transport), same
ABI/bytecode artifacts, same transaction sequence. Duplicated rather than
imported per identity.py's "no sibling dependency on integrity-sdk while
both packages are still in flux" philosophy, scoped down to exactly what
`integrity agent register` needs: fund/deploy/register. Unlike the SDK's
chain.py, this module has no telemetry-adjacent surface to trim -- the SDK
version was already just fund/deploy/register, so this is a straight port,
not a subset.

Every function below (except `fund_agent_wallet`/`mint_testnet_itk`, which
are explicitly the funder wallet's actions) signs as the *agent's own*
wallet (see wallet.py) -- that distinction is the entire point of the
self-sovereign registration model documented in
docs/INTERFACE_CONTRACT.md's "Agent Primitives" section: an agent's
identity/anchor contracts are deployed by a transaction the agent itself
signed, not one the protocol signed on its behalf.
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
    """Cached per rpc_url: a single `agent register` invocation makes several
    transactions in sequence, and there's no reason to reopen the HTTP
    provider each time."""
    return Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))


@lru_cache(maxsize=8)
def _load_artifact(contract_name: str) -> dict:
    """Loads the trimmed {abi, bytecode} JSON synced from contracts/out/ via
    `make sync-abis` (see scripts/sync_abis.py, which writes this CLI's copy
    alongside the SDK's) -- never reads contracts/out/ directly, so this
    package stays usable without a Foundry toolchain present."""
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
    (see docs/INTERFACE_CONTRACT.md §6.6 for the exact nested shape --
    `singletons` / `cloneTemplates` / `protocolAddresses` / `domains`).

    Deliberately raises rather than returning `{}` on a missing file: every
    caller of this function is about to sign and broadcast a real
    transaction that needs a real address from this file, so silently
    proceeding with an empty dict would just produce a much more confusing
    `KeyError` several lines later instead of a clear one here.
    """
    p = Path(path)
    if not p.exists():
        raise DeploymentsFileMissing(
            f"{path} does not exist -- run `forge script script/Deploy.s.sol "
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
    signed by a key other than the agent's own -- by construction, since a
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
    Mints `amount_wei` of $ITK to `agent_address`, so the agent has
    stake-ready collateral for `Slasher`/`SmartBAA`/market entry without a
    separate manual step during testing. Callers MUST pass the agent's
    SovereignAgent CONTRACT address here, not its raw EOA wallet --
    `IntegrityMarket`/`A2ACapitalPool` pull ITK from `msg.sender`, which is
    always the SovereignAgent address when a call is routed through its own
    `execute()`, so ITK minted to the wallet instead is stranded and
    unspendable through that path (see `main.py`'s `agent register` command,
    which mints here only after `deploy_sovereign_agent` for exactly this
    reason). Requires `funder` to hold `MINTER_ROLE` on `IntegrityToken` --
    true for the deploy script's default single-operator testnet setup (see
    contracts/script/Deploy.s.sol), NOT something to rely on in a production
    deployment where minting should be a deliberately separate, audited
    action, not an automatic side effect of registration. Testnet-only
    convenience -- not part of the core registration invariants documented
    in the interface contract.
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


def deploy_sovereign_agent(
    w3: Web3, agent: LocalAccount, did: str, oracle_signer: str, chain_id: int, nonce: Optional[int] = None
) -> str:
    """
    The agent's own wallet directly deploys its SovereignAgent identity
    contract -- `controller_` is the agent's own address, so this one wallet
    is simultaneously the deployer (proving self-sovereign creation) and the
    ongoing controller (able to call `execute`/`rotateController` later).
    Returns the deployed contract's checksummed address.
    """
    factory = _contract(w3, "SovereignAgent")
    tx_nonce = nonce if nonce is not None else w3.eth.get_transaction_count(agent.address)
    tx = factory.constructor(did, agent.address, oracle_signer, "0x0000000000000000000000000000000000000000").build_transaction(
        {
            "from": agent.address,
            "nonce": tx_nonce,
            "chainId": chain_id,
        }
    )
    signed = agent.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = _wait(w3, tx_hash, action="deploy_sovereign_agent")
    return receipt.contractAddress


def deploy_state_anchor(w3: Web3, agent: LocalAccount, sovereign_agent_address: str, chain_id: int, nonce: Optional[int] = None) -> str:
    """
    The agent's own wallet directly deploys its StateAnchor instance, with
    `admin` set to the just-deployed SovereignAgent contract address (not
    the raw EOA) -- per the protocol's call-routing convention, every
    subsequent state change on this StateAnchor (e.g. granting the oracle
    ANCHOR_ROLE, see `grant_anchor_role`) must be routed through
    `SovereignAgent.execute`.
    """
    factory = _contract(w3, "StateAnchor")
    tx_nonce = nonce if nonce is not None else w3.eth.get_transaction_count(agent.address)
    tx = factory.constructor(Web3.to_checksum_address(sovereign_agent_address)).build_transaction(
        {
            "from": agent.address,
            "nonce": tx_nonce,
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
    nonce: Optional[int] = None,
) -> str:
    """
    Grants the protocol's oracle signer ANCHOR_ROLE on this agent's own
    StateAnchor, so the oracle can later submit Merkle roots on the agent's
    behalf. Routed through `SovereignAgent.execute` -- StateAnchor's admin is
    the SovereignAgent contract, not this raw EOA, so a direct `grantRole`
    call from the EOA would revert.
    """
    state_anchor = _contract(w3, "StateAnchor", address=state_anchor_address)
    anchor_role = state_anchor.functions.ANCHOR_ROLE().call()
    grant_calldata = state_anchor.functions.grantRole(anchor_role, Web3.to_checksum_address(oracle_signer)).build_transaction(
        {"gas": 0}
    )["data"]

    sovereign_agent = _contract(w3, "SovereignAgent", address=sovereign_agent_address)
    tx_nonce = nonce if nonce is not None else w3.eth.get_transaction_count(agent.address)
    tx = sovereign_agent.functions.execute(
        Web3.to_checksum_address(state_anchor_address), 0, grant_calldata
    ).build_transaction(
        {
            "from": agent.address,
            "nonce": tx_nonce,
            "chainId": chain_id,
        }
    )
    signed = agent.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    _wait(w3, tx_hash, action="grant_anchor_role")
    return tx_hash.hex()


def has_anchor_role(w3: Web3, state_anchor_address: str, oracle_signer: str) -> bool:
    """Read-only check for whether `grant_anchor_role` has already succeeded for this
    StateAnchor -- lets `agent register` skip a redundant (if harmless, since OZ's
    `grantRole` is itself idempotent) transaction on a retry."""
    state_anchor = _contract(w3, "StateAnchor", address=state_anchor_address)
    anchor_role = state_anchor.functions.ANCHOR_ROLE().call()
    return state_anchor.functions.hasRole(anchor_role, Web3.to_checksum_address(oracle_signer)).call()


def itk_balance(w3: Web3, itk_address: str, holder_address: str) -> int:
    """Read-only ITK balance check -- lets `agent register` skip re-minting on a retry,
    which (unlike `grantRole`) is NOT idempotent: calling `mint_testnet_itk` twice mints
    twice."""
    itk = _contract(w3, "IntegrityToken", address=itk_address)
    return itk.functions.balanceOf(Web3.to_checksum_address(holder_address)).call()


def state_anchor_latest_root(w3: Web3, state_anchor_address: str) -> bytes:
    """Read-only `StateAnchor.latestRoot()` -- a non-zero return means `anchor_root` has
    already run for this agent. Lets `agent register` skip re-anchoring on a retry."""
    state_anchor = _contract(w3, "StateAnchor", address=state_anchor_address)
    return state_anchor.functions.latestRoot().call()


_UNKNOWN_DID_SELECTOR = "0x" + keccak(text="UnknownDID()")[:4].hex()


def resolve_did(w3: Web3, registry_address: str, did: str) -> Optional[PrimitivesRegistered]:
    """
    Reads `XibalbaAgentRegistry.resolveDID(did)`. Unlike `isRegisteredAgent` (a plain bool
    getter), `resolveDID` genuinely REVERTS with the custom error `UnknownDID()` for a DID
    that was never registered (confirmed by reading `XibalbaAgentRegistry.sol` directly:
    `if (!record.exists) revert UnknownDID();`) -- returns `None` for that case rather than
    letting the revert propagate; returns the full 7-primitive set (plus controller/domain)
    if the DID is already registered. Any OTHER revert (unexpected selector, RPC error) is
    re-raised, not swallowed.

    Ported from `integrity_sdk.chain.resolve_did` -- this CLI previously had NO idempotency
    check of any kind before `agent register`'s on-chain sequence (unlike the SDK, which at
    least had this check even before its own deploy-resume fix), so every invocation for an
    already-registered DID deployed a second, orphaned SovereignAgent/StateAnchor pair.
    See `main.py`'s `agent_register` and `PRODUCTION_GAPS.md`'s §28 for the full history.
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


#: Canonical seed string for the genesis vault root. Pinned in docs/INTERFACE_CONTRACT.md
#: §4.4a -- never copied as a hex literal. Every package that needs this value derives
#: the same bytes from the same ASCII string.
GENESIS_VAULT_SEED = "integrity.trust-vault.genesis.v1"


def genesis_vault_root() -> bytes:
    """`keccak256("integrity.trust-vault.genesis.v1")` -- the canonical non-zero root
    meaning "vault initialized, nothing in it yet" (spec v0.3 §4.1: an
    empty-but-initialized vault is valid at birth, but `anchorRoot` reverts on
    `bytes32(0)`, so "empty" needs a defined non-zero representation)."""
    return keccak(text=GENESIS_VAULT_SEED)


def anchor_root(
    w3: Web3,
    agent: LocalAccount,
    sovereign_agent_address: str,
    state_anchor_address: str,
    chain_id: int,
    root: Optional[bytes] = None,
    nonce: Optional[int] = None,
) -> str:
    """
    Anchors the agent's memory root on its own StateAnchor.
    """
    root = root or genesis_vault_root()
    state_anchor = _contract(w3, "StateAnchor", address=state_anchor_address)
    anchor_calldata = state_anchor.functions.anchorRoot(root).build_transaction({"gas": 0})["data"]

    sovereign_agent = _contract(w3, "SovereignAgent", address=sovereign_agent_address)
    tx_nonce = nonce if nonce is not None else w3.eth.get_transaction_count(agent.address)
    tx = sovereign_agent.functions.execute(
        Web3.to_checksum_address(state_anchor_address), 0, anchor_calldata
    ).build_transaction(
        {
            "from": agent.address,
            "nonce": tx_nonce,
            "chainId": chain_id,
        }
    )
    signed = agent.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    _wait(w3, tx_hash, action="anchor_root")
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
    nonce: Optional[int] = None,
) -> PrimitivesRegistered:
    """
    Calls `AgentPrimitivesFactory.registerPrimitives`, the step that clones
    and initializes the 5 remaining primitives and atomically registers the
    full 7-address set. `vertical` is the `ComplianceGate.Vertical` enum's
    raw uint8 value (0 = None, 1 = Healthcare).

    Parses the real `PrimitivesRegistered` event out of the transaction
    receipt rather than trying to predict clone addresses client-side
    (`Clones.clone`'s CREATE-based address depends on the factory's own
    nonce at call time, which this client doesn't track) -- the event is the
    authoritative source for what the factory actually deployed.
    """
    factory = _contract(w3, "AgentPrimitivesFactory", address=factory_address)
    tx_nonce = nonce if nonce is not None else w3.eth.get_transaction_count(agent.address)
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
            "nonce": tx_nonce,
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
    # doesn't match -- pre-filtering to logs from the factory's own address
    # avoids that noise without changing which event we actually decode.
    factory_logs = [log for log in receipt["logs"] if log["address"] == factory.address]
    events = factory.events.PrimitivesRegistered().process_receipt({**receipt, "logs": factory_logs})
    if not events:
        raise RuntimeError(
            "register_primitives transaction succeeded but emitted no "
            "PrimitivesRegistered event -- this should be impossible given "
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


# --- XibalbaNameService (XNS, added 2026-07-11) -----------------------------------


def _xns_send_via_agent(
    w3: Web3,
    agent: LocalAccount,
    sovereign_agent_address: str,
    xns_address: str,
    chain_id: int,
    calldata: bytes,
) -> dict:
    """
    Shared build/sign/send/wait for the three XNS state-changing calls below
    (`register`/`set_primary_handle`/`release`), routed through
    `SovereignAgent.execute` -- same pattern `grant_anchor_role` above already
    establishes (see that function's docstring): `XibalbaNameService.register`
    checks `XibalbaAgentRegistry.isRegisteredAgent(msg.sender)`, and the
    registry only knows about `SovereignAgent` *contract* addresses, not
    controller EOAs. Calling XNS directly with the EOA as signer (an earlier,
    wrong version of this function did exactly that) makes `msg.sender` the
    EOA, which is never a registered agent -- caught by the real end-to-end
    test in tests/test_chain.py, which is what this fix is responding to, not
    a hypothetical.
    """
    sovereign_agent = _contract(w3, "SovereignAgent", address=sovereign_agent_address)
    tx = sovereign_agent.functions.execute(Web3.to_checksum_address(xns_address), 0, calldata).build_transaction(
        {
            "from": agent.address,
            "nonce": w3.eth.get_transaction_count(agent.address),
            "chainId": chain_id,
        }
    )
    signed = agent.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return _wait(w3, tx_hash, action="xns")


def xns_register(
    w3: Web3, agent: LocalAccount, sovereign_agent_address: str, xns_address: str, handle: str, chain_id: int
) -> dict:
    """
    Calls `XibalbaNameService.register(handle)` via the agent's own
    `SovereignAgent.execute`, signed by the controller wallet. Reverts
    on-chain (surfaced to the caller as a normal web3 ContractLogicError) if
    `sovereign_agent_address` isn't `isRegisteredAgent` per
    `XibalbaAgentRegistry`, or if `handle` is already claimed -- this
    function does not pre-check either condition client-side, since the
    contract is the authoritative check (see XibalbaNameService.sol's
    NatSpec on why registration is self-service with no privileged
    registrar in the critical path).
    """
    xns = _contract(w3, "XibalbaNameService", address=xns_address)
    calldata = xns.functions.register(handle).build_transaction({"gas": 0})["data"]
    return _xns_send_via_agent(w3, agent, sovereign_agent_address, xns_address, chain_id, calldata)


def xns_set_primary_handle(
    w3: Web3, agent: LocalAccount, sovereign_agent_address: str, xns_address: str, handle: str, chain_id: int
) -> dict:
    xns = _contract(w3, "XibalbaNameService", address=xns_address)
    calldata = xns.functions.setPrimaryHandle(handle).build_transaction({"gas": 0})["data"]
    return _xns_send_via_agent(w3, agent, sovereign_agent_address, xns_address, chain_id, calldata)


def xns_release(
    w3: Web3, agent: LocalAccount, sovereign_agent_address: str, xns_address: str, handle: str, chain_id: int
) -> dict:
    xns = _contract(w3, "XibalbaNameService", address=xns_address)
    calldata = xns.functions.release(handle).build_transaction({"gas": 0})["data"]
    return _xns_send_via_agent(w3, agent, sovereign_agent_address, xns_address, chain_id, calldata)


def xns_resolve(w3: Web3, xns_address: str, handle: str) -> Optional[str]:
    """
    Read-only: resolves a handle to its owning `SovereignAgent` address.
    Unlike the write functions above, this needs no signer -- `resolve` is a
    `view` function. Returns `None` (rather than letting the contract's
    `HandleNotFound` revert propagate as a raw web3 error) for the common
    "handle doesn't exist" case, since callers displaying this to a human
    want a clean not-found result, not an ABI-decoded custom-error message.
    """
    xns = _contract(w3, "XibalbaNameService", address=xns_address)
    try:
        return xns.functions.resolve(handle).call()
    except Exception:  # noqa: BLE001 -- any revert (HandleNotFound) means "not found"
        return None


def xns_primary_handle(w3: Web3, xns_address: str, sovereign_agent: str) -> str:
    """Read-only: the agent's primary handle, or "" if it has none registered."""
    xns = _contract(w3, "XibalbaNameService", address=xns_address)
    return xns.functions.primaryHandle(Web3.to_checksum_address(sovereign_agent)).call()
