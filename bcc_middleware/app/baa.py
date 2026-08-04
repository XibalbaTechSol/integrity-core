"""
Real on-chain Business Associate Agreement (BAA) status check.

Healthcare-vertical intents (see `requires_baa` in policies/bcc.rego) must
not be authorized unless the agent currently has an *active* BAA recorded
on-chain -- this is a legal/compliance gate, not just a technical one, so it
has to be a real `eth_call` against a real contract, never a hardcoded
allowlist (that was the old prototype's "STAGING MODE" bug this rewrite is
explicitly told not to repeat).

On-chain interface actually implemented by `contracts/src/health/
SmartBAAFactory.sol` (confirmed against the real, already-built/tested
Solidity, not assumed):

    function isBAAActive(address coveredEntity, address businessAssociate) external view returns (bool);

*** CORRECTED PROTOCOL BUG ***
This module used to call a single-argument `isBAAActive(address agent)` --
a signature invented before `contracts/` existed to call against, and never
caught because there was no real contract to catch it. The real factory
contract is keyed on the *pair* `(coveredEntity, businessAssociate)`: one
`SmartBAA` escrow exists per hospital<->agent relationship (see
`SmartBAAFactory.baaOf`), so "is this agent's BAA active" is meaningless
without also saying *which* covered entity it's active with. Calling the
real two-arg function with a one-arg ABI encoding would either revert (best
case -- caught below and correctly treated as CANNOT_VERIFY) or, far worse,
silently ABI-decode into a plausible-but-wrong bool if a future contract
happened to have a matching 4-byte selector by coincidence. Always keep this
ABI byte-for-byte in sync with the deployed contract's real signature rather
than a remembered/assumed one.

`businessAssociate` is derived from the commitment's `agent_id` DID via
`chain.agent_id_to_address` (see that module for the documented, flagged
DID->address convention). `coveredEntity` comes directly from the
commitment's `covered_entity_address` field (see schemas.py) -- it is NOT
derived via `agent_id_to_address`, since a covered entity has no DID at all
in this protocol (it's registered by raw EVM address in
`contracts/src/health/CoveredEntityRegistry.sol`).

Fail-closed policy: if we cannot positively confirm `isBAAActive == true`
(no contract address configured yet, no covered_entity_address on the
commitment, RPC unreachable, call reverts, wrong ABI on the deployed
contract, etc.) the result is `BAAStatus.CANNOT_VERIFY`, and main.py treats
that identically to `INACTIVE` -- i.e. it denies. A missing/broken BAA check
must never be interpreted as "assume compliant".
"""

from __future__ import annotations

import enum
import logging

from web3.exceptions import BadFunctionCallOutput, Web3Exception

from app.chain import AgentResolutionError, agent_id_to_address, get_w3
from app.config import Settings

logger = logging.getLogger("bcc_middleware.baa")

# Minimal ABI fragment -- just the one view function we call. Kept local
# rather than importing contracts/out/SmartBAAFactory.sol/SmartBAAFactory.json
# directly so this package doesn't take a hard build-order dependency on
# `contracts/` having run `forge build` -- but the shape below MUST match
# that artifact's real ABI exactly (see module docstring on the bug this
# caused when it didn't).
_BAA_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "coveredEntity", "type": "address"},
            {"internalType": "address", "name": "businessAssociate", "type": "address"},
        ],
        "name": "isBAAActive",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    }
]


class BAAStatus(enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    CANNOT_VERIFY = "cannot_verify"


def check_baa_status(
    settings: Settings,
    agent_id: str,
    covered_entity_address: str | None,
    *,
    contract_address: str | None = None,
) -> tuple[BAAStatus, str]:
    """
    Returns (status, detail). `covered_entity_address` is required (though
    typed Optional, since it comes straight from the commitment's
    possibly-unset field, see schemas.py) -- a missing value fails closed
    below rather than raising, so a caller forgetting to thread it through
    denies loudly instead of crashing the request. `contract_address` is
    accepted as an override purely so tests can point this at a
    locally-deployed contract without going through `deployments.local.json`;
    production code paths always resolve it from settings, and it should
    point at the deployed `SmartBAAFactory` -- the per-pair `SmartBAA`
    escrow instances it creates do NOT implement `isBAAActive` themselves.
    """
    if not covered_entity_address:
        # This is a caller bug (main.py should never call us for a
        # requires_baa commitment that has no covered_entity_address) as
        # much as a data-quality problem, but either way we cannot name
        # which (coveredEntity, businessAssociate) pair to query -- fail
        # closed rather than guess.
        return (
            BAAStatus.CANNOT_VERIFY,
            f"commitment for agent {agent_id} has no covered_entity_address; cannot resolve which "
            "covered entity (hospital) this BAA check is against",
        )

    address = contract_address or settings.contract_address(settings.baa_contract_name)
    if not address:
        return (
            BAAStatus.CANNOT_VERIFY,
            f"no '{settings.baa_contract_name}' address in {settings.deployments_file} "
            "(contracts/ likely hasn't deployed yet)",
        )

    w3 = get_w3(settings.rpc_url)
    if not w3.is_connected():
        return BAAStatus.CANNOT_VERIFY, f"RPC {settings.rpc_url} is unreachable"

    try:
        agent_address = agent_id_to_address(agent_id, oracle_url=settings.oracle_url)
        covered_entity_checksum = w3.to_checksum_address(covered_entity_address)
        contract = w3.eth.contract(address=w3.to_checksum_address(address), abi=_BAA_ABI)
        active = contract.functions.isBAAActive(covered_entity_checksum, agent_address).call()
    except AgentResolutionError as exc:
        # Can't turn the agent's DID into its real SovereignAgent address (agent
        # unknown to the oracle, oracle down, etc). Fail closed: we cannot verify
        # a BAA for an agent whose on-chain identity we can't resolve.
        logger.warning("BAA check could not resolve agent %s: %s", agent_id, exc)
        return BAAStatus.CANNOT_VERIFY, f"could not resolve agent's on-chain address: {exc}"
    except (BadFunctionCallOutput, Web3Exception, ValueError) as exc:
        # BadFunctionCallOutput / a generic revert usually means the
        # deployed contract doesn't implement isBAAActive the way we expect
        # (e.g. a stale/incompatible ABI) -- treat exactly like "can't
        # verify", not like "inactive", so it's distinguishable in logs.
        # ValueError also covers a malformed covered_entity_address that
        # fails to_checksum_address (e.g. wrong length).
        logger.warning(
            "BAA eth_call failed for agent=%s coveredEntity=%s at %s: %s",
            agent_id,
            covered_entity_address,
            address,
            exc,
        )
        return BAAStatus.CANNOT_VERIFY, f"eth_call to isBAAActive reverted or failed: {exc}"

    return (
        (BAAStatus.ACTIVE if active else BAAStatus.INACTIVE),
        f"isBAAActive({covered_entity_checksum}, {agent_address}) == {active}",
    )
