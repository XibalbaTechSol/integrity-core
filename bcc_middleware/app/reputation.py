"""
Posts AIS checkpoints to the v3 `AISRegistry` and raises `StakeVault` disputes on detected
misbehavior. integrity-oracle computes AIS and flags misbehavior but, deliberately (see its own
chain.rs docstring: "this service never signs or submits transactions"), never writes anything
on-chain. This module is the writer (owner question 3 of the v2 graph deletion plan: the BCC
scoring loop writes `AISRegistry`, holding `SCORER_ROLE` granted at deploy). See
app/scoring_loop.py for the periodic orchestration that calls these primitives.

Every write is keyed by the agent's v3 actor (`AgentRegistry.resolveDID(did).actor`), the
address both `AISRegistry` and `StakeVault` key on.

bcc_middleware is the chosen home for this signer, not a new dedicated service: on the
single-operator testnet deployment the scorer, the disputer and this service's existing
ANCHOR_SIGNER_PRIVATE_KEY are the same address, so reusing it avoids a new key custody
boundary for roles the operator already holds.

*** Checkpoints are best-effort, like anchoring -- NOT a security gate here ***
A failed or delayed post leaves an agent's on-chain score stale, not wrong-but-trusted. Note
what a post DOES do on chain: `AISRegistry.postCheckpoint` calls `StakeVault.onCheckpoint`,
which latches a freeze when the score falls below the vault's `freezeThreshold`. So this loop
can freeze an agent; only governance `unfreeze` lifts it.

*** Disputes are automated but not dangerous -- raising one only HOLDS stake, it never moves
funds ***. `StakeVault.resolveDispute` is admin-gated (never `DISPUTER_ROLE`) and decides
whether anything is burned, so a false-positive automated dispute is recoverable by that
arbiter. That is what makes it safe for the periodic loop to raise them unattended.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from eth_account import Account
from web3.exceptions import Web3Exception

from app.chain import AgentResolutionError, get_w3, registry_contract
from app.config import Settings
from app.nonce_lock import send_with_managed_nonce, signer_lock

logger = logging.getLogger("bcc_middleware.reputation")

# AISRegistry.MAX_SCORE: checkpoint scores are basis points, 0..10000.
MAX_SCORE_BPS = 10_000
ZERO_ROOT = b"\x00" * 32


@dataclass
class ScorePushResult:
    submitted: bool
    detail: str
    tx_hash: str | None = None


@dataclass
class DisputeResult:
    submitted: bool
    detail: str
    tx_hash: str | None = None
    dispute_id: int | None = None


def _signer_key(settings: Settings) -> str | None:
    return settings.reputation_signer_private_key or settings.anchor_signer_private_key


def post_checkpoint(
    settings: Settings,
    ais_registry_address: str,
    actor: str,
    score_bps: int,
    window_end: int,
    *,
    evidence_root: bytes = ZERO_ROOT,
    releasable: int = 0,
) -> ScorePushResult:
    """
    Signs and submits `AISRegistry.postCheckpoint(actor, score_bps, window_end, evidence_root,
    releasable)`.

    `score_bps` is basis points (0..10000), not the Oracle's 0..1000 AIS; the caller converts.
    `releasable` defaults to 0: releasing an agent's per-action locks for a compliant window is
    a policy decision this loop does not make (v2 deletion slice D2). `evidence_root` defaults
    to zero (no root is attested with the score yet).
    """
    if not 0 <= score_bps <= MAX_SCORE_BPS:
        return ScorePushResult(submitted=False, detail=f"score {score_bps} bps is outside 0..{MAX_SCORE_BPS}")

    signer_key = _signer_key(settings)
    if not signer_key:
        return ScorePushResult(submitted=False, detail="no reputation/anchor signer key configured")

    w3 = get_w3(settings.rpc_url)
    if not w3.is_connected():
        return ScorePushResult(submitted=False, detail=f"RPC {settings.rpc_url} is unreachable")

    try:
        account = Account.from_key(signer_key)
        contract = registry_contract(settings, "AISRegistry", ais_registry_address)
        agent = w3.to_checksum_address(actor)
        # See app/nonce_lock.py's module docstring: held for the full read-nonce -> sign ->
        # broadcast -> mine sequence, since this key can be the same one app/anchor.py signs with.
        with signer_lock(account.address):
            tx_hash, receipt = send_with_managed_nonce(
                w3,
                account,
                lambda nonce: contract.functions.postCheckpoint(
                    agent, score_bps, window_end, evidence_root, releasable
                ).build_transaction({"from": account.address, "nonce": nonce, "chainId": settings.chain_id}),
            )
    except (AgentResolutionError, Web3Exception, ValueError) as exc:
        # Includes the pre-flight revert for an actor AgentRegistry does not list as registered
        # (`NotRegisteredAgent`) and for a signer without SCORER_ROLE.
        logger.warning("postCheckpoint(%s, %d) submission failed: %s", actor, score_bps, exc)
        return ScorePushResult(submitted=False, detail=f"transaction submission failed: {exc}")

    if receipt.status != 1:
        return ScorePushResult(submitted=False, detail=f"transaction reverted (status={receipt.status})", tx_hash=tx_hash.hex())

    return ScorePushResult(submitted=True, detail="checkpoint posted", tx_hash=tx_hash.hex())


def get_available_stake(settings: Settings, stake_vault_address: str, actor: str) -> int | None:
    """
    `StakeVault.availableOf(actor)`: free stake net of action locks, open-dispute holds and
    queued withdrawals (never `stakeOf().amount - stakeOf().locked`, which overstates it). Returns
    None (distinct from 0) on any read failure, so callers can tell "genuinely zero" apart from
    "couldn't check"; raising a dispute against chain state we can't read would be reckless.
    """
    w3 = get_w3(settings.rpc_url)
    if not w3.is_connected():
        return None
    try:
        contract = registry_contract(settings, "StakeVault", stake_vault_address)
        return contract.functions.availableOf(w3.to_checksum_address(actor)).call()
    except (AgentResolutionError, Web3Exception, ValueError) as exc:
        logger.warning("could not read available stake for %s from %s: %s", actor, stake_vault_address, exc)
        return None


def raise_dispute(settings: Settings, stake_vault_address: str, actor: str, amount: int, reason: str) -> DisputeResult:
    """
    Signs and submits `StakeVault.raiseDispute(actor, amount, reason)` (the signer needs
    `DISPUTER_ROLE`). Only HOLDS `amount` of the actor's stake; see this module's docstring.
    """
    signer_key = _signer_key(settings)
    if not signer_key:
        return DisputeResult(submitted=False, detail="no reputation/anchor signer key configured")

    w3 = get_w3(settings.rpc_url)
    if not w3.is_connected():
        return DisputeResult(submitted=False, detail=f"RPC {settings.rpc_url} is unreachable")

    try:
        account = Account.from_key(signer_key)
        contract = registry_contract(settings, "StakeVault", stake_vault_address)
        agent = w3.to_checksum_address(actor)
        # See app/nonce_lock.py's module docstring.
        with signer_lock(account.address):
            tx_hash, receipt = send_with_managed_nonce(
                w3,
                account,
                lambda nonce: contract.functions.raiseDispute(agent, amount, reason).build_transaction(
                    {"from": account.address, "nonce": nonce, "chainId": settings.chain_id}
                ),
            )
    except (AgentResolutionError, Web3Exception, ValueError) as exc:
        logger.warning("raiseDispute(%s, %d, %r) submission failed: %s", actor, amount, reason, exc)
        return DisputeResult(submitted=False, detail=f"transaction submission failed: {exc}")

    if receipt.status != 1:
        return DisputeResult(submitted=False, detail=f"transaction reverted (status={receipt.status})", tx_hash=tx_hash.hex())

    dispute_id = None
    try:
        logs = contract.events.DisputeRaised().process_receipt(receipt)
        if logs:
            dispute_id = logs[0]["args"]["disputeId"]
    except Exception:  # decoding the event is a nice-to-have, never worth failing the call over
        pass

    return DisputeResult(submitted=True, detail="dispute raised", tx_hash=tx_hash.hex(), dispute_id=dispute_id)
