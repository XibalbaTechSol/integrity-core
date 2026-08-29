"""
Issues and verifies the `verification_token` returned by a successful
`POST /v1/bcc/intercept` (PRODUCTION_GAPS.md §5).

*** What this used to be, and why it was a false claim ***
`schemas.py` documented the token as "proving this middleware evaluated and
approved the commitment" -- but it was `sha256(agent_id|nonce|
intended_state_hash|time.time())`: unsigned, unpersisted, and trivially
recomputable by ANYONE who knows the (public) commitment fields, since
sha256 has no secret key involved. No relying party could actually verify
it against anything; every consumer found in this codebase just
displayed/threaded the value through without checking it.

*** What it is now ***
An HMAC-SHA256 keyed with a process-local secret (`Settings.
bcc_verification_secret`) that only this service holds -- computing a valid
token requires the key, so a token's mere well-formedness is no longer
forgeable. It's also PERSISTED (in-memory, see module docstring on scope)
so a relying party can ask this service, via `POST /v1/bcc/verify_token`,
whether a given token was genuinely issued for exactly those commitment
fields -- closing the "checked by nobody" half of the original finding, not
just the "proves nothing" half.

Deterministic over (agent_id, nonce, intended_state_hash): the commitment's
own nonce is already unique per agent (nonce replay is rejected upstream in
run_intercept), so there's no need to fold in a timestamp/random salt to
avoid collisions -- doing so would only make the token non-reproducible for
no security benefit, since HMAC unforgeability comes from the secret key,
not from unpredictability of the material.

In-memory, single-process persistence is an accepted scope limitation, same
posture as `nonce_store.py`/`circuit_breaker.py`: tokens are short-lived
"did this service just approve this" proofs, not long-term credentials, so
not surviving a restart is fine.

*** Bounded, unlike nonce_store.py/circuit_breaker.py ***
Those two are naturally bounded by agent count (one entry per agent).
`_issued_tokens` is keyed by TOKEN, one new entry per successfully
authorized `/v1/bcc/intercept` call -- forever, with nothing to evict it,
which is an unbounded memory leak on the hot path, not "same posture" at
all. `_MAX_ISSUED_TOKENS` caps it: oldest-issued entries are evicted once
the cap is exceeded (a plain `dict` preserves insertion order in Python,
so the oldest entries are simply the ones at the front). A verify request
against an evicted token correctly reports `valid: false` -- the same
answer a caller gets for a token that was simply never issued, which is an
acceptable, documented tradeoff for a "did you approve this a moment ago"
proof, not a long-term audit record (that's what the Merkle-anchored
on-chain trail is for).
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass

from app.config import Settings

_MAX_ISSUED_TOKENS = 50_000

# token -> issued record. See module docstring on in-memory scope and bound.
_issued_tokens: dict[str, "IssuedToken"] = {}


@dataclass(frozen=True)
class IssuedToken:
    agent_id: str
    nonce: int
    intended_state_hash: str
    issued_at: float


def _compute(settings: Settings, agent_id: str, nonce: int, intended_state_hash: str) -> str:
    material = f"{agent_id}|{nonce}|{intended_state_hash}".encode()
    return hmac.new(settings.bcc_verification_secret.encode(), material, hashlib.sha256).hexdigest()


def issue_token(settings: Settings, agent_id: str, nonce: int, intended_state_hash: str) -> str:
    """Computes and persists a token for an approved commitment. Called
    exactly once per successful `run_intercept`, after every gate has
    already passed."""
    token = _compute(settings, agent_id, nonce, intended_state_hash)
    _issued_tokens[token] = IssuedToken(
        agent_id=agent_id, nonce=nonce, intended_state_hash=intended_state_hash, issued_at=time.time()
    )
    if len(_issued_tokens) > _MAX_ISSUED_TOKENS:
        # dicts preserve insertion order -- the oldest-issued entries are
        # simply the ones at the front. Evict enough to get back under the
        # cap rather than one at a time, so a sustained burst doesn't pay
        # this cost on every single call.
        for stale_token in list(_issued_tokens.keys())[: len(_issued_tokens) - _MAX_ISSUED_TOKENS]:
            del _issued_tokens[stale_token]
    return token


def verify_token(settings: Settings, token: str, agent_id: str, nonce: int, intended_state_hash: str) -> bool:
    """
    True only if `token` was genuinely issued by THIS process for exactly
    this (agent_id, nonce, intended_state_hash) triple -- both a persisted-
    record lookup AND an HMAC recomputation must agree, so a caller can't
    satisfy this by guessing a value that merely happens to hash right
    (the persisted-record check) nor by replaying a token issued for
    different fields (the HMAC recomputation, keyed on the fields actually
    passed in, not just the persisted ones).
    """
    record = _issued_tokens.get(token)
    if record is None:
        return False
    if record.agent_id != agent_id or record.nonce != nonce or record.intended_state_hash != intended_state_hash:
        return False
    expected = _compute(settings, agent_id, nonce, intended_state_hash)
    return hmac.compare_digest(expected, token)
