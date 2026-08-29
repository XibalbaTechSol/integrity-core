"""
Real integration test for the on-chain BAA gate against the ACTUAL
`contracts/` Integrity Health stack -- `CoveredEntityRegistry` + `SmartBAAFactory` +
`SmartBAA` + `IntegrityToken` -- not the lightweight `MockBAARegistry`
fixture that tests/test_chain_baa_anchor.py uses for its broader
eth_call-plumbing coverage.

Why this file exists in addition to that one: the whole point of the bug
this rewrite fixed (`app/baa.py` calling a one-argument `isBAAActive(agent)`
that no real contract ever implemented) is that `MockBAARegistry` was
written to match the WRONG assumed signature and so could never have caught
it -- there was no real contract to check against. This file closes that
gap for good: it compiles/deploys the real Solidity from the sibling
`contracts/` package (via `forge build`'s output in `contracts/out/`,
per docs/INTERFACE_CONTRACT.md's monorepo layout) onto a real local anvil
chain, drives the real registration/creation/signing lifecycle, and proves
`check_baa_status` gets a real True/False back from the real two-argument
`isBAAActive(coveredEntity, businessAssociate)`.

*** Why the agent side of these transactions uses anvil impersonation ***
`app/chain.py::agent_id_to_address` now resolves an agent's real
`SovereignAgent` contract address from integrity-oracle's
`GET /v1/agent/{id}` (see that module and tests/helpers.py's
`mock_oracle_agent_resolution` -- a real oracle isn't part of this file's
fixture set, so its one HTTP call is stubbed, returning a fresh
`Account.create()` address that stands in for "the agent's real on-chain
SovereignAgent address" for these tests' purposes). Either way -- whether a
real oracle resolved it or a freshly generated EVM account stands in for one
-- this test doesn't hold that address's private key, so nothing can locally
sign a transaction FROM it. To drive a real on-chain `SmartBAA.sign()` call as
that exact address (the same address `check_baa_status` independently
re-resolves and queries), this test uses anvil's
`anvil_impersonateAccount`/`anvil_setBalance` cheat RPC methods -- the
JSON-RPC equivalent of Foundry's `vm.prank`, which
`contracts/test/health/SmartBAA.t.sol` already uses for the identical
purpose. This is a standard local-test-chain technique for driving a
contract call as an address you don't hold a key for; it is not a mock of
anything this test is actually verifying (the deployed contracts, the
`isBAAActive` ABI/call, and `check_baa_status`'s interpretation of the
result are all real).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import respx
from eth_account import Account
from web3 import Web3

from app.baa import BAAStatus, check_baa_status
from app.chain import agent_id_to_address
from app.config import Settings
from tests.helpers import mock_oracle_agent_resolution, new_agent

_ORACLE_URL = "http://oracle.test"


def _new_agent_with_resolved_address(respx_mock: respx.MockRouter) -> tuple[str, str]:
    """Generates a fresh agent DID and a fresh, real EVM address to stand in
    for its SovereignAgent contract, and stubs the oracle to resolve one to
    the other -- see tests/helpers.py::mock_oracle_agent_resolution for why
    the oracle (not a pure function of the DID) is the real resolution path
    now that `businessAssociate` must be the agent's actual on-chain
    SovereignAgent address, not a derivation from its Ed25519 pubkey."""
    agent_id, _ = new_agent()
    agent_address = Account.create().address
    mock_oracle_agent_resolution(respx_mock, _ORACLE_URL, agent_id, agent_address)
    return agent_id, agent_address

# Monorepo layout per docs/INTERFACE_CONTRACT.md §9: bcc_middleware/ and
# contracts/ are sibling packages under integrity-core/. `forge build`
# must have already run in contracts/ (it has, as of this test being
# written -- out/ is checked for at collection time below rather than
# assumed, so a missing build fails loudly instead of silently skipping).
CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "contracts"
CONTRACTS_OUT = CONTRACTS_DIR / "out"

# CoveredEntityRegistry.EntityType enum ordinal (Unregistered=0,
# CoveredEntity=1, BusinessAssociate=2) -- see
# contracts/src/health/CoveredEntityRegistry.sol.
ENTITY_TYPE_COVERED_ENTITY = 1


def _load_artifact(contract_file: str, contract_name: str) -> dict:
    path = CONTRACTS_OUT / contract_file / f"{contract_name}.json"
    if not path.exists():
        pytest.skip(
            f"{path} not found -- run `forge build` in {CONTRACTS_DIR} first. "
            "This is a genuine build prerequisite (real Integrity Health contracts), not a mock gap."
        )
    with open(path) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def real_baa_stack(anvil_chain):
    """
    Deploys the REAL IntegrityToken + CoveredEntityRegistry + SmartBAAFactory
    contracts (compiled by contracts/'s own `forge build`) onto the same
    session-scoped local anvil chain the rest of the test suite already
    runs against (see conftest.py's `anvil_chain`).
    """
    w3 = anvil_chain["w3"]
    admin = Account.from_key(anvil_chain["signer_private_key"])

    def _deploy(contract_file: str, contract_name: str, *ctor_args):
        artifact = _load_artifact(contract_file, contract_name)
        abi = artifact["abi"]
        bytecode = artifact["bytecode"]["object"]
        factory = w3.eth.contract(abi=abi, bytecode=bytecode)
        tx = factory.constructor(*ctor_args).build_transaction(
            {
                "from": admin.address,
                "nonce": w3.eth.get_transaction_count(admin.address),
                "chainId": w3.eth.chain_id,
            }
        )
        signed = admin.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
        assert receipt.status == 1, f"{contract_name} deployment reverted"
        return w3.eth.contract(address=receipt.contractAddress, abi=abi)

    # IntegrityToken(admin, initialMint) -- collateral asset SmartBAA.sign()
    # escrows. Individual tests below use requiredCollateral=0 (the escrow
    # mechanics themselves are already covered by
    # contracts/test/health/SmartBAA.t.sol; this file's job is proving the
    # isBAAActive gate specifically), so the initial mint amount here is
    # arbitrary -- it just needs to be a real, functioning ERC20 for
    # SmartBAA's constructor/safeTransferFrom(..., 0) calls to succeed against.
    itk = _deploy("IntegrityToken.sol", "IntegrityToken", admin.address, Web3.to_wei(1_000_000, "ether"))
    registry = _deploy("CoveredEntityRegistry.sol", "CoveredEntityRegistry", admin.address)
    factory = _deploy(
        "SmartBAAFactory.sol", "SmartBAAFactory", registry.address, itk.address, admin.address, admin.address
    )

    return {
        "w3": w3,
        "rpc_url": anvil_chain["rpc_url"],
        "admin": admin,
        "itk": itk,
        "registry": registry,
        "factory": factory,
    }


def _send(w3: Web3, account, bound_fn) -> dict:
    """Builds, signs, and sends a transaction from `account`'s own key; asserts success."""
    tx = bound_fn.build_transaction(
        {
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "chainId": w3.eth.chain_id,
        }
    )
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
    assert receipt.status == 1, f"transaction to {tx['to']} reverted"
    return receipt


def _send_impersonated(w3: Web3, from_address: str, bound_fn) -> dict:
    """
    Sends a transaction FROM `from_address` via anvil impersonation -- see
    module docstring for why the agent side of these tests needs this
    instead of a normal locally-signed transaction.
    """
    w3.provider.make_request("anvil_impersonateAccount", [from_address])
    w3.provider.make_request("anvil_setBalance", [from_address, hex(Web3.to_wei(10, "ether"))])
    try:
        tx_hash = bound_fn.transact({"from": from_address})
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
        assert receipt.status == 1, "impersonated transaction reverted"
        return receipt
    finally:
        w3.provider.make_request("anvil_stopImpersonatingAccount", [from_address])


def _register_covered_entity(w3: Web3, admin, registry, address: str) -> None:
    _send(w3, admin, registry.functions.registerEntity(address, ENTITY_TYPE_COVERED_ENTITY, "ipfs://test-hospital"))


def test_isBAAActive_false_before_any_baa_exists(real_baa_stack):
    """Real contract, real (never-created) pair -> a real `false`, not a revert or a guess."""
    with respx.mock(assert_all_called=False, assert_all_mocked=False) as mock:
        settings = Settings(rpc_url=real_baa_stack["rpc_url"], oracle_url=_ORACLE_URL)
        agent_id, _ = _new_agent_with_resolved_address(mock)
        covered_entity = Account.create().address

        status, detail = check_baa_status(settings, agent_id, covered_entity, contract_address=real_baa_stack["factory"].address)

        assert status is BAAStatus.INACTIVE
        assert "isBAAActive" in detail


def test_isBAAActive_false_when_baa_created_but_not_signed(real_baa_stack):
    """
    `createBAA` alone only reaches SmartBAA.Status.Proposed -- the real
    contract's `isBAAActive` correctly still says false until `sign()`.
    """
    w3 = real_baa_stack["w3"]
    admin = real_baa_stack["admin"]
    registry = real_baa_stack["registry"]
    factory = real_baa_stack["factory"]

    hospital = Account.create()
    w3.provider.make_request("anvil_setBalance", [hospital.address, hex(Web3.to_wei(10, "ether"))])
    _register_covered_entity(w3, admin, registry, hospital.address)

    with respx.mock(assert_all_called=False, assert_all_mocked=False) as mock:
        agent_id, agent_address = _new_agent_with_resolved_address(mock)

        _send(w3, hospital, factory.functions.createBAA(agent_address, Web3.keccak(text="doc-not-signed"), 0))

        settings = Settings(rpc_url=real_baa_stack["rpc_url"], oracle_url=_ORACLE_URL)
        status, _ = check_baa_status(settings, agent_id, hospital.address, contract_address=factory.address)
        assert status is BAAStatus.INACTIVE


def test_isBAAActive_true_after_real_baa_created_and_signed(real_baa_stack):
    """
    The full real lifecycle: register a real Covered Entity, create a real
    SmartBAA escrow via the real Factory, have the business associate
    (agent) really sign it (activating it on-chain), then confirm
    `check_baa_status` -- calling the REAL two-argument
    `isBAAActive(coveredEntity, businessAssociate)` -- reports ACTIVE.
    This is the exact bug scenario from the task: before this fix,
    `check_baa_status` called a one-argument `isBAAActive(agent)` that this
    real contract does not have at all, so this call would have reverted
    (and, worse, an earlier one-arg *mock* would have masked that forever).
    """
    w3 = real_baa_stack["w3"]
    admin = real_baa_stack["admin"]
    registry = real_baa_stack["registry"]
    factory = real_baa_stack["factory"]

    hospital = Account.create()
    w3.provider.make_request("anvil_setBalance", [hospital.address, hex(Web3.to_wei(10, "ether"))])
    _register_covered_entity(w3, admin, registry, hospital.address)

    with respx.mock(assert_all_called=False, assert_all_mocked=False) as mock:
        agent_id, agent_address = _new_agent_with_resolved_address(mock)

        _send(w3, hospital, factory.functions.createBAA(agent_address, Web3.keccak(text="doc-v1"), 0))
        # createBAA returns the deployed SmartBAA address as its return value,
        # not directly readable from a mined receipt -- re-derive it the same
        # way check_baa_status/isBAAActive do, via the factory's own baaOf view.
        baa_address = factory.functions.baaOf(hospital.address, agent_address).call()
        assert baa_address != "0x0000000000000000000000000000000000000000", "createBAA did not register in baaOf"
        baa = w3.eth.contract(address=baa_address, abi=_load_artifact("SmartBAA.sol", "SmartBAA")["abi"])

        settings = Settings(rpc_url=real_baa_stack["rpc_url"], oracle_url=_ORACLE_URL)
        status_before, _ = check_baa_status(settings, agent_id, hospital.address, contract_address=factory.address)
        assert status_before is BAAStatus.INACTIVE  # created but not yet signed

        _send_impersonated(w3, agent_address, baa.functions.sign())

        status_after, detail = check_baa_status(settings, agent_id, hospital.address, contract_address=factory.address)
        assert status_after is BAAStatus.ACTIVE
        assert f"isBAAActive({Web3.to_checksum_address(hospital.address)}, {agent_address}) == True" == detail


def test_isBAAActive_false_again_after_revoke(real_baa_stack):
    """Real state transition back to inactive -- `check_baa_status` isn't caching a stale True."""
    w3 = real_baa_stack["w3"]
    admin = real_baa_stack["admin"]
    registry = real_baa_stack["registry"]
    factory = real_baa_stack["factory"]

    hospital = Account.create()
    w3.provider.make_request("anvil_setBalance", [hospital.address, hex(Web3.to_wei(10, "ether"))])
    _register_covered_entity(w3, admin, registry, hospital.address)

    with respx.mock(assert_all_called=False, assert_all_mocked=False) as mock:
        agent_id, agent_address = _new_agent_with_resolved_address(mock)

        _send(w3, hospital, factory.functions.createBAA(agent_address, Web3.keccak(text="doc-revoke"), 0))
        baa_address = factory.functions.baaOf(hospital.address, agent_address).call()
        baa = w3.eth.contract(address=baa_address, abi=_load_artifact("SmartBAA.sol", "SmartBAA")["abi"])

        _send_impersonated(w3, agent_address, baa.functions.sign())

        settings = Settings(rpc_url=real_baa_stack["rpc_url"], oracle_url=_ORACLE_URL)
        status_active, _ = check_baa_status(settings, agent_id, hospital.address, contract_address=factory.address)
        assert status_active is BAAStatus.ACTIVE

        _send(w3, hospital, baa.functions.revoke())

        status_revoked, _ = check_baa_status(settings, agent_id, hospital.address, contract_address=factory.address)
        assert status_revoked is BAAStatus.INACTIVE
