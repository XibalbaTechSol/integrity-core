"""Concurrent telemetry senders sharing one agent DID must not collide on the Oracle nonce.

The Oracle accepts a telemetry batch only when ``nonce > agents.last_nonce`` (checked under
``SELECT ... FOR UPDATE``, integrity-oracle ``db.rs``). Claude Code runs every PostToolUse hook
in a fresh process, and parallel tool calls overlap those processes: each one GETs the same
``last_nonce = L`` and POSTs ``L + 1``, so all but one get a 409. Unique nonces alone would not
fix it either: if A takes ``L + 1`` and B takes ``L + 2`` but B's POST lands first, A's is
rejected. Allocation and send must be atomic across processes.

The stub below enforces the Oracle's rule, delays each request so the processes really overlap,
and the test runs real OS processes (not threads), because the race is between processes.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

AGENT = "did:integrity:nonce-race"
N_PROCS = 6

_CHILD = r"""
import os, sys
from integrity_sdk.client import IntegrityClient
c = IntegrityClient(
    sys.argv[1], oracle_url=sys.argv[2], auto_flush=False, background_flush=False,
    enable_otel_export=False,
)
c.log_telemetry({"text_output": "parallel hook " + sys.argv[3]})
ok = c.flush_telemetry()
print("OK" if ok else "FAIL")
"""


class _StubOracle:
    def __init__(self) -> None:
        self.last_nonce = 0
        self.accepted: list[int] = []
        self.rejected: list[int] = []
        self._lock = threading.Lock()
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # quiet
                pass

            def _send(self, code: int, body: dict) -> None:
                raw = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                time.sleep(0.15)  # every process reads last_nonce before any POST lands
                with stub._lock:
                    last = stub.last_nonce
                self._send(200, {"id": AGENT, "last_nonce": last, "oracle_registered": True})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                time.sleep(0.05)
                with stub._lock:  # the Oracle's FOR UPDATE + strict-greater check
                    nonce = body["nonce"]
                    if nonce <= stub.last_nonce:
                        stub.rejected.append(nonce)
                        self._send(409, {"error": "nonce replay", "last_seen": stub.last_nonce})
                        return
                    stub.last_nonce = nonce
                    stub.accepted.append(nonce)
                self._send(200, {"accepted": True, "nonce": nonce})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def test_parallel_hook_processes_never_replay_a_nonce(tmp_path):
    oracle = _StubOracle()
    try:
        env = {**os.environ, "INTEGRITY_NONCE_LOCK_DIR": str(tmp_path / "locks")}
        for name in ("HERMES_HOME", "CODEX_HOME", "CLAUDE_CONFIG_DIR", "INTEGRITY_PROFILE_ROOT"):
            env.pop(name, None)
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", _CHILD, AGENT, oracle.url, str(i)],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            for i in range(N_PROCS)
        ]
        results = [p.communicate(timeout=120) for p in procs]
    finally:
        oracle.close()

    outs = [out.strip() for out, _ in results]
    assert oracle.rejected == [], f"nonce replays: {oracle.rejected} (stderr: {[e[-400:] for _, e in results]})"
    assert outs == ["OK"] * N_PROCS, outs
    assert len(oracle.accepted) == N_PROCS
    assert oracle.accepted == sorted(set(oracle.accepted))  # strictly increasing, no duplicates
