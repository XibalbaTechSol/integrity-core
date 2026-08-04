"""
Pushes AIS scores to each agent's ReputationRegistry clone and raises
Slasher disputes on detected misbehavior -- closes the loop nothing else
in this monorepo does: integrity-oracle computes AIS and flags misbehavior
but, deliberately (see its own chain.rs docstring: "this service never
signs or submits transactions"), never pushes anything on-chain. Nothing
else did either, until this module. See app/scoring_loop.py for the
periodic orchestration that calls these primitives, and
PRODUCTION_GAPS.md for this gap's history.

bcc_middleware is the chosen home for this signer, not a new dedicated
service: on today's single-operator testnet deployment
(deployments.baseSepolia.json's protocolAddresses), oracleSigner,
disputer, and this service's existing ANCHOR_SIGNER_PRIVATE_KEY /
ANCHOR_ROLE key are the same address, so reusing it avoids standing up a
new service and a new key custody boundary for a role the operator
already holds.

*** Score pushes are best-effort, like anchoring -- NOT a security gate ***
A failed or delayed push leaves an agent's on-chain score stale, not
wrong-but-trusted: nothing downstream treats "no update yet" as "verified
good". Same posture as app/anchor.py; see that module's docstring.

*** Disputes are automated but not dangerous -- raising one only LOCKS
stake, it never moves funds ***. See contracts/src/oracle/Slasher.sol's
own NatSpec: `resolveDispute` needs a separate arbiter role (never the
same key as DISPUTER_ROLE) and a full challenge window before anything is
actually burned. A false-positive automated dispute is recoverable by
that arbiter, not catastrophic -- which is what makes it safe for
app/scoring_loop.py's periodic polling to raise them without a human in
the loop at raise-time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from eth_account import Account
from web3.exceptions import Web3Exception

from app.chain import get_w3
from app.config import Settings
from app.nonce_lock import send_with_managed_nonce, signer_lock

logger = logging.getLogger("bcc_middleware.reputation")

_REPUTATION_REGISTRY_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "agent", "type": "address"},
            {"internalType": "uint256", "name": "baseScore", "type": "uint256"},
        ],
        "name": "updateScore",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

_SLASHER_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "agent", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "string", "name": "reason", "type": "string"},
        ],
        "name": "raiseDispute",
        "outputs": [{"internalType": "uint256", "name": "disputeId", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "", "type": "address"}],
        "name": "stakeOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "", "type": "address"}],
        "name": "lockedStakeOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "disputeId", "type": "uint256"},
            {"indexed": True, "internalType": "address", "name": "agent", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "amount", "type": "uint256"},
            {"indexed": False, "internalType": "string", "name": "reason", "type": "string"},
        ],
        "name": "DisputeRaised",
        "type": "event",
    },
]


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


def push_score(settings: Settings, reputation_registry_address: str, agent_address: str, base_score: int) -> ScorePushResult:
    """
    Signs and submits `updateScore(agent, baseScore)` against one agent's
    ReputationRegistry clone.

    `base_score` MUST be the PRE-boost weighted sum (see
    ReputationRegistry.sol's own NatSpec: "oracle pushes baseScore... this
    contract independently earns the right to apply the 1.15x multiplier").
    Callers must not pass the oracle's already-ZK-boosted `ais` field here
    -- see app/scoring_loop.py's `_base_score_from_ais_response` for how the
    real caller derives it.
    """
    signer_key = _signer_key(settings)
    if not signer_key:
        return ScorePushResult(submitted=False, detail="no reputation/anchor signer key configured")

    w3 = get_w3(settings.rpc_url)
    if not w3.is_connected():
        return ScorePushResult(submitted=False, detail=f"RPC {settings.rpc_url} is unreachable")

    try:
        account = Account.from_key(signer_key)
        contract = w3.eth.contract(address=w3.to_checksum_address(reputation_registry_address), abi=_REPUTATION_REGISTRY_ABI)
        # See app/nonce_lock.py's module docstring: held for the full
        # read-nonce -> sign -> broadcast -> mine sequence, since this key
        # can be the same one app/anchor.py signs with.
        with signer_lock(account.address):
            tx_hash, receipt = send_with_managed_nonce(
                w3,
                account,
                lambda nonce: contract.functions.updateScore(
                    w3.to_checksum_address(agent_address), base_score
                ).build_transaction({"from": account.address, "nonce": nonce, "chainId": settings.chain_id}),
            )
    except (Web3Exception, ValueError) as exc:
        logger.warning("updateScore(%s, %d) submission failed: %s", agent_address, base_score, exc)
        return ScorePushResult(submitted=False, detail=f"transaction submission failed: {exc}")

    if receipt.status != 1:
        return ScorePushResult(submitted=False, detail=f"transaction reverted (status={receipt.status})", tx_hash=tx_hash.hex())

    return ScorePushResult(submitted=True, detail="score pushed", tx_hash=tx_hash.hex())


def get_available_stake(settings: Settings, slasher_address: str, agent_address: str) -> int | None:
    """
    Reads `stakeOf - lockedStakeOf` for an agent, so callers can size a
    dispute without guessing. Returns None (distinct from 0) on any read
    failure, so callers can tell "agent genuinely has zero available
    stake" apart from "couldn't check" -- raising a dispute against a chain
    state we can't even read would be reckless.
    """
    w3 = get_w3(settings.rpc_url)
    if not w3.is_connected():
        return None
    try:
        contract = w3.eth.contract(address=w3.to_checksum_address(slasher_address), abi=_SLASHER_ABI)
        agent = w3.to_checksum_address(agent_address)
        stake = contract.functions.stakeOf(agent).call()
        locked = contract.functions.lockedStakeOf(agent).call()
        return max(0, stake - locked)
    except (Web3Exception, ValueError) as exc:
        logger.warning("could not read available stake for %s from %s: %s", agent_address, slasher_address, exc)
        return None


def raise_dispute(settings: Settings, slasher_address: str, agent_address: str, amount: int, reason: str) -> DisputeResult:
    """
    Signs and submits `raiseDispute(agent, amount, reason)`. Only LOCKS
    `amount` of the agent's stake -- see this module's own docstring and
    Slasher.sol's NatSpec for why that asymmetry (automated raise,
    human-gated resolve) is what makes this safe to call automatically.
    """
    signer_key = _signer_key(settings)
    if not signer_key:
        return DisputeResult(submitted=False, detail="no reputation/anchor signer key configured")

    w3 = get_w3(settings.rpc_url)
    if not w3.is_connected():
        return DisputeResult(submitted=False, detail=f"RPC {settings.rpc_url} is unreachable")

    try:
        account = Account.from_key(signer_key)
        contract = w3.eth.contract(address=w3.to_checksum_address(slasher_address), abi=_SLASHER_ABI)
        # See app/nonce_lock.py's module docstring.
        with signer_lock(account.address):
            tx_hash, receipt = send_with_managed_nonce(
                w3,
                account,
                lambda nonce: contract.functions.raiseDispute(
                    w3.to_checksum_address(agent_address), amount, reason
                ).build_transaction({"from": account.address, "nonce": nonce, "chainId": settings.chain_id}),
            )
    except (Web3Exception, ValueError) as exc:
        logger.warning("raiseDispute(%s, %d, %r) submission failed: %s", agent_address, amount, reason, exc)
        return DisputeResult(submitted=False, detail=f"transaction submission failed: {exc}")

    if receipt.status != 1:
        return DisputeResult(submitted=False, detail=f"transaction reverted (status={receipt.status})", tx_hash=tx_hash.hex())

    dispute_id = None
    try:
        contract = w3.eth.contract(address=w3.to_checksum_address(slasher_address), abi=_SLASHER_ABI)
        logs = contract.events.DisputeRaised().process_receipt(receipt)
        if logs:
            dispute_id = logs[0]["args"]["disputeId"]
    except Exception:  # decoding the event is a nice-to-have, never worth failing the call over
        pass

    return DisputeResult(submitted=True, detail="dispute raised", tx_hash=tx_hash.hex(), dispute_id=dispute_id)
