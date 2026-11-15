"""`integrity status` (folds the old `agent show` / `agent ais`) and `integrity doctor`.

Both fail closed: an Oracle or RPC that can't be reached is exit 3 ("unverified"), never a pass.
Checks that need `AgentRegistry` (registration v3 PR 3.2) report "pending", not pass or fail.
"""
from __future__ import annotations

import json

import httpx
import pytest
from typer.testing import CliRunner

from integrity_cli import identity
from integrity_cli.main import app

runner = CliRunner()
ORACLE = "http://localhost:8080"
DID = "did:integrity:abc"
AGENT = {"id": DID, "verification_tier": 1, "oracle_registered": True, "has_ed25519_key": True}


# --- status ----------------------------------------------------------------------------------

def test_status_for_an_explicit_did(httpx_mock):
    httpx_mock.add_response(url=f"{ORACLE}/v1/agent/{DID}", json=AGENT, is_reusable=True)
    httpx_mock.add_response(url=f"{ORACLE}/v1/agent/{DID}/ais", json={"ais": 87.5, "verification_tier": 1}, is_reusable=True)
    result = runner.invoke(app, ["status", DID, "--json"])
    assert result.exit_code == 0, result.output
    doc = json.loads(result.stdout)
    assert doc["schema"] == "integrity.cli.status.v1"
    assert doc["agent_id"] == DID and doc["registered"] is True and doc["verification_tier"] == 1
    assert doc["ais"]["ais"] == 87.5
    assert doc["record"] == AGENT
    for key in ("record", "actor", "trust"):
        assert doc["onchain"][key]["status"] == "pending"
    human = runner.invoke(app, ["status", DID])
    assert "87.5" in human.stdout and "tier 1" in human.stdout and "pending" in human.stdout


def test_status_defaults_to_the_local_identity(httpx_mock):
    runner.invoke(app, ["identity", "new"])
    did = identity.did_document("default")["id"]
    httpx_mock.add_response(url=f"{ORACLE}/v1/agent/{did}", json={**AGENT, "id": did})
    httpx_mock.add_response(url=f"{ORACLE}/v1/agent/{did}/ais", json={"ais": 10.0})
    doc = json.loads(runner.invoke(app, ["status", "--json"]).stdout)
    assert doc["agent_id"] == did and doc["identity"] == "default"


def test_status_without_identity_or_did_is_a_no():
    assert runner.invoke(app, ["status"]).exit_code == 1


