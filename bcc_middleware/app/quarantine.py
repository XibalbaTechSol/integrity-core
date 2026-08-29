"""
Active Quarantine Enforcement — closes the loop `scoring_loop.py` left open.

`scoring_loop.py` can *raise* a `Slasher.raiseDispute` against an agent (locking part of its
stake) when the oracle's flagged-telemetry ratio crosses a threshold, but until this module
nothing ever read that state back into `run_intercept`'s authorization decision — OPA and the
circuit breaker were driven purely by this service's own request history, so an agent already
under active dispute could keep transacting exactly as before. PRODUCTION_GAPS.md §5 names
this as the confirmed-open gap this closes.

The on-chain signal is `Slasher.lockedStakeOf(agent) > 0`. `raiseDispute` locks stake
immediately and `resolveDispute` always decrements it back — whether the dispute resolves as
slashed or released — so this is a live gate with no separate un-quarantine step to build:
quarantine clears itself the moment governance resolves the dispute (see
`contracts/src/oracle/Slasher.sol`'s `resolveDispute`).

Fail-open on CANNOT_VERIFY, deliberately DIFFERENT from `app/baa.py`'s fail-closed posture —
and the difference is scope, not inconsistency. The BAA check only runs for the narrow set of
healthcare-vertical intents OPA flags `requires_baa`, so failing closed there blocks one
legally-sensitive action class when unverifiable. This quarantine check runs unconditionally
for every single request (step 4b in main.py, ahead of OPA), so failing closed on
CANNOT_VERIFY would mean any oracle hiccup or RPC blip denies *all* traffic from *every*
agent — a defense-in-depth secondary control taking down the primary path is a worse failure
mode than the one it exists to catch. Only a POSITIVELY CONFIRMED `lockedStakeOf > 0` denies;
main.py logs CANNOT_VERIFY and lets the request continue to OPA.
"""

from __future__ import annotations

import enum
import logging

from web3.exceptions import BadFunctionCallOutput, Web3Exception

from app.chain import AgentResolutionError, agent_id_to_address, get_w3, resolve_agent_primitives
from app.config import Settings

logger = logging.getLogger("bcc_middleware.quarantine")

# Same ABI fragment app/reputation.py's get_available_stake reads — kept local rather than
# imported cross-module so this gate has no dependency on the reputation-sync loop being
# configured at all (it must work even with DISPUTE_ENABLED=false, since a dispute could have
# been raised in a prior session or by a different operator key).
_SLASHER_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "", "type": "address"}],
        "name": "lockedStakeOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
]


class QuarantineStatus(enum.Enum):
    CLEAR = "clear"
    QUARANTINED = "quarantined"
    CANNOT_VERIFY = "cannot_verify"


def check_quarantine_status(settings: Settings, agent_id: str) -> tuple[QuarantineStatus, str]:
    """
    Returns (status, detail). QUARANTINED means `lockedStakeOf(agent) > 0` on the agent's own
    Slasher clone — an unresolved dispute has locked part of its stake. CANNOT_VERIFY covers
    every failure path (RPC down, agent unresolvable, no slasher primitive yet) and is treated
    identically to QUARANTINED by the caller.
    """
    try:
        primitives = resolve_agent_primitives(settings.oracle_url, agent_id)
    except AgentResolutionError as exc:
        logger.warning("quarantine check could not resolve primitives for %s: %s", agent_id, exc)
        return QuarantineStatus.CANNOT_VERIFY, f"could not resolve agent's primitives: {exc}"

    slasher_address = primitives.get("slasher")
    if not slasher_address:
        return QuarantineStatus.CANNOT_VERIFY, f"agent {agent_id} has no slasher primitive on record"

    w3 = get_w3(settings.rpc_url)
    if not w3.is_connected():
        return QuarantineStatus.CANNOT_VERIFY, f"RPC {settings.rpc_url} is unreachable"

    try:
        agent_address = agent_id_to_address(agent_id, oracle_url=settings.oracle_url)
        contract = w3.eth.contract(address=w3.to_checksum_address(slasher_address), abi=_SLASHER_ABI)
        locked = contract.functions.lockedStakeOf(agent_address).call()
    except AgentResolutionError as exc:
        logger.warning("quarantine check could not resolve agent address for %s: %s", agent_id, exc)
        return QuarantineStatus.CANNOT_VERIFY, f"could not resolve agent's on-chain address: {exc}"
    except (BadFunctionCallOutput, Web3Exception, ValueError) as exc:
        logger.warning("lockedStakeOf eth_call failed for agent=%s at %s: %s", agent_id, slasher_address, exc)
        return QuarantineStatus.CANNOT_VERIFY, f"eth_call to lockedStakeOf reverted or failed: {exc}"

    if locked > 0:
        return QuarantineStatus.QUARANTINED, f"lockedStakeOf({agent_address}) == {locked} (active dispute)"
    return QuarantineStatus.CLEAR, f"lockedStakeOf({agent_address}) == 0"
