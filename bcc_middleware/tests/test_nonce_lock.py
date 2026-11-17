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

from app.nonce_lock import signer_lock
from app.reputation import post_checkpoint
from tests.helpers import bind_actor, chain_settings, fixture_contract, new_agent


def test_signer_lock_returns_the_same_instance_for_the_same_address():
    addr = "0xAbCdEf0000000000000000000000000000AbCd"
    assert signer_lock(addr) is signer_lock(addr)
    # Case-insensitive: EVM addresses are the same account regardless of checksum casing.
    assert signer_lock(addr) is signer_lock(addr.lower())


def test_signer_lock_returns_different_instances_for_different_addresses():
    a = "0x1111111111111111111111111111111111111111"[:42]
    b = "0x2222222222222222222222222222222222222222"[:42]
    assert signer_lock(a) is not signer_lock(b)


def test_concurrent_post_checkpoint_with_shared_signer_key_never_collides_on_nonce(anvil_chain):
    """
    Real regression test: N threads, same signer key (mirroring anchor.py and
    reputation.py sharing ANCHOR_SIGNER_PRIVATE_KEY on today's single-operator
    deployment), each posting a checkpoint for a DIFFERENT agent concurrently.
    Without app/nonce_lock.py's serialization, two threads reading
    `get_transaction_count` before either transaction is mined can submit the
    same nonce -- one succeeds, the rest fail with "nonce too low"/reverted
    submission. Every one of these must succeed.
    """
    settings = chain_settings(anvil_chain, anchor_signer_private_key=anvil_chain["signer_private_key"])
    agents = []
    for _ in range(8):
        agent_id, _key = new_agent()
        actor = Account.create().address
        bind_actor(anvil_chain, agent_id, actor)
        agents.append(actor)
    results: list = [None] * len(agents)

    def _push(i: int, actor: str) -> None:
        results[i] = post_checkpoint(settings, anvil_chain["ais_registry_address"], actor, 5000 + i, 1_000_000)

    threads = [threading.Thread(target=_push, args=(i, addr)) for i, addr in enumerate(agents)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    failures = [(agents[i], r.detail) for i, r in enumerate(results) if r is None or not r.submitted]
    assert not failures, f"one or more concurrent posts failed (nonce race not actually fixed): {failures}"

    ais = fixture_contract(anvil_chain, "ais_registry")
    for i, actor in enumerate(agents):
        assert ais.functions.latest(actor).call()[0] == 5000 + i
