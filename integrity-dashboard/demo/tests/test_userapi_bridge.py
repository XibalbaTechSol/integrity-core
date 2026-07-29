"""
`userapi_bridge.report_status` against a REAL local HTTP server standing in
for integrity-userapi (same pattern as integrity-userapi's own
`tests/conftest.py::_FakeOracleServer` -- a real socket + real `requests`
call, not a mocked function).
"""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from integrity_demo import userapi_bridge


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _RecordingUserapiServer:
    def __init__(self, status_code: int = 200) -> None:
        self.port = _free_port()
        self.status_code = status_code
        self.requests: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_PATCH(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length)) if length else {}
                outer.requests.append(
                    {"path": self.path, "headers": dict(self.headers), "body": body}
                )
                self.send_response(outer.status_code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, format: str, *args) -> None:  # noqa: A002
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def userapi_server():
    server = _RecordingUserapiServer()
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ("USERAPI_URL", "USERAPI_TOKEN", "USERAPI_RUN_ID"):
        monkeypatch.delenv(key, raising=False)


def test_report_status_is_a_noop_when_env_vars_are_unset(userapi_server) -> None:
    userapi_bridge.report_status("running")
    assert userapi_server.requests == []


def test_report_status_is_a_noop_when_only_some_env_vars_set(monkeypatch, userapi_server) -> None:
    monkeypatch.setenv("USERAPI_URL", userapi_server.url)
    monkeypatch.setenv("USERAPI_TOKEN", "some-jwt")
    # USERAPI_RUN_ID deliberately left unset.
    userapi_bridge.report_status("running")
    assert userapi_server.requests == []


def test_report_status_patches_the_real_run_with_a_bearer_token(monkeypatch, userapi_server) -> None:
    monkeypatch.setenv("USERAPI_URL", userapi_server.url)
    monkeypatch.setenv("USERAPI_TOKEN", "a-jwt-token")
    monkeypatch.setenv("USERAPI_RUN_ID", "abc-123")

    userapi_bridge.report_status("completed", {"agents_registered": ["a", "b"]})

    assert len(userapi_server.requests) == 1
    req = userapi_server.requests[0]
    assert req["path"] == "/demo/runs/abc-123"
    assert req["headers"]["Authorization"] == "Bearer a-jwt-token"
    assert req["body"] == {"status": "completed", "result_summary": {"agents_registered": ["a", "b"]}}


def test_report_status_uses_api_key_header_for_uak_prefixed_tokens(monkeypatch, userapi_server) -> None:
    monkeypatch.setenv("USERAPI_URL", userapi_server.url)
    monkeypatch.setenv("USERAPI_TOKEN", "uak_some-api-key")
    monkeypatch.setenv("USERAPI_RUN_ID", "abc-123")

    userapi_bridge.report_status("running")

    req = userapi_server.requests[0]
    assert req["headers"]["X-API-Key"] == "uak_some-api-key"
    assert "Authorization" not in req["headers"]


def test_report_status_swallows_http_errors(monkeypatch) -> None:
    server = _RecordingUserapiServer(status_code=404)
    try:
        monkeypatch.setenv("USERAPI_URL", server.url)
        monkeypatch.setenv("USERAPI_TOKEN", "a-jwt-token")
        monkeypatch.setenv("USERAPI_RUN_ID", "does-not-exist")

        # Must not raise, even though the server responds 404.
        userapi_bridge.report_status("failed", {"error": "boom"})
    finally:
        server.stop()


def test_report_status_swallows_connection_errors(monkeypatch) -> None:
    monkeypatch.setenv("USERAPI_URL", "http://127.0.0.1:1")  # nothing listens here
    monkeypatch.setenv("USERAPI_TOKEN", "a-jwt-token")
    monkeypatch.setenv("USERAPI_RUN_ID", "abc-123")

    # Must not raise even though the connection itself fails.
    userapi_bridge.report_status("running")
