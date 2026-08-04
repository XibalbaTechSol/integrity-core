"""
Agent-side client for the Integrity Health (HIPAA/healthcare) vertical: `CoveredEntityRegistry`,
`SmartBAAFactory` + `SmartBAA`, `ComplianceGate`, and `EHRGate`.

Was PRODUCTION_GAPS.md's own documented gap until this module existed: the ABIs
existed (`scripts/sync_abis.py`'s CONTRACTS list already synced `ComplianceGate`,
`CoveredEntityRegistry`, `SmartBAAFactory`, `SmartBAA` — added for exactly this module,
per that script's own comment — plus `EHRGate`, added alongside this file) but zero
Python wrapper functions called any of them; `integrity-dashboard/demo`'s Clinician-Delta
persona (docs/INTERFACE_CONTRACT.md §11) has nothing to build against without this.

Mirrors `markets.py`'s two-tier style exactly: thin, one-real-transaction-each wrappers
around `chain._contract`, reusing `markets._execute_via_agent` for every call an
application contract gates on `agentRegistry.isRegisteredAgent(msg.sender)` — i.e.
`msg.sender` must be the agent's SovereignAgent CONTRACT, never its raw controller
wallet (see that helper's own docstring for why).

Not every function here is agent-routed, though — three real, distinct signer roles
exist in this vertical, and mixing them up is a real on-chain revert, not just a style
choice:
  - `register_covered_entity`: signed by whoever holds REGISTRAR_ROLE (the protocol's
    funder/governance address on today's single-operator testnet) — a direct call, no
    agent involved yet.
  - `create_baa`: signed by the COVERED ENTITY's own EOA (`CoveredEntityRegistry.
    isActiveCoveredEntity(msg.sender)` gates it) — hospitals aren't registered agents
    with a SovereignAgent contract, so this is a plain wallet transaction too.
  - `sign_baa`, `set_self_declared_compliance`, `verify_and_log_access`: signed by the
    AGENT (the business associate / the entity accessing PHI) and MUST be execute-routed
    through its SovereignAgent contract, or the on-chain identity checks fail.
  - `grant_ehr_access`, `revoke_ehr_access`: signed by the PATIENT's own EOA
    (`EHRGate.grantAccess`/`revokeAccess` key off `msg.sender` as the patient directly)
    — patients aren't agents either.
"""

from __future__ import annotations

from eth_account.signers.local import LocalAccount
from web3 import Web3

from . import chain
from .markets import _execute_via_agent

# CoveredEntityRegistry.EntityType enum values (contracts/src/health/CoveredEntityRegistry.sol).
ENTITY_TYPE_UNREGISTERED = 0
ENTITY_TYPE_COVERED_ENTITY = 1
ENTITY_TYPE_BUSINESS_ASSOCIATE = 2


def register_covered_entity(
    w3: Web3,
    registrar: LocalAccount,
    registry_address: str,
    entity_address: str,
    entity_type: int,
    metadata_uri: str,
    chain_id: int,
) -> str:
    """
    Calls `CoveredEntityRegistry.registerEntity` -- REGISTRAR_ROLE-gated, a direct call
    signed by `registrar` (not agent-routed: registering entities is a protocol-level
    vetting action, not something an agent does to/for itself). `entity_type` is one of
    the `ENTITY_TYPE_*` constants above.
    """
    registry = chain._contract(w3, "CoveredEntityRegistry", address=registry_address)
    tx = registry.functions.registerEntity(
        Web3.to_checksum_address(entity_address), entity_type, metadata_uri
    ).build_transaction(
        {
            "from": registrar.address,
            "nonce": w3.eth.get_transaction_count(registrar.address),
            "chainId": chain_id,
        }
    )
    signed = registrar.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    chain._wait(w3, tx_hash, action="register_covered_entity")
    return tx_hash.hex()


