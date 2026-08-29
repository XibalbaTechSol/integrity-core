"""Shared fixtures for the unit suite.

`captured_posts`, `_FakeResponse` and the nonce-sync stub previously lived only inside
`test_client.py`. They are lifted here so other modules (e.g. the F2/F3 reliability tests)
can exercise the client's flush path without duplicating the plumbing or, worse, making real
network calls to localhost:8080 and eating the timeout.

`test_client.py` keeps its own copies: a module-level fixture takes precedence over a
conftest one, so its long-standing definitions and comments stay authoritative for that file
rather than being changed remotely by this file.
"""

from __future__ import annotations

import pytest


class _FakeResponse:
    def __init__(self, status_ok: bool = True, payload: dict | None = None, status_code: int = 200):
        self._status_ok = status_ok
        self._payload = payload or {}
        self.status_code = status_code

    def raise_for_status(self):
        if not self._status_ok:
            import requests

            err = requests.HTTPError("simulated oracle error")
            err.response = self
            raise err

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _no_real_nonce_sync_network_calls(monkeypatch):
    """`flush_telemetry` does a real GET to sync the nonce before a client's first flush.

    Simulating "oracle unreachable" reproduces exactly what `_sync_nonce_from_oracle` does on
    failure (mark synced, leave `_nonce` alone), so local-nonce assertions stay valid — and no
    test pays a real network timeout.
    """
    import requests

    monkeypatch.setattr(
        "integrity_sdk.client.requests.get",
        lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("no oracle in this test")),
    )


@pytest.fixture
def captured_posts(monkeypatch):
    """Collects every telemetry POST instead of sending it.

    Thread-safe by necessity: the background flusher (F3) posts from its own thread, so a
    plain list append could race with the assertions reading it.
    """
    import threading

    posts: list[dict] = []
    lock = threading.Lock()

    class _ThreadSafeList(list):
        def append(self, item):  # type: ignore[override]
            with lock:
                super().append(item)

    posts = _ThreadSafeList()

    def _fake_post(url, json=None, timeout=None):
        posts.append({"url": url, "json": json})
        return _FakeResponse(status_ok=True)

    monkeypatch.setattr("integrity_sdk.client.requests.post", _fake_post)
    return posts
