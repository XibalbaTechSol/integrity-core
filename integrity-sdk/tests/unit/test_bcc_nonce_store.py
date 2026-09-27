from __future__ import annotations

import multiprocessing
from pathlib import Path

import pytest

from integrity_sdk.bcc import NonceStore


def _allocate_nonces(path: str, count: int, output: multiprocessing.Queue) -> None:
    store = NonceStore(Path(path))
    output.put([store.next() for _ in range(count)])


def test_nonce_store_allocates_unique_values_across_processes(tmp_path):
    path = tmp_path / "bcc_nonce"
    output = multiprocessing.Queue()
    workers = [
        multiprocessing.Process(target=_allocate_nonces, args=(str(path), 40, output))
        for _ in range(4)
    ]
    for worker in workers:
        worker.start()
    values = [value for _ in workers for value in output.get(timeout=10)]
    for worker in workers:
        worker.join(timeout=10)
        assert worker.exitcode == 0

    assert len(set(values)) == 160
    assert min(values) > 0
    assert int(path.read_text()) == max(values)


def test_nonce_store_uses_epoch_floor_and_remains_monotonic(tmp_path, monkeypatch):
    path = tmp_path / "bcc_nonce"
    monkeypatch.setattr("integrity_sdk.bcc.time.time_ns", lambda: 1_800_000_000_000_000_000)
    store = NonceStore(path)

    first = store.next()
    second = store.next()

    assert first == 1_800_000_000_000
    assert second == first + 1


def test_nonce_store_refuses_corrupt_counter_instead_of_resetting(tmp_path):
    path = tmp_path / "bcc_nonce"
    path.write_text("not-a-number")

    with pytest.raises(RuntimeError, match="refusing to reset"):
        NonceStore(path).next()

    assert path.read_text() == "not-a-number"