def test_status_unregistered_is_a_no(httpx_mock):
    httpx_mock.add_response(url=f"{ORACLE}/v1/agent/{DID}", status_code=404, json={"detail": "not found"})
    result = runner.invoke(app, ["status", DID, "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["registered"] is False


@pytest.mark.parametrize("failure", ["connect", "503"])
def test_status_oracle_unreachable_is_unverified(httpx_mock, failure):
    if failure == "connect":
        httpx_mock.add_exception(httpx.ConnectError("refused"))
    else:
        httpx_mock.add_response(url=f"{ORACLE}/v1/agent/{DID}", status_code=503, text="cold start")
    assert runner.invoke(app, ["status", DID]).exit_code == 3


def test_status_ais_failure_does_not_hide_registration(httpx_mock):
    httpx_mock.add_response(url=f"{ORACLE}/v1/agent/{DID}", json=AGENT)
    httpx_mock.add_response(url=f"{ORACLE}/v1/agent/{DID}/ais", status_code=500, text="boom")
    result = runner.invoke(app, ["status", DID, "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["ais"] is None and "500" in doc["ais_error"]


# --- doctor ----------------------------------------------------------------------------------

XNS = "0x00000000000000000000000000000000000000aa"
POLICY = "0x00000000000000000000000000000000000000ab"


class _Eth:
    def __init__(self, chain_id, code):
        self.chain_id = chain_id
        self._code = code

    def get_code(self, address):
        return self._code.get(address.lower(), b"")


class _W3:
    def __init__(self, connected=True, chain_id=31337, code=None):
        self._connected = connected
        self.eth = _Eth(chain_id, code if code is not None else {XNS: b"\x60", POLICY: b"\x60"})

    def is_connected(self):
        return self._connected


def _deployments(tmp_path, chain_id=31337, singletons=None):
    path = tmp_path / "deployments.json"
    path.write_text(json.dumps({
        "chainId": chain_id,
        "singletons": singletons if singletons is not None else {"XibalbaNameService": XNS, "PolicyRegistry": POLICY},
    }))
    return str(path)


def _doctor(monkeypatch, tmp_path, *, w3=None, deployments=None, extra=()):
    from integrity_cli import doctor_cmd

    monkeypatch.setattr(doctor_cmd, "get_w3", lambda url: w3 or _W3())
    dep = deployments or _deployments(tmp_path)
    result = runner.invoke(app, ["doctor", "--deployments-file", dep, "--json", *extra])
    return result, (json.loads(result.stdout) if result.stdout.strip() else None)


def _by_name(doc):
    return {c["name"]: c for c in doc["checks"]}


def test_doctor_all_green_with_pending_v3_checks(httpx_mock, monkeypatch, tmp_path):
    httpx_mock.add_response(url=f"{ORACLE}/healthz", text="ok")
    result, doc = _doctor(monkeypatch, tmp_path)
    assert result.exit_code == 0, result.output
    assert doc["schema"] == "integrity.cli.doctor.v1"
    checks = _by_name(doc)
    for name in ("oracle", "deployments", "rpc", "chain_id", "xns", "policy_registry"):
        assert checks[name]["status"] == "pass", (name, checks[name])
    for name in ("agent_registry", "attester", "trust_config"):
        assert checks[name]["status"] == "pending" and "3.2" in checks[name]["detail"]


def test_doctor_oracle_down_fails_closed(httpx_mock, monkeypatch, tmp_path):
    httpx_mock.add_exception(httpx.ConnectError("refused"))
    result, doc = _doctor(monkeypatch, tmp_path)
    assert result.exit_code == 3
    assert _by_name(doc)["oracle"]["status"] == "unverified"


def test_doctor_rpc_down_is_unverified_and_dependent_checks_are_not_passed(httpx_mock, monkeypatch, tmp_path):
    httpx_mock.add_response(url=f"{ORACLE}/healthz", text="ok")
    result, doc = _doctor(monkeypatch, tmp_path, w3=_W3(connected=False))
    assert result.exit_code == 3
    checks = _by_name(doc)
    assert checks["rpc"]["status"] == "unverified"
    for name in ("chain_id", "xns", "policy_registry"):
        assert checks[name]["status"] == "unverified"


def test_doctor_chain_id_mismatch_is_a_no(httpx_mock, monkeypatch, tmp_path):
    httpx_mock.add_response(url=f"{ORACLE}/healthz", text="ok")
    result, doc = _doctor(monkeypatch, tmp_path, w3=_W3(chain_id=84532))
    assert result.exit_code == 1
    assert _by_name(doc)["chain_id"]["status"] == "fail"


def test_doctor_missing_contract_code_is_a_no(httpx_mock, monkeypatch, tmp_path):
    httpx_mock.add_response(url=f"{ORACLE}/healthz", text="ok")
    result, doc = _doctor(monkeypatch, tmp_path, w3=_W3(code={XNS: b"\x60"}))
    assert result.exit_code == 1
    assert _by_name(doc)["policy_registry"]["status"] == "fail"


def test_doctor_missing_deployments_file_is_a_no(httpx_mock, monkeypatch, tmp_path):
    httpx_mock.add_response(url=f"{ORACLE}/healthz", text="ok")
    result, doc = _doctor(monkeypatch, tmp_path, deployments=str(tmp_path / "missing.json"))
    assert result.exit_code == 1
    assert _by_name(doc)["deployments"]["status"] == "fail"


def test_doctor_pack_root_match(httpx_mock, monkeypatch, tmp_path):
    from integrity_cli import doctor_cmd
    from tests.test_policy_cmd import MANIFEST, SECTION

    from integrity_sdk.core.pack_onchain import compile_onchain

    pack = tmp_path / "demo"
    pack.mkdir()
    (pack / "pack.yaml").write_text(MANIFEST)
    (pack / "policy.rego").write_text("package integrity.pack\n")
    (pack / "onchain.json").write_text(json.dumps(SECTION))
    root = compile_onchain(SECTION).root

    httpx_mock.add_response(url=f"{ORACLE}/healthz", text="ok", is_reusable=True)
    monkeypatch.setattr(doctor_cmd, "graph_root_of", lambda w3, r, d: root)
    result, doc = _doctor(monkeypatch, tmp_path, extra=("--pack", str(pack)))
    assert result.exit_code == 0, result.output
    assert _by_name(doc)["pack_root"]["status"] == "pass"

    monkeypatch.setattr(doctor_cmd, "graph_root_of", lambda w3, r, d: b"\x00" * 32)
    result, doc = _doctor(monkeypatch, tmp_path, extra=("--pack", str(pack)))
    assert result.exit_code == 1
    assert _by_name(doc)["pack_root"]["status"] == "fail"
