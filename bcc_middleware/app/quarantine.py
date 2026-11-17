"""
Active Quarantine Enforcement — reads open disputes back into `run_intercept`'s decision.

`scoring_loop.py` can *raise* a `StakeVault.raiseDispute` against an agent's actor (holding
part of its stake) when the oracle's flagged-telemetry ratio crosses a threshold. This module
reads that state back, so an agent under active dispute cannot keep transacting as before
(PRODUCTION_GAPS.md §5).

The on-chain signal is `StakeVault.disputeLockedOf(actor) > 0`, with the vault resolved through
`AgentRegistry.trustConfig()` -> `TrustConfig.stakeVault()` and the actor through
`AgentRegistry.resolveDID(did).actor`. It is deliberately NOT `stakeOf(actor).locked`: that
field covers per-action locks only (`StakeVault.sol`), so an agent with an open dispute and no
action locks would read as clear. `raiseDispute` raises the hold immediately and
`resolveDispute` always lowers it again, slashed or released, so quarantine clears itself the
moment governance resolves the dispute.

An agent with no bound actor gets `NO_ACTOR` (owner question 8b): no actor, no stake, and so no
on-chain dispute to read. `main.py` treats it exactly as it treats `CANNOT_VERIFY`, which keeps
today's posture for off-chain agents (the Oracle's `primitives` was absent for them too).

Fail-open on CANNOT_VERIFY / NO_ACTOR, deliberately DIFFERENT from `app/baa.py`'s fail-closed
posture, and the difference is scope, not inconsistency. The BAA check only runs for the narrow
set of healthcare-vertical intents OPA flags `requires_baa`, so failing closed there blocks one
legally-sensitive action class when unverifiable. This quarantine check runs unconditionally for
every request (step 4b in main.py, ahead of OPA), so failing closed would mean any RPC blip
denies *all* traffic from *every* agent. Only a POSITIVELY CONFIRMED `disputeLockedOf > 0`
denies; for the high-risk intents in `quarantine_fail_closed_intents`, main.py also denies on
an unverifiable read.
"""

from __future__ import annotations

import enum
import logging

from web3.exceptions import BadFunctionCallOutput, Web3Exception

from app.chain import AgentResolutionError, get_w3, registry_contract, resolve_agent_actor, stake_vault_address
from app.config import Settings

logger = logging.getLogger("bcc_middleware.quarantine")


class QuarantineStatus(enum.Enum):
    CLEAR = "clear"
    QUARANTINED = "quarantined"
    CANNOT_VERIFY = "cannot_verify"
    NO_ACTOR = "no_actor"


def fail_closed_for_intent(settings: Settings, intent_type: str) -> bool:
    """Whether an unverifiable quarantine read must deny this intent.

    Exact matches cover clinical actions; suffix matching covers runtime tool
    labels such as ``claude_tool:Bash:chain_write``. Low-risk reads continue
    to OPA when the secondary quarantine signal is unavailable.
    """
    normalized = (intent_type or "").strip()
    configured = settings.quarantine_fail_closed_intents
    if normalized in configured:
        return True
    return any(normalized.endswith(f":{risk_class}") for risk_class in configured)


def check_quarantine_status(settings: Settings, agent_id: str) -> tuple[QuarantineStatus, str]:
    """
    Returns (status, detail). QUARANTINED means `StakeVault.disputeLockedOf(actor) > 0`: an
    unresolved dispute holds part of the actor's stake. NO_ACTOR means AgentRegistry binds no
    actor to this DID. CANNOT_VERIFY covers every failure path (RPC down, no AgentRegistry in
    the deployments file, malformed or retired DID, unset trust config).
    """
    w3 = get_w3(settings.rpc_url)
    try:
        if not w3.is_connected():
            return QuarantineStatus.CANNOT_VERIFY, f"RPC {settings.rpc_url} is unreachable"
        actor = resolve_agent_actor(settings, agent_id)
        if actor is None:
            return QuarantineStatus.NO_ACTOR, f"NO_ACTOR: AgentRegistry binds no actor to agent {agent_id}"
        vault = stake_vault_address(settings)
        held = registry_contract(settings, "StakeVault", vault).functions.disputeLockedOf(actor).call()
    except AgentResolutionError as exc:
        logger.warning("quarantine check could not resolve agent %s on chain: %s", agent_id, exc)
        return QuarantineStatus.CANNOT_VERIFY, f"could not resolve agent's actor or stake vault: {exc}"
    except (BadFunctionCallOutput, Web3Exception, ValueError, OSError) as exc:
        logger.warning("disputeLockedOf eth_call failed for agent=%s: %s", agent_id, exc)
        return QuarantineStatus.CANNOT_VERIFY, f"eth_call to disputeLockedOf reverted or failed: {exc}"

    if held > 0:
        return QuarantineStatus.QUARANTINED, f"disputeLockedOf({actor}) == {held} (active dispute)"
    return QuarantineStatus.CLEAR, f"disputeLockedOf({actor}) == 0"
