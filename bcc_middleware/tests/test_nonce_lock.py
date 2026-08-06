"""
Tests for app/nonce_lock.py and the cross-module nonce race it fixes
(PRODUCTION_GAPS.md §5): app/anchor.py and app/reputation.py can share the
same signer key (REPUTATION_SIGNER_PRIVATE_KEY falls back to
ANCHOR_SIGNER_PRIVATE_KEY) and run on different OS threads, so unguarded
concurrent `get_transaction_count` -> `send_raw_transaction` calls can race
onto the same nonce.
"""

from __future__ import annotations

import threading

from eth_account import Account

from app.config import Settings
from app.nonce_lock import signer_lock
from app.reputation import push_score


def test_signer_lock_returns_the_same_instance_for_the_same_address():
    addr = "0xAbCdEf0000000000000000000000000000AbCd"
    assert signer_lock(addr) is signer_lock(addr)
    # Case-insensitive: EVM addresses are the same account regardless of checksum casing.
    assert signer_lock(addr) is signer_lock(addr.lower())


def test_signer_lock_returns_different_instances_for_different_addresses():
    a = "0x1111111111111111111111111111111111111111"[:42]
    b = "0x2222222222222222222222222222222222222222"[:42]
    assert signer_lock(a) is not signer_lock(b)


def test_concurrent_push_score_with_shared_signer_key_never_collides_on_nonce(anvil_chain):
    """
    Real regression test: N threads, same signer key (mirroring anchor.py and
    reputation.py sharing ANCHOR_SIGNER_PRIVATE_KEY on today's single-operator
    deployment), each pushing a score for a DIFFERENT agent concurrently.
    Without app/nonce_lock.py's serialization, two threads reading
    `get_transaction_count` before either transaction is mined can submit the
    same nonce -- one succeeds, the rest fail with "nonce too low"/reverted
    submission. Every one of these must succeed.
    """
    settings = Settings(rpc_url=anvil_chain["rpc_url"], anchor_signer_private_key=anvil_chain["signer_private_key"])
    agents = [Account.create().address for _ in range(8)]
    results: list = [None] * len(agents)

    def _push(i: int, agent_address: str) -> None:
        results[i] = push_score(settings, anvil_chain["reputation_registry_address"], agent_address, 500 + i)

    threads = [threading.Thread(target=_push, args=(i, addr)) for i, addr in enumerate(agents)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    failures = [(agents[i], r.detail) for i, r in enumerate(results) if r is None or not r.submitted]
    assert not failures, f"one or more concurrent pushes failed (nonce race not actually fixed): {failures}"

    w3 = anvil_chain["w3"]
    contract = w3.eth.contract(address=anvil_chain["reputation_registry_address"], abi=anvil_chain["reputation_registry_abi"])
    for i, agent_address in enumerate(agents):
        assert contract.functions.baseScoreOf(agent_address).call() == 500 + i
