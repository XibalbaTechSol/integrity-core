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


def approve_factory_bond(
    w3: Web3,
    agent: LocalAccount,
    sovereign_agent_address: str,
    itk_address: str,
    factory_address: str,
    amount: int,
    chain_id: int,
    nonce: int | None = None,
) -> str:
    """Routes an ERC20 approve through the SovereignAgent to authorize the Factory."""
    itk = _contract(w3, "IntegrityToken", address=itk_address)
    approve_calldata = itk.functions.approve(w3.to_checksum_address(factory_address), amount).build_transaction(
        {"gas": 0}
    )["data"]

    sovereign_agent = _contract(w3, "SovereignAgent", address=sovereign_agent_address)
    tx_nonce = nonce if nonce is not None else w3.eth.get_transaction_count(agent.address)
    tx = sovereign_agent.functions.execute(
        w3.to_checksum_address(itk_address), 0, approve_calldata
    ).build_transaction(
        {
            "from": agent.address,
            "nonce": tx_nonce,
            "chainId": chain_id,
        }
    )
    signed = agent.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    _wait(w3, tx_hash, action="approve_factory_bond")
    return tx_hash.hex()


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


def register_core(
    w3: Web3,
    agent: LocalAccount,
    factory_address: str,
    sovereign_agent_address: str,
    state_anchor_address: str,
    did: str,
    domain_id: bytes,
    chain_id: int,
    nonce: Optional[int] = None,
) -> PrimitivesRegistered:
    """Register only the core identity and anchored-memory primitives."""
    factory = _contract(w3, "AgentPrimitivesFactory", address=factory_address)
    tx_nonce = nonce if nonce is not None else w3.eth.get_transaction_count(agent.address)
    tx = factory.functions.registerCore(
        Web3.to_checksum_address(sovereign_agent_address),
        Web3.to_checksum_address(state_anchor_address),
        did,
        domain_id,
    ).build_transaction({
        "from": agent.address,
        "nonce": tx_nonce,
        "chainId": chain_id,
    })
    signed = agent.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    _wait(w3, tx_hash, action="register_core")
    zero = "0x0000000000000000000000000000000000000000"
    return PrimitivesRegistered(
        did_hash=keccak(text=did).hex(),
        sovereign_agent=Web3.to_checksum_address(sovereign_agent_address),
        controller=Web3.to_checksum_address(agent.address),
        state_anchor=Web3.to_checksum_address(state_anchor_address),
        reputation_registry=zero,
        slasher=zero,
        verifier_registry=zero,
        compliance_gate=zero,
        agent_profile=zero,
        domain_id=domain_id.hex(),
    )


# --- XibalbaNameService (XNS, added 2026-07-11) -----------------------------------


def factory_has_registrar_role(w3: Web3, registry_address: str, factory_address: str) -> bool:
    """Read-only check for whether `factory_address` holds `REGISTRAR_ROLE` on
    `XibalbaAgentRegistry` -- a fixed precondition `AgentPrimitivesFactory.
    registerPrimitives` depends on for `registry.registerPrimitives`/
    `domainRegistry.recordJoin` to succeed. See main.py's `agent_register`."""
    from eth_utils import keccak

    registrar_role = keccak(text="REGISTRAR_ROLE")
    registry = _contract(w3, "XibalbaAgentRegistry", address=registry_address)
    return registry.functions.hasRole(registrar_role, Web3.to_checksum_address(factory_address)).call()


# --------------------------------------------------------------------------
# One chain layer (registration v3 CLI redesign, decision D4)
# --------------------------------------------------------------------------
# These used to be byte-for-byte duplicates of integrity_sdk.chain (same ABIs, same calls), and
# had already drifted: the SDK retries reads and nonce races, this copy did not. The CLI now
# calls the SDK's versions; the names are re-exported so `chain.xns_register(...)` etc. keep
# working for main.py and tests/test_chain.py. The primitives-path helpers above stay here
# until registration v3 PR 3.4 retires that path.
from integrity_sdk.chain import (  # noqa: E402,F401
    can_join_domain,
    deploy_sovereign_agent,
    domain_exists,
    execute_via_agent,
    register_domain,
    xns_primary_handle,
    xns_register,
    xns_release,
    xns_resolve,
    xns_set_primary_handle,
)
