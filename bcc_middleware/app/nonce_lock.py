"""
Process-wide, per-signer-address lock serializing "read nonce -> build ->
sign -> broadcast -> wait for receipt" across every chain-writing caller in
this service.

app/anchor.py and app/reputation.py can share the SAME private key on
today's single-operator testnet deployment (`REPUTATION_SIGNER_PRIVATE_KEY`
falls back to `ANCHOR_SIGNER_PRIVATE_KEY` -- see reputation.py's module
docstring), and they run on genuinely different OS threads: anchoring is
invoked (via `asyncio.to_thread`, see main.py) from a request-handling code
path, while the reputation sync loop runs via its own `asyncio.to_thread`
call from a periodic background task. web3.py's `get_transaction_count`
(reads the next nonce, defaults to the 'latest' MINED block -- it does not
see another thread's still-pending transaction) and `send_raw_transaction`
are separate network round-trips with no atomicity between them: two threads
can each read the same "next" nonce before either transaction is mined, then
both submit with that same nonce. One succeeds; the other fails with "nonce
too low" (or worse, silently replaces it if gas pricing works out that way).
PRODUCTION_GAPS.md §5.

The lock must be held for the FULL sequence, including the receipt wait --
not just the nonce read -- so that by the time a second caller for the same
address reads the nonce, the first caller's transaction is actually mined
and `get_transaction_count` correctly reflects it. This trades some
throughput (chain writes for the same key are fully serialized) for
correctness; this service's write volume (periodic score syncs, occasional
anchor flushes) makes that an acceptable cost, not a bottleneck.

**E13 (audit, 2026-08-02): the lock alone was not enough.** `nonce too low`
kept reproducing in production even with the full-sequence lock above,
because the RPC endpoint (`base-sepolia-rpc.publicnode.com`) is a
load-balanced, multi-backend-node hostname -- confirmed by the error shape
itself: `next nonce 329, tx nonce 328` means the node that received the
*broadcast* had already seen nonce 328 mined, while the node that answered
this process's *`get_transaction_count("latest")`* call (a separate HTTP
round-trip, likely a different backend node behind the same hostname) had
not caught up yet. The in-process lock correctly serializes this process's
own writes; it cannot make two different RPC backend nodes agree with each
other. `reserve_nonce`/`commit_nonce`/`invalidate_nonce` fix this by no
longer trusting a fresh `get_transaction_count` read on every call at all --
the nonce is read from chain once (cold start, or after a failure forces a
re-read) and tracked in-process thereafter, which is correct regardless of
how many nodes sit behind the RPC hostname.

That cache is only as good as the assumption that nothing else ever moves
this address's nonce outside this module -- true in production (this key
signs nothing but anchor/reputation writes), but false in the test suite,
where fixtures deploy/fund from the same well-known anvil account. Caught
by running the tests, not by trusting the assumption: two tests failed with
"nonce too low" after the cache went stale relative to fixture-driven
activity it couldn't see. `send_with_managed_nonce` below is the fix --
retries exactly once, invalidating and re-reading fresh, on a nonce
rejection from any source, so the cache self-heals instead of requiring the
"nothing else touches this address" assumption to hold forever.
"""

from __future__ import annotations

import threading
from typing import Callable

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()

#: Next nonce to use per (lowercased) signer address, cached in-process.
#: Mutated only by reserve_nonce/commit_nonce/invalidate_nonce below, and
#: only ever while the caller holds signer_lock(address) -- see each
#: function's docstring. Not independently locked: signer_lock already
#: serializes every access for a given address, by construction of how
#: anchor.py/reputation.py use this module.
_next_nonce: dict[str, int] = {}


def signer_lock(address: str) -> threading.Lock:
    """
    Returns the same `Lock` instance for the same (case-insensitive)
    address on every call, process-wide. Different addresses get
    independent locks, so callers using genuinely different signer keys
    never block each other.
    """
    key = address.lower()
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _locks[key] = lock
        return lock


def reserve_nonce(w3, address: str) -> int:
    """
    Returns the nonce to use for this signer's next transaction. Caller MUST
    hold `signer_lock(address)` for the duration of the build-sign-broadcast
    sequence that uses this value, and must call `commit_nonce` once the
    transaction is confirmed mined (even if reverted) or `invalidate_nonce`
    on any failure where that's not known (E13) -- see module docstring.

    Sourced from a live `get_transaction_count("latest")` read only the
    first time this address is seen (or after `invalidate_nonce`); every
    call after that returns the in-process tracked value, never re-reading
    "latest" from the RPC.
    """
    key = address.lower()
    if key not in _next_nonce:
        _next_nonce[key] = w3.eth.get_transaction_count(address)
    return _next_nonce[key]


def commit_nonce(address: str) -> None:
    """Call once the transaction that used `reserve_nonce`'s value is
    confirmed mined -- reverted-on-chain counts, since the nonce was still
    consumed either way. Advances the in-process counter by one."""
    key = address.lower()
    _next_nonce[key] = _next_nonce.get(key, 0) + 1


def invalidate_nonce(address: str) -> None:
    """Call on any failure where it isn't known whether the reserved nonce
    was actually consumed on-chain (build/sign/broadcast error, or a
    receipt-wait timeout that could mean 'still pending' rather than 'never
    sent'). Drops the cached value so the next `reserve_nonce` call for this
    address re-reads from chain instead of guessing -- safer to pay for one
    extra RPC round-trip than to silently skip or reuse a nonce."""
    _next_nonce.pop(address.lower(), None)


def send_with_managed_nonce(w3, account, build_tx: Callable[[int], dict], timeout: int = 30):
    """
    Builds (via `build_tx(nonce)`), signs, broadcasts, and waits for receipt,
    using this module's in-process nonce cache instead of a fresh
    `get_transaction_count` read on every call (E13). Caller MUST hold
    `signer_lock(account.address)` for the duration of this call.

    Retries exactly once if the network rejects the broadcast as a nonce
    error, invalidating the cache first -- this is what makes the cache safe
    even when something the cache didn't already fix (a load-balanced RPC's
    stale read) is instead something it can't see at all (another process,
    or in tests, a fixture, moving the same address's nonce out from under
    it): either way, one fresh read and retry recovers.

    Pads `build_tx`'s gas estimate by 30% before signing. Found empirically
    (E13 follow-up): `build_transaction`'s automatic `eth_estimateGas` is a
    point-in-time snapshot, and on a busy chain (many transactions landing
    close together -- exactly what a nonce-managing retry loop plus a full
    test suite produces) the estimate can be for a cheaper state (e.g. a
    warm storage slot) than the one the transaction actually executes
    against a block later, producing a real `OutOfGas` revert on an
    otherwise-correct, correctly-nonced transaction. A fixed percentage
    margin is cheap (unused gas is refunded) and removes the dependency on
    estimate/execution happening against identical state.

    Returns `(tx_hash, receipt)`. Raises on a second consecutive failure, or
    on any non-nonce failure.
    """
    from web3.exceptions import Web3Exception

    last_exc: Exception | None = None
    for attempt in range(2):
        nonce = reserve_nonce(w3, account.address)
        try:
            tx = build_tx(nonce)
            tx["gas"] = int(tx["gas"] * 1.3)
            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
        except (Web3Exception, ValueError) as exc:
            invalidate_nonce(account.address)
            last_exc = exc
            if attempt == 0 and "nonce too low" in str(exc).lower():
                continue
            raise
        commit_nonce(account.address)
        return tx_hash, receipt
    raise last_exc  # pragma: no cover -- unreachable, loop always returns or raises