def create_baa(
    w3: Web3,
    covered_entity: LocalAccount,
    baa_factory_address: str,
    business_associate_address: str,
    agreement_hash: bytes,
    required_collateral_wei: int,
    chain_id: int,
) -> str:
    """
    Calls `SmartBAAFactory.createBAA` -- signed directly by `covered_entity`'s own EOA
    (must already be registered active via `register_covered_entity` above).
    `business_associate_address` is the AGENT's SovereignAgent contract address (the
    party this BAA will be between), not that agent's raw wallet -- matches
    `isBAAActive`'s keying convention throughout this vertical. Returns the deployed
    `SmartBAA` escrow address (read back from the real `BAACreated` event, not predicted
    client-side -- same rationale as `chain.register_primitives`).
    """
    factory = chain._contract(w3, "SmartBAAFactory", address=baa_factory_address)
    tx = factory.functions.createBAA(
        Web3.to_checksum_address(business_associate_address), agreement_hash, required_collateral_wei
    ).build_transaction(
        {
            "from": covered_entity.address,
            "nonce": w3.eth.get_transaction_count(covered_entity.address),
            "chainId": chain_id,
        }
    )
    signed = covered_entity.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = chain._wait(w3, tx_hash, action="create_baa")

    factory_logs = [log for log in receipt["logs"] if log["address"] == factory.address]
    events = factory.events.BAACreated().process_receipt({**receipt, "logs": factory_logs})
    if not events:
        raise RuntimeError("createBAA transaction succeeded but emitted no BAACreated event")
    return events[0]["args"]["baa"]


def sign_baa(
    w3: Web3,
    controller: LocalAccount,
    sovereign_agent_address: str,
    baa_address: str,
    itk_address: str,
    required_collateral_wei: int,
    chain_id: int,
) -> str:
    """
    Calls `SmartBAA.sign()` -- execute-routed through the agent's SovereignAgent
    contract (the `businessAssociate` a BAA was created against). Two execute-routed
    transactions, same pattern as `markets.enter_position`: first `IntegrityToken.
    approve` (SmartBAA pulls collateral FROM `msg.sender`, which will be the
    SovereignAgent contract once routed, so that's what needs to hold and approve the
    ITK), then `SmartBAA.sign()` itself.
    """
    itk = chain._contract(w3, "IntegrityToken", address=itk_address)
    approve_calldata = itk.functions.approve(
        Web3.to_checksum_address(baa_address), required_collateral_wei
    ).build_transaction({"gas": 0})["data"]
    _execute_via_agent(w3, controller, sovereign_agent_address, itk_address, approve_calldata, chain_id)

    baa = chain._contract(w3, "SmartBAA", address=baa_address)
    sign_calldata = baa.functions.sign().build_transaction({"gas": 0})["data"]
    receipt = _execute_via_agent(w3, controller, sovereign_agent_address, baa_address, sign_calldata, chain_id)
    return receipt["transactionHash"].hex()


def set_self_declared_compliance(
    w3: Web3,
    controller: LocalAccount,
    sovereign_agent_address: str,
    compliance_gate_address: str,
    hipaa_eligible: bool,
    zdr_enabled: bool,
    external_web_access_declared: bool,
    data_residency_region: str,
    chain_id: int,
) -> str:
    """
    Calls `ComplianceGate.setSelfDeclaredCompliance` on the agent's OWN ComplianceGate
    clone (one of the 7 primitives from registration) -- execute-routed, since that
    clone's `DEFAULT_ADMIN_ROLE` is the agent's SovereignAgent address. Purely a
    self-reported posture; `ComplianceGate.isHealthcareCompliant` never trusts these
    flags alone (it independently re-checks the covered entity registry + a live BAA)
    -- see that function's own NatSpec.
    """
    gate = chain._contract(w3, "ComplianceGate", address=compliance_gate_address)
    calldata = gate.functions.setSelfDeclaredCompliance(
        hipaa_eligible, zdr_enabled, external_web_access_declared, data_residency_region
    ).build_transaction({"gas": 0})["data"]
    receipt = _execute_via_agent(w3, controller, sovereign_agent_address, compliance_gate_address, calldata, chain_id)
    return receipt["transactionHash"].hex()


