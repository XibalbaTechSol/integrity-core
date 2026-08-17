"""
Top-level self-sovereign agent registration: the full dependency-ordered
sequence described in docs/INTERFACE_CONTRACT.md's "Agent Primitives"
section, from a bare DID all the way to a fully-registered 7-primitive
on-chain identity.

Sequence (each step hard-depends on the previous one succeeding on-chain):
  1. Load or create the agent's Ed25519 DID (did.py).
  2. Load or create the agent's EVM wallet (wallet.py) — a separate keypair.
  3. Attach the EVM wallet as a CAIP-10 verification method on the DID doc.
  4. Fund the EVM wallet with ETH from the protocol's funder wallet (ETH
     pays gas for the wallet's own transactions, including every
     SovereignAgent.execute() call in later steps and in markets.py).
  5. The agent's own wallet directly deploys SovereignAgent.
  6. The agent's own wallet directly deploys StateAnchor.
  7. Mint a testnet ITK allocation to the SovereignAgent CONTRACT (not the
     wallet — testnet convenience, not a core protocol invariant, but the
     mint TARGET is load-bearing: see chain.mint_testnet_itk and this
     module's step-7 comment for why it must be the contract).
  8. Grant the protocol's oracle signer ANCHOR_ROLE on that StateAnchor,
     routed through SovereignAgent.execute.
  9. Call AgentPrimitivesFactory.registerPrimitives to clone+register the
     remaining 5 primitives.
  10. Persist every address next to the DID's document.json.
  11. POST to the oracle's /v1/agent/register, which independently
      re-verifies the claimed primitives against on-chain state before
      accepting the registration (see integrity-oracle's routes.rs) — this
      is what makes registration "real" from the protocol's point of view,
      not just from this SDK's.

This module deliberately does not swallow any step's failure — a partially
completed registration (e.g. SovereignAgent deployed but registerPrimitives
never called) is a real, visible error state, not something to paper over
with a retry-forever loop or a silently-incomplete return value.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, asdict
from typing import Optional

import requests
from web3 import Web3

from . import chain, did, wallet

logger = logging.getLogger("integrity_sdk.registration")

# ComplianceGate.Vertical enum values (contracts/src/health/ComplianceGate.sol).
# One vertical per agent -- ComplianceGate stores a single `Vertical public
# vertical` field, not a list, so "multi-vertical" in the broader MVP sense
# means many DIFFERENT agents each declaring a different vertical (a
# healthcare agent, a trading agent, a market-maker agent), not one agent
# declaring several. This is a self-declared badge for dashboard/discovery
# purposes (mirrors the self-declared compliance flags below Healthcare in
# the enum) -- it does NOT gate participation in IntegrityMarket/
# A2ACapitalPool, which only ever check live AIS (see markets.py); an agent
# can enter a market or receive a capital allocation regardless of which
# vertical (if any) it declared here.
_VERTICALS = {
    "none": 0,
    "healthcare": 1,
    "prediction_market": 2,
    "trading": 3,
    "capital_allocation": 4,
}

_DEFAULT_AGENT_FUND_WEI = Web3.to_wei(0.01, "ether")
_DEFAULT_TESTNET_ITK_ALLOCATION_WEI = Web3.to_wei(10_000, "ether")


class RegistrationError(RuntimeError):
    """Raised when any step of the registration sequence fails. The
    exception message always identifies which step failed — a partially
    completed registration must never look like a generic failure the
    caller has to dig through logs to diagnose."""


def _progress_path(agent_id: Optional[str]):
    """Where a not-yet-fully-registered agent's already-deployed SovereignAgent/
    StateAnchor addresses are recorded, so a subsequent call (a manual retry, or
    an operator re-running the same registration script) resumes from them
    instead of deploying a fresh pair. Separate file from `primitives.json`
    (written only on full success, step 10) so the two can never be confused —
    this file's mere existence means "incomplete," `primitives.json`'s means
    "done."

    Real motivation, not speculative: every documented orphaned SovereignAgent/
    StateAnchor pair on Base Sepolia (PRODUCTION_GAPS.md's registration entry)
    came from exactly this gap — a failure after step 5/6 left nothing on disk
    recording what had already been deployed, so the next attempt (whether an
    operator's manual retry or this function called again) always deployed a
    second, throwaway pair. Real testnet gas, real abandoned contracts, five
    incidents across two sessions before this fix.
    """
    return did.agent_dir(agent_id) / "registration_progress.json"


def _load_deploy_progress(agent_id: Optional[str]) -> Optional[dict]:
    path = _progress_path(agent_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        # Corrupt/unreadable progress file must never block registration —
        # treat exactly like "no progress recorded" and deploy fresh.
        return None


def _save_deploy_progress(agent_id: Optional[str], **fields: str) -> None:
    path = _progress_path(agent_id)
    existing = _load_deploy_progress(agent_id) or {}
    existing.update(fields)
    path.write_text(json.dumps(existing))


def _clear_deploy_progress(agent_id: Optional[str]) -> None:
    path = _progress_path(agent_id)
    if path.exists():
        path.unlink()


@dataclass
class AgentRegistration:
    did: str
    evm_address: str
    sovereign_agent: str
    state_anchor: str
    reputation_registry: str
    slasher: str
    verifier_registry: str
    compliance_gate: str
    agent_profile: str
    domain_id: str
    oracle_registered: bool

    def to_dict(self) -> dict:
        return asdict(self)


def register_agent(
    agent_id: Optional[str] = None,
    *,
    domain_name: str = "general.integrity",
    compliance_vertical: str = "none",
    profile_uri: str = "",
    rpc_url: Optional[str] = None,
    deployments_file: Optional[str] = None,
    oracle_url: Optional[str] = None,
    fund_amount_wei: int = _DEFAULT_AGENT_FUND_WEI,
    testnet_itk_allocation_wei: int = _DEFAULT_TESTNET_ITK_ALLOCATION_WEI,
    skip_oracle_registration: bool = False,
) -> AgentRegistration:
    """
    Runs the full self-sovereign registration sequence for `agent_id`
    (defaults to the DID home's "default" slot — see did.py/wallet.py).

    `rpc_url`/`deployments_file`/`oracle_url` default to the same
    cross-package env vars every other component reads (see
    docs/INTERFACE_CONTRACT.md §3: RPC_URL, DEPLOYMENTS_FILE, ORACLE_URL).

    `skip_oracle_registration=True` runs only the on-chain portion (steps
    1-10) without the final oracle POST — useful for testing/CLI flows
    against a chain that has no oracle running yet. The default is False:
    a "real" registration per the interface contract includes the oracle's
    independent on-chain re-verification.
    """
    rpc_url = rpc_url or os.getenv("RPC_URL", "http://localhost:8545")
    deployments_file = deployments_file or os.getenv("DEPLOYMENTS_FILE", "../deployments.local.json")
    oracle_url = oracle_url or os.getenv("ORACLE_URL", "http://localhost:8080")

    if compliance_vertical not in _VERTICALS:
        raise ValueError(f"compliance_vertical must be one of {sorted(_VERTICALS)}, got {compliance_vertical!r}")

    w3 = chain.get_w3(rpc_url)
    if not w3.is_connected():
        raise RegistrationError(f"RPC {rpc_url} is unreachable — cannot register an agent")
    chain_id = w3.eth.chain_id

    deployments = chain.load_deployments(deployments_file)
    factory_address = deployments["singletons"]["AgentPrimitivesFactory"]
    itk_address = deployments["singletons"]["IntegrityToken"]
    registry_address = deployments["singletons"]["XibalbaAgentRegistry"]
    oracle_signer = deployments["protocolAddresses"]["oracleSigner"]
    funder_key = os.getenv("FUNDER_PRIVATE_KEY")
    if not funder_key:
        raise RegistrationError("FUNDER_PRIVATE_KEY is not set — required to fund the agent's new wallet")

    from eth_account import Account
    from eth_utils import keccak

    funder = Account.from_key(funder_key)

    # Steps 1-3: DID + EVM wallet + CAIP-10 binding.
    agent_did, keypair, doc = did.load_or_create_did(agent_id)
    evm_account = wallet.generate_or_load_evm_wallet(agent_id)
    doc = did.attach_evm_account(doc, evm_account.address, chain_id)

    # Idempotency check (PRODUCTION_GAPS.md Sec3): before spending any gas or
    # testnet ITK, ask XibalbaAgentRegistry whether this exact DID is already
    # fully registered. Without this, retrying after a partial failure (or
    # simply calling register_agent twice for the same DID) always deployed a
    # FRESH SovereignAgent/StateAnchor pair -- register_primitives would then
    # revert AlreadyRegistered() at the very last step, after the gas/ITK for
    # the throwaway pair was already spent, leaving it permanently orphaned
    # (XibalbaAgentRegistry.registerPrimitives runs exactly once per DID, with
    # no update/rotate function). Short-circuiting here instead makes a
    # second call for the same DID a safe, cheap no-op that returns the
    # EXISTING on-chain primitives rather than a wasted duplicate deployment.
    existing = chain.resolve_did(w3, registry_address, agent_did)
    if existing is not None:
        logger.info(
            "agent %s is already registered on-chain (SovereignAgent %s) — skipping "
            "on-chain deployment, returning the existing registration",
            agent_did, existing.sovereign_agent,
        )
        registration = AgentRegistration(
            did=agent_did,
            evm_address=evm_account.address,
            sovereign_agent=existing.sovereign_agent,
            state_anchor=existing.state_anchor,
            reputation_registry=existing.reputation_registry,
            slasher=existing.slasher,
            verifier_registry=existing.verifier_registry,
            compliance_gate=existing.compliance_gate,
            agent_profile=existing.agent_profile,
            domain_id=existing.domain_id,
            oracle_registered=False,
        )
        doc_path = did.agent_dir(agent_id) / "document.json"
        doc_path.write_text(json.dumps(doc, indent=2) + "\n")
        primitives_path = did.agent_dir(agent_id) / "primitives.json"
        primitives_path.write_text(json.dumps(registration.to_dict(), indent=2) + "\n")
        _clear_deploy_progress(agent_id)  # fully registered on-chain -- any lingering progress file is stale

        if not skip_oracle_registration:
            _post_to_oracle(oracle_url, agent_did, doc, registration, keypair, evm_account, idempotent=True)
        logger.info("agent %s already registered (SovereignAgent %s) — no new on-chain work done", agent_did, registration.sovereign_agent)
        return registration

    # Step 4: fund. ETH goes to the WALLET (not the SovereignAgent contract) --
    # the wallet is what pays gas for every transaction the agent signs,
    # including the SovereignAgent.execute() calls that route state changes
    # through its own contract (see step 5's comment for why ITK, unlike
    # ETH, goes to the contract instead).
    try:
        chain.fund_agent_wallet(w3, funder, evm_account.address, fund_amount_wei, chain_id)
    except Exception as exc:  # noqa: BLE001 — re-raised with step context below
        raise RegistrationError(f"step 4 (fund_agent_wallet) failed: {exc}") from exc

    # Steps 5-6: direct deploys. Moved ahead of the testnet ITK mint (which
    # used to be step 5, minting to the wallet) because ITK collateral must
    # live on the SovereignAgent CONTRACT, not the wallet -- see the mint
    # step's comment below for why, and IntegrityMarket.sol/A2ACapitalPool.sol
    # for the downstream contracts that require it.
    #
    # Resume-from-partial-failure: before deploying anything, check whether a
    # prior call already got a SovereignAgent/StateAnchor on-chain for this
    # exact agent_id and simply never finished (steps 7+ failing, e.g. the two
    # missing-role incidents in PRODUCTION_GAPS.md's registration entry). If
    # so, verify each recorded address genuinely has deployed bytecode --
    # never trust a locally-recorded address blindly, the same lesson the
    # phantom-factory incident (PRODUCTION_GAPS.md, same entry) taught the
    # hard way about deployments.baseSepolia.json -- and reuse them instead of
    # paying to deploy a second, throwaway pair. A stale/invalid record (empty
    # bytecode) is silently discarded and this falls through to a fresh
    # deploy, exactly like having no progress file at all.
    progress = _load_deploy_progress(agent_id)
    sovereign_agent = progress.get("sovereign_agent") if progress else None
    state_anchor = progress.get("state_anchor") if progress else None
    if sovereign_agent and w3.eth.get_code(Web3.to_checksum_address(sovereign_agent)) in (b"", "0x"):
        logger.warning("step 5: recorded SovereignAgent %s has no bytecode -- discarding stale progress", sovereign_agent)
        sovereign_agent = None
        state_anchor = None

    if sovereign_agent:
        logger.info("step 5: reusing already-deployed SovereignAgent %s (no new deploy)", sovereign_agent)
    else:
        try:
            sovereign_agent = chain.deploy_sovereign_agent(w3, evm_account, agent_did, oracle_signer, chain_id)
        except Exception as exc:  # noqa: BLE001
            raise RegistrationError(f"step 5 (deploy_sovereign_agent) failed: {exc}") from exc
        _save_deploy_progress(agent_id, sovereign_agent=sovereign_agent)

    if state_anchor and w3.eth.get_code(Web3.to_checksum_address(state_anchor)) in (b"", "0x"):
        logger.warning("step 6: recorded StateAnchor %s has no bytecode -- discarding stale progress", state_anchor)
        state_anchor = None

    if state_anchor:
        logger.info("step 6: reusing already-deployed StateAnchor %s (no new deploy)", state_anchor)
    else:
        try:
            state_anchor = chain.deploy_state_anchor(w3, evm_account, sovereign_agent, chain_id)
        except Exception as exc:  # noqa: BLE001
            raise RegistrationError(
                f"step 6 (deploy_state_anchor) failed — SovereignAgent {sovereign_agent} was deployed "
                f"and its address is saved in {_progress_path(agent_id)}; a retry will reuse it "
                f"rather than deploying a second one: {exc}"
            ) from exc
        _save_deploy_progress(agent_id, sovereign_agent=sovereign_agent, state_anchor=state_anchor)

    # Step 7: testnet ITK allocation, minted to the SovereignAgent CONTRACT
    # address (not the wallet). Every AIS-gated application contract
    # (IntegrityMarket.enterPosition, A2ACapitalPool via markets.py) checks
    # `agentRegistry.isRegisteredAgent(msg.sender)` -- which only resolves
    # for the SovereignAgent contract address, never the raw controller
    # wallet (see XibalbaAgentRegistry.sol: `didHashOf` is keyed on
    # `primitives.sovereignAgent`). Since those same calls also pull ITK
    # FROM msg.sender, the collateral has to already be sitting on that same
    # contract, or every real market/allocation transaction markets.py
    # submits (via SovereignAgent.execute, see markets.py) would revert with
    # an ERC20 insufficient-balance error despite the agent's wallet holding
    # plenty of ITK it can never spend through that call path.
    # Skip re-minting on a retry that already got this far -- unlike grant_anchor_role
    # below (idempotent by construction, OZ's grantRole no-ops if already held), minting
    # again would genuinely double-issue ITK to the same SovereignAgent.
    already_minted = testnet_itk_allocation_wei > 0 and chain.itk_balance(w3, itk_address, sovereign_agent) >= testnet_itk_allocation_wei
    if already_minted:
        logger.info("step 7: SovereignAgent %s already holds >= %s wei ITK -- skipping mint", sovereign_agent, testnet_itk_allocation_wei)

    if testnet_itk_allocation_wei > 0 and not already_minted:
        # Preferred path: mint from the protocol's designated *liquidity agent* (e.g.
        # `xibalba.integrity`), so testnet ITK is issued by a registered agent through its
        # own `SovereignAgent.execute` and is attributable on-chain to that agent rather
        # than to an operator EOA.
        #
        # This requires the liquidity agent's CONTROLLER key to be present locally, since
        # only the controller may call `execute`. That is true for the current
        # single-operator testnet setup and false in general — a third party registering
        # its own agent obviously cannot sign as the liquidity agent. So this falls back to
        # the funder mint rather than failing registration, and says so in the log. A
        # multi-operator deployment would replace this with a request to a faucet service
        # the liquidity agent runs, not with a shared key.
        liquidity_agent_id = os.getenv("INTEGRITY_LIQUIDITY_AGENT")
        minted_from_treasury = False
        if liquidity_agent_id:
            try:
                liquidity_primitives = json.loads(
                    (did.agent_dir(liquidity_agent_id) / "primitives.json").read_text()
                )
                liquidity_sa = liquidity_primitives["sovereign_agent"]
                liquidity_controller = wallet.generate_or_load_evm_wallet(liquidity_agent_id)
                chain.mint_testnet_itk_from_treasury(
                    w3,
                    liquidity_controller,
                    itk_address,
                    liquidity_sa,
                    sovereign_agent,
                    testnet_itk_allocation_wei,
                    chain_id,
                )
                minted_from_treasury = True
                logger.info(
                    "step 7: minted %s wei ITK to %s via liquidity agent '%s' (%s)",
                    testnet_itk_allocation_wei, sovereign_agent, liquidity_agent_id, liquidity_sa,
                )
            except Exception as exc:  # noqa: BLE001 — fall back, but never silently
                logger.warning(
                    "step 7: liquidity-agent mint via '%s' failed (%r) — falling back to the "
                    "funder mint. The ITK will be issued by the operator EOA, not by the agent.",
                    liquidity_agent_id, exc,
                )

        if not minted_from_treasury:
            try:
                chain.mint_testnet_itk(w3, funder, itk_address, sovereign_agent, testnet_itk_allocation_wei, chain_id)
            except Exception as exc:  # noqa: BLE001
                raise RegistrationError(f"step 7 (mint_testnet_itk) failed: {exc}") from exc

    # Step 8: route the ANCHOR_ROLE grant through the agent's own contract. Idempotent by
    # construction (OZ's grantRole no-ops if the role is already held) but checked first
    # anyway on a retry, to skip the transaction entirely rather than pay gas for a no-op.
    if chain.has_anchor_role(w3, state_anchor, oracle_signer):
        logger.info("step 8: StateAnchor %s already granted ANCHOR_ROLE to %s -- skipping", state_anchor, oracle_signer)
    else:
        try:
            chain.grant_anchor_role(w3, evm_account, sovereign_agent, state_anchor, oracle_signer, chain_id)
        except Exception as exc:  # noqa: BLE001
            raise RegistrationError(
                f"step 8 (grant_anchor_role) failed — SovereignAgent {sovereign_agent} and "
                f"StateAnchor {state_anchor} were deployed but are not fully wired: {exc}"
            ) from exc

    # Step 8b: anchor the genesis memory root, BEFORE registerPrimitives.
    #
    # Spec v0.3 §6 fixes this ordering ("deploy SovereignAgent + StateAnchor →
    # agent-authorize genesis memory root → registerPrimitives") and §7.1 makes it
    # load-bearing: the oracle independently reads `StateAnchor.latestRoot` at
    # `POST /v1/agent/register` and returns 400 MemoryNotInitialized on a zero root. An
    # agent that skipped this step deploys fine on-chain and then cannot register with the
    # oracle — hence doing it here, inside the atomic registration flow, rather than
    # leaving it to callers.
    #
    # Idempotence: NOT guaranteed solely by step 0's resolve_did short-circuit, despite
    # what this comment used to claim -- resolve_did only catches a retry once
    # registerPrimitives (step 9) has succeeded. A retry after step 9 itself fails (the
    # exact shape of both real incidents in PRODUCTION_GAPS.md's registration entry) reaches
    # this line again for the same StateAnchor, so it's checked explicitly here too, the
    # same way steps 5-8 now are.
    if chain.state_anchor_latest_root(w3, state_anchor) != b"\x00" * 32:
        logger.info("step 8b: StateAnchor %s already has a non-zero root -- skipping re-anchor", state_anchor)
    else:
        try:
            chain.anchor_genesis_root(w3, evm_account, sovereign_agent, state_anchor, chain_id)
        except Exception as exc:  # noqa: BLE001
            raise RegistrationError(
                f"step 8b (anchor_genesis_root) failed — SovereignAgent {sovereign_agent} and "
                f"StateAnchor {state_anchor} exist on-chain but the agent has no genesis memory "
                f"root, so the oracle will reject it with MemoryNotInitialized: {exc}"
            ) from exc

    # Step 9: clone + register the remaining 5.
    domain_id = keccak(text=domain_name)
    try:
        result = chain.register_primitives(
            w3,
            evm_account,
            factory_address,
            sovereign_agent,
            state_anchor,
            agent_did,
            domain_id,
            _VERTICALS[compliance_vertical],
            profile_uri,
            chain_id,
        )
    except Exception as exc:  # noqa: BLE001
        raise RegistrationError(
            f"step 9 (register_primitives) failed — SovereignAgent {sovereign_agent} and "
            f"StateAnchor {state_anchor} exist on-chain but are not registered in "
            f"XibalbaAgentRegistry: {exc}"
        ) from exc

    registration = AgentRegistration(
        did=agent_did,
        evm_address=evm_account.address,
        sovereign_agent=result.sovereign_agent,
        state_anchor=result.state_anchor,
        reputation_registry=result.reputation_registry,
        slasher=result.slasher,
        verifier_registry=result.verifier_registry,
        compliance_gate=result.compliance_gate,
        agent_profile=result.agent_profile,
        domain_id=result.domain_id,
        oracle_registered=False,
    )

    # Step 10: persist.
    doc_path = did.agent_dir(agent_id) / "document.json"
    doc_path.write_text(json.dumps(doc, indent=2) + "\n")
    primitives_path = did.agent_dir(agent_id) / "primitives.json"
    primitives_path.write_text(json.dumps(registration.to_dict(), indent=2) + "\n")
    # registerPrimitives just succeeded -- resolve_did's idempotency check (top of this
    # function) now covers this DID going forward, so the deploy-progress file has done its
    # job and would only be misleading state to leave behind.
    _clear_deploy_progress(agent_id)

    # Step 11: oracle independent re-verification.
    if not skip_oracle_registration:
        _post_to_oracle(oracle_url, agent_did, doc, registration, keypair, evm_account, idempotent=False)

    logger.info("registered agent %s (SovereignAgent %s)", agent_did, registration.sovereign_agent)
    return registration


def _post_to_oracle(
    oracle_url: str,
    agent_did: str,
    doc: dict,
    registration: "AgentRegistration",
    keypair,
    evm_account,
    *,
    idempotent: bool,
) -> None:
    """
    POSTs to the oracle's `/v1/agent/register`, mutating `registration.oracle_registered`
    on success. Payload shape is pinned by integrity-oracle's real
    `RegisterAgentRequest` struct (handlers.rs) -- see docs/INTERFACE_CONTRACT.md §6.3
    for the documented schema. Three things this used to get wrong (found 2026-07-09 via
    a real 422/400 against a live oracle, not a guess):
      1. The DID field is named `did`, not `agent_id` -- sending `agent_id` left the
         struct's required `did` field missing, which serde rejects at the
         JSON-body-extraction layer (422) before the handler even runs.
      2. `primitives` must be exactly the 7-address PrimitiveSetDto shape -- built
         explicitly here rather than reusing `registration.to_dict()` (which also
         carries `did`/`evm_address`/`domain_id`/`oracle_registered`, fields
         PrimitiveSetDto doesn't have).
      3. The handler requires at least one of `ed25519_pubkey_hex`/`eth_address_hex`
         (400 if both are absent) so it has real verification material to store
         against the DID -- both are sent here since this SDK always has both by this
         point in the sequence.

    `idempotent=True` (the on-chain-already-registered short-circuit path in
    `register_agent`) treats a 409 (`AppError::AgentAlreadyExists` -- the oracle's own
    Postgres unique-violation on `agents.id`) as success, not an error: the oracle
    already knowing about this DID is exactly the expected outcome when we already know
    it's on-chain registered, not a failure to propagate. A non-idempotent call (a fresh
    registration) still treats any failure, 409 included, as a real error -- the
    interface contract's stance that an agent isn't "really" registered until the
    oracle independently re-verifies it stays true for that path.
    """
    try:
        resp = requests.post(
            f"{oracle_url}/v1/agent/register",
            json={
                "did": agent_did,
                "did_document": doc,
                "primitives": {
                    "sovereign_agent": registration.sovereign_agent,
                    "state_anchor": registration.state_anchor,
                    "reputation_registry": registration.reputation_registry,
                    "slasher": registration.slasher,
                    "verifier_registry": registration.verifier_registry,
                    "compliance_gate": registration.compliance_gate,
                    "agent_profile": registration.agent_profile,
                },
                "ed25519_pubkey_hex": "0x" + keypair.public_bytes().hex(),
                "eth_address_hex": evm_account.address,
            },
            timeout=10,
        )
        if idempotent and resp.status_code == 409:
            registration.oracle_registered = True
            return
        resp.raise_for_status()
        registration.oracle_registered = True
    except requests.RequestException as exc:
        # Deliberately re-raised, not swallowed: per the interface contract, an agent
        # isn't "really" registered from the protocol's point of view until the oracle
        # has independently re-verified it on-chain. A caller that genuinely wants the
        # on-chain-only state (e.g. to register the oracle service itself, which can't
        # call its own not-yet-running API) should pass skip_oracle_registration=True
        # explicitly rather than have this fail silently.
        raise RegistrationError(
            f"step 11 (oracle registration) failed — the agent's 7 primitives are "
            f"fully deployed and registered on-chain at {registration.sovereign_agent}, "
            f"but the oracle at {oracle_url} did not accept the registration: {exc}"
        ) from exc
