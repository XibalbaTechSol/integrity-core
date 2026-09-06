"""Regression coverage for time-bounded Merkle anchoring.

Low-traffic agents must not wait forever for ``BCC_MERKLE_BATCH_SIZE``
approvals. The periodic cycle flushes a partial batch, serializes competing
flush triggers, and cleans up safely when lifespan exits exceptionally.
"""

from __future__ import annotations

import pytest

import app.main as main_module
from app.anchor import AnchorResult
from app.config import Settings
from app.merkle import MerkleBatcher
from app.schemas import BCCCommitment
from tests.helpers import new_agent, sign_commitment


def _commitment(*, nonce: int = 1) -> BCCCommitment:
    agent_id, private_key = new_agent()
    return BCCCommitment(
        **sign_commitment(
            private_key,
            agent_id=agent_id,
            intent_type="payment",
            nonce=nonce,
        )
    )


def test_anchor_interval_must_be_positive():
    with pytest.raises(ValueError, match="merkle anchor interval"):
        Settings(merkle_anchor_interval_seconds=0)


def test_periodic_cycle_flushes_a_partial_batch(monkeypatch):
    local_batcher = MerkleBatcher(batch_size=8)
    commitment = _commitment()
    local_batcher.add(commitment)
    monkeypatch.setattr(main_module, "batcher", local_batcher)

    anchored = []

    def _anchor(_settings, leaves):
        anchored.extend(leaves)
        return {
            commitment.agent_id: AnchorResult(
                submitted=True,
                detail="anchored",
                tx_hash="0xabc",
                root=b"\x11" * 32,
            )
        }

    monkeypatch.setattr(main_module.anchor_module, "anchor_batch_per_agent", _anchor)
    monkeypatch.setattr(main_module, "_report_anchor_events", lambda *_args: None)

    flushed = main_module._flush_and_anchor(Settings(), require_full=False)

    assert flushed is not None
    leaves, _results = flushed
    assert len(leaves) == 1
    assert [leaf.commitment.agent_id for leaf in anchored] == [commitment.agent_id]
    assert local_batcher.pending_count == 0


def test_concurrent_flush_cycles_are_single_flight(monkeypatch):
    import threading

    local_batcher = MerkleBatcher(batch_size=1)
    first = _commitment()
    second = _commitment(nonce=2)
    local_batcher.add(first)
    monkeypatch.setattr(main_module, "batcher", local_batcher)

    first_entered = threading.Event()
    release_first = threading.Event()
    calls: list[list[str]] = []

    def _anchor(_settings, leaves):
        calls.append([leaf.commitment.agent_id for leaf in leaves])
        if len(calls) == 1:
            first_entered.set()
            assert release_first.wait(timeout=2)
        return {
            leaf.commitment.agent_id: AnchorResult(submitted=False, detail="test")
            for leaf in leaves
        }

    monkeypatch.setattr(main_module.anchor_module, "anchor_batch_per_agent", _anchor)
    monkeypatch.setattr(main_module, "_report_anchor_events", lambda *_args: None)

    first_thread = threading.Thread(
        target=main_module._flush_and_anchor,
        args=(Settings(),),
        kwargs={"require_full": False},
    )
    first_thread.start()
    assert first_entered.wait(timeout=2)
    local_batcher.add(second)

    second_thread = threading.Thread(
        target=main_module._flush_and_anchor,
        args=(Settings(),),
        kwargs={"require_full": False},
    )
    second_thread.start()
    assert len(calls) == 1

    release_first.set()
    first_thread.join(timeout=2)
    second_thread.join(timeout=2)
    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert calls == [[first.agent_id], [second.agent_id]]


@pytest.mark.asyncio
async def test_lifespan_cleans_up_anchor_task_after_exception(monkeypatch):
    settings = Settings(
        score_sync_enabled=False,
        spool_enabled=False,
        merkle_anchor_enabled=True,
        merkle_anchor_interval_seconds=60,
    )
    monkeypatch.setattr(main_module, "default_settings", settings)

    with pytest.raises(RuntimeError, match="startup body failed"):
        async with main_module.lifespan(main_module.app):
            raise RuntimeError("startup body failed")

    assert main_module._anchor_flush_task is None


@pytest.mark.asyncio
async def test_periodic_loop_waits_for_inflight_flush_during_cancellation(monkeypatch):
    import asyncio

    real_sleep = asyncio.sleep
    settings = Settings(merkle_anchor_interval_seconds=17)
    flush_started = asyncio.Event()
    release_flush = asyncio.Event()

    async def _sleep(_seconds):
        return None

    async def _to_thread(_func, *_args, **_kwargs):
        flush_started.set()
        await release_flush.wait()

    monkeypatch.setattr(main_module.asyncio, "sleep", _sleep)
    monkeypatch.setattr(main_module.asyncio, "to_thread", _to_thread)

    task = asyncio.create_task(main_module._anchor_flush_loop(settings))
    await flush_started.wait()
    task.cancel()
    await real_sleep(0)
    assert not task.done()

    release_flush.set()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_periodic_loop_waits_for_interval_then_flushes(monkeypatch):
    settings = Settings(merkle_anchor_interval_seconds=17)
    calls = []
    sleep_calls = 0

    async def _sleep(seconds):
        nonlocal sleep_calls
        sleep_calls += 1
        assert seconds == 17
        if sleep_calls == 2:
            raise asyncio.CancelledError

    async def _to_thread(func, *args, **kwargs):
        calls.append((func, args, kwargs))
        return 0

    import asyncio

    monkeypatch.setattr(main_module.asyncio, "sleep", _sleep)
    monkeypatch.setattr(main_module.asyncio, "to_thread", _to_thread)

    with pytest.raises(asyncio.CancelledError):
        await main_module._anchor_flush_loop(settings)

    assert calls == [
        (main_module._flush_and_anchor, (settings,), {"require_full": False})
    ]