def grant_ehr_access(
    w3: Web3,
    patient: LocalAccount,
    ehr_gate_address: str,
    record_hash: bytes,
    agent_address: str,
    covered_entity_address: str,
    chain_id: int,
) -> str:
    """
    Calls `EHRGate.grantAccess` -- signed directly by the PATIENT's own EOA (patients
    have no SovereignAgent contract; `msg.sender` in the contract IS the patient
    address, by design). `agent_address` is the AGENT's SovereignAgent contract address
    (the only identity `checkAccess`/`verifyAndLogAccess` will later recognize), not its
    raw wallet.
    """
    gate = chain._contract(w3, "EHRGate", address=ehr_gate_address)
    tx = gate.functions.grantAccess(
        record_hash, Web3.to_checksum_address(agent_address), Web3.to_checksum_address(covered_entity_address)
    ).build_transaction(
        {
            "from": patient.address,
            "nonce": w3.eth.get_transaction_count(patient.address),
            "chainId": chain_id,
        }
    )
    signed = patient.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    chain._wait(w3, tx_hash, action="grant_ehr_access")
    return tx_hash.hex()


def revoke_ehr_access(
    w3: Web3, patient: LocalAccount, ehr_gate_address: str, record_hash: bytes, agent_address: str, chain_id: int
) -> str:
    """Calls `EHRGate.revokeAccess` -- same patient-signed, direct-call posture as
    `grant_ehr_access` (see that function's docstring)."""
    gate = chain._contract(w3, "EHRGate", address=ehr_gate_address)
    tx = gate.functions.revokeAccess(record_hash, Web3.to_checksum_address(agent_address)).build_transaction(
        {
            "from": patient.address,
            "nonce": w3.eth.get_transaction_count(patient.address),
            "chainId": chain_id,
        }
    )
    signed = patient.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    chain._wait(w3, tx_hash, action="revoke_ehr_access")
    return tx_hash.hex()


def check_ehr_access(
    w3: Web3, ehr_gate_address: str, sovereign_agent_address: str, patient_address: str, record_hash: bytes
) -> bool:
    """
    Read-only `EHRGate.checkAccess(patient, recordHash)`. Simulates the AGENT as the
    caller via `.call({"from": sovereign_agent_address})` -- `checkAccess` keys its
    lookup on `msg.sender`, so calling it without a `from` would check the SDK
    process's own default account's gate, not the intended agent's, and silently
    return a meaningless `False`. Never reverts (see `EHRGate.sol`'s own NatSpec on
    why an unregistered caller gets `False`, not a revert), so this is safe to call
    speculatively before `verify_and_log_access`.
    """
    gate = chain._contract(w3, "EHRGate", address=ehr_gate_address)
    return gate.functions.checkAccess(Web3.to_checksum_address(patient_address), record_hash).call(
        {"from": Web3.to_checksum_address(sovereign_agent_address)}
    )


def verify_and_log_access(
    w3: Web3,
    controller: LocalAccount,
    sovereign_agent_address: str,
    ehr_gate_address: str,
    patient_address: str,
    record_hash: bytes,
    chain_id: int,
) -> str:
    """
    Calls `EHRGate.verifyAndLogAccess` -- execute-routed through the agent's
    SovereignAgent contract, the same three-way consent+BAA+AIS check as
    `check_ehr_access` but with a real on-chain `AccessLogged` event either way
    (granted or denied), so there's an audit trail of every real access attempt. Returns
    the transaction hash, matching every other write function in this module and in
    `markets.py` -- call `check_ehr_access` first (a free read) if the caller wants the
    boolean outcome before committing to a real transaction.
    """
    gate = chain._contract(w3, "EHRGate", address=ehr_gate_address)
    calldata = gate.functions.verifyAndLogAccess(
        Web3.to_checksum_address(patient_address), record_hash
    ).build_transaction({"gas": 0})["data"]
    receipt = _execute_via_agent(w3, controller, sovereign_agent_address, ehr_gate_address, calldata, chain_id)
    return receipt["transactionHash"].hex()
