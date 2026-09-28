"""SDK core OPA client against a real OPA server (skipped when no `opa` binary is available).

The point is real policy output, not a mock: Shield's old policy test mocked
OPA's response, which is how "no rule matched" came to mean deny without
anyone noticing. Here a real `opa run --server` evaluates a signed pack.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

from integrity_sdk.core import decision as d
from integrity_sdk.core import packs
from integrity_sdk.core.opa import OpaClient, OpaError
from integrity_sdk.did import Keypair, public_key_multibase

OPA = shutil.which("opa") or (str(Path.home() / ".local/bin/opa") if (Path.home() / ".local/bin/opa").exists() else None)
pytestmark = pytest.mark.skipif(OPA is None, reason="opa binary not installed (scripts/install_toolchain.sh)")

MANIFEST = """\
pack_format: integrity.pack/1
name: hipaa
version: 0.1.0
kernel_range: ">=1.0.0 <2.0.0"
decision_contract: integrity.decision/1
entrypoint: data.integrity.pack.decision
event_classes:
  agent.tool_call: {no_match: deny}
  device.sensor: {no_match: log_only}
"""
POLICY = """\
package integrity.pack

decision := {"decision": "deny", "reason_code": "NO_BAA", "controls": ["HIPAA-164.502(b)"]} if {
    input.touches_phi
    not input.baa_active
}

decision := {"decision": "permit", "reason_code": "BAA_ACTIVE"} if {
    input.touches_phi
    input.baa_active
}
"""


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def opa_url():
    port = _free_port()
    process = subprocess.Popen(
        [OPA, "run", "--server", "--addr", f"127.0.0.1:{port}", "--log-level", "error"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + 15
    while True:
        try:
            opener.open(url + "/health", timeout=1).read()
            break
        except OSError:
            if time.monotonic() > deadline:
                process.kill()
                pytest.fail("opa server did not start")
            time.sleep(0.1)
    yield url
    process.terminate()
    process.wait(timeout=10)


def _signed_pack(root: Path, policy: str, signer: Keypair) -> packs.LoadedPack:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pack.yaml").write_text(MANIFEST)
    (root / "policy.rego").write_text(policy)
    packs.sign_pack(root, signer)
    return packs.load_pack(root, trusted_signers=[public_key_multibase(signer.public_bytes())])


@pytest.fixture
def signer():
    return Keypair.generate()


def test_real_opa_decisions_follow_the_contract(opa_url, tmp_path, signer):
    pack = _signed_pack(tmp_path / "hipaa", POLICY, signer)
    client = OpaClient(opa_url)
    client.install(pack)
    assert client.installed_pack_hash == pack.pack_hash

    denied = client.decide(pack, "agent.tool_call", {"touches_phi": True, "baa_active": False})
    assert (denied.decision, denied.reason_code, denied.controls, denied.blocks) == (
        "deny", "NO_BAA", ("HIPAA-164.502(b)",), True
    )
    permitted = client.decide(pack, "agent.tool_call", {"touches_phi": True, "baa_active": True})
    assert (permitted.decision, permitted.blocks) == ("permit", False)

    # No rule matches: the pack's per-class default, not "deny because nothing allowed it".
    unmatched_tool = client.decide(pack, "agent.tool_call", {"touches_phi": False})
    unmatched_sensor = client.decide(pack, "device.sensor", {"touches_phi": False})
    assert (unmatched_tool.decision, unmatched_tool.reason_code) == ("deny", d.REASON_NO_MATCH)
    assert (unmatched_sensor.decision, unmatched_sensor.blocks) == ("log_only", False)

    shadow = client.decide(pack, "agent.tool_call", {"touches_phi": True, "baa_active": False}, mode=d.SHADOW)
    assert shadow.decision == "deny" and not shadow.blocks


def test_install_replaces_the_previous_pack_and_evaluation_is_pinned_to_it(opa_url, tmp_path, signer):
    client = OpaClient(opa_url)
    first = _signed_pack(tmp_path / "first", POLICY, signer)
    second = _signed_pack(
        tmp_path / "second",
        'package integrity.pack\n\ndecision := {"decision": "permit", "reason_code": "OPEN"} if { true }\n',
        signer,
    )
    client.install(first)
    client.install(second)  # would fail to compile if the first pack's modules were still loaded
    assert client.decide(second, "agent.tool_call", {}).reason_code == "OPEN"
    stale = client.decide(first, "agent.tool_call", {"touches_phi": True, "baa_active": True})
    assert (stale.decision, stale.reason_code) == ("deny", d.REASON_EVALUATOR_ERROR)


def test_invalid_rego_is_refused_and_leaves_nothing_enforceable(opa_url, tmp_path, signer):
    client = OpaClient(opa_url)
    broken = _signed_pack(tmp_path / "broken", "package integrity.pack\n\ndecision := {\n", signer)
    with pytest.raises(OpaError) as excinfo:
        client.install(broken)
    assert excinfo.value.code == "OPA_HTTP_ERROR"
    assert client.installed_pack_hash is None
    assert client.decide(broken, "device.sensor", {}).reason_code == d.REASON_EVALUATOR_ERROR


def test_unreachable_opa_denies(tmp_path, signer):
    pack = _signed_pack(tmp_path / "hipaa", POLICY, signer)
    client = OpaClient(f"http://127.0.0.1:{_free_port()}", timeout_seconds=0.5)
    with pytest.raises(OpaError) as excinfo:
        client.install(pack)
    assert excinfo.value.code == "OPA_UNAVAILABLE"
    decided = client.decide(pack, "device.sensor", {})
    assert (decided.decision, decided.reason_code, decided.blocks) == ("deny", d.REASON_EVALUATOR_ERROR, True)
    assert client.decide(None, "device.sensor", {}).reason_code == d.REASON_NO_PACK


def test_opa_proxy_environment_is_ignored(opa_url, tmp_path, signer, monkeypatch):
    # A sidecar query must never be sent to an egress proxy.
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    pack = _signed_pack(tmp_path / "hipaa", POLICY, signer)
    client = OpaClient(opa_url)
    client.install(pack)
    assert client.decide(pack, "agent.tool_call", {"touches_phi": True, "baa_active": True}).decision == "permit"
    assert os.environ["HTTP_PROXY"]  # still set: the client ignored it rather than it being absent
