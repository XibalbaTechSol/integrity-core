"""`integrity status` (folds the old `agent show` / `agent ais`) and `integrity doctor`.

Both fail closed: an Oracle or RPC that can't be reached is exit 3 ("unverified"), never a pass.
On-chain state is read from the v3 `AgentRegistry` (`singletons.AgentRegistry`); every test here
uses a fake web3/registry, so none of them touches a real chain.
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


class _Call:
    def __init__(self, value):
        self._value = value

    def call(self):
        if isinstance(self._value, Exception):
            raise self._value
        return self._value


class _Functions:
    def __init__(self, record=None, trust_config=None, attesters=()):
        self._record, self._trust_config, self._attesters = record, trust_config, {a.lower() for a in attesters}

    def resolveDID(self, did):
        return _Call(self._record)

    def trustConfig(self):
        return _Call(self._trust_config)

    def ATTESTER_ROLE(self):
        return _Call(b"\x01" * 32)

    def hasRole(self, role, account):
        return _Call(account.lower() in self._attesters)


class _Registry:
    def __init__(self, **kw):
        self.functions = _Functions(**kw)


ZERO32 = b"\x00" * 32
ZERO = "0x" + "00" * 20
ACTOR = "0x00000000000000000000000000000000000000cc"


def _record(pubkey=b"\x07" * 32, actor=ACTOR, registered_at=100, retired_at=0):
    return (pubkey, "0x" + "11" * 20, actor, ZERO32, "", registered_at, retired_at, 1)


@pytest.fixture(autouse=True)
def _no_real_chain_for_status(monkeypatch):
    """status reads AgentRegistry by default; never let a test reach the live local anvil."""
    from integrity_cli import status_cmd

    monkeypatch.setattr(status_cmd, "get_w3", lambda url: _W3(connected=False))


@pytest.fixture
def status_chain(monkeypatch, tmp_path):
    """Point status at a fake connected chain whose AgentRegistry returns `record`."""
    from integrity_cli import status_cmd

    def install(record):
        dep = tmp_path / "status-deployments.json"
        dep.write_text(json.dumps({"chainId": 31337, "singletons": {"AgentRegistry": REGISTRY}}))
        monkeypatch.setenv("DEPLOYMENTS_FILE", str(dep))
        monkeypatch.setattr(status_cmd, "get_w3", lambda url: _W3())
        monkeypatch.setattr(status_cmd, "agent_registry_contract", lambda w3, a: _Registry(record=record))

    return install


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
    # RPC unreachable (autouse fixture): on-chain rows are "unverified", never guessed; per-agent
    # trust is Phase 4. The Oracle answer still decides the exit code.
    assert doc["onchain"]["record"]["status"] == "unverified"
    assert doc["onchain"]["actor"]["status"] == "unverified"
    assert doc["onchain"]["trust"]["status"] == "pending"
    human = runner.invoke(app, ["status", DID])
    assert "87.5" in human.stdout and "tier 1" in human.stdout and "unverified" in human.stdout


@pytest.mark.parametrize(
    "record, want_record, want_actor",
    [
        (_record(), "present", "bound"),
        (_record(actor=ZERO), "present", "none"),
        (_record(retired_at=200), "retired", "bound"),
        (_record(pubkey=ZERO32, actor=ZERO, registered_at=0), "absent", "none"),
    ],
)
def test_status_reads_the_agent_registry(httpx_mock, status_chain, record, want_record, want_actor):
    status_chain(record)
    httpx_mock.add_response(url=f"{ORACLE}/v1/agent/{DID}", json=AGENT)
    httpx_mock.add_response(url=f"{ORACLE}/v1/agent/{DID}/ais", json={"ais": 1.0})
    result = runner.invoke(app, ["status", DID, "--json"])
    assert result.exit_code == 0, result.output  # an absent on-chain record is optional, not a no
    onchain = json.loads(result.stdout)["onchain"]
    assert onchain["record"]["status"] == want_record
    assert onchain["actor"]["status"] == want_actor
    if want_actor == "bound":
        assert onchain["actor"]["actor"] == ACTOR


def test_status_registry_read_error_is_unverified(httpx_mock, status_chain):
    status_chain(RuntimeError("execution reverted"))
    httpx_mock.add_response(url=f"{ORACLE}/v1/agent/{DID}", json=AGENT)
    httpx_mock.add_response(url=f"{ORACLE}/v1/agent/{DID}/ais", json={"ais": 1.0})
    onchain = json.loads(runner.invoke(app, ["status", DID, "--json"]).stdout)["onchain"]
    assert onchain["record"]["status"] == "unverified" and "read failed" in onchain["record"]["detail"]


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
REGISTRY = "0x00000000000000000000000000000000000000ac"
TRUST = "0x00000000000000000000000000000000000000ad"
ATTESTER = "0x00000000000000000000000000000000000000ae"
ALL_CODE = {XNS: b"\x60", POLICY: b"\x60", REGISTRY: b"\x60", TRUST: b"\x60"}


class _Eth:
    def __init__(self, chain_id, code):
        self.chain_id = chain_id
        self._code = code

    def get_code(self, address):
        return self._code.get(address.lower(), b"")


class _W3:
    def __init__(self, connected=True, chain_id=31337, code=None):
        self._connected = connected
        self.eth = _Eth(chain_id, code if code is not None else ALL_CODE)

    def is_connected(self):
        return self._connected


def _deployments(tmp_path, chain_id=31337, singletons=None):
    path = tmp_path / "deployments.json"
    path.write_text(json.dumps({
        "chainId": chain_id,
        "singletons": singletons if singletons is not None else {
            "XibalbaNameService": XNS, "PolicyRegistry": POLICY, "AgentRegistry": REGISTRY,
        },
    }))
    return str(path)


def _doctor(monkeypatch, tmp_path, *, w3=None, deployments=None, extra=(), registry=None):
    from integrity_cli import doctor_cmd

    monkeypatch.setattr(doctor_cmd, "get_w3", lambda url: w3 or _W3())
    monkeypatch.setattr(
        doctor_cmd, "agent_registry_contract",
        lambda w3_, address: registry or _Registry(trust_config=TRUST, attesters=(ATTESTER,)),
    )
    dep = deployments or _deployments(tmp_path)
    result = runner.invoke(app, ["doctor", "--deployments-file", dep, "--json", *extra])
    return result, (json.loads(result.stdout) if result.stdout.strip() else None)


def _by_name(doc):
    return {c["name"]: c for c in doc["checks"]}


def test_doctor_all_green(httpx_mock, monkeypatch, tmp_path):
    httpx_mock.add_response(url=f"{ORACLE}/healthz", text="ok")
    result, doc = _doctor(monkeypatch, tmp_path)
    assert result.exit_code == 0, result.output
    assert doc["schema"] == "integrity.cli.doctor.v1"
    checks = _by_name(doc)
    for name in ("oracle", "deployments", "rpc", "chain_id", "xns", "policy_registry", "agent_registry", "trust_config"):
        assert checks[name]["status"] == "pass", (name, checks[name])
    assert checks["trust_config"]["detail"] == TRUST
    # No attester address given: listed, but never a silent pass.
    assert checks["attester"]["status"] == "skipped"
    assert not any(c["status"] == "pending" for c in doc["checks"])


@pytest.mark.parametrize("attester, status, code", [(ATTESTER, "pass", 0), ("0x" + "99" * 20, "fail", 1)])
def test_doctor_attester_role(httpx_mock, monkeypatch, tmp_path, attester, status, code):
    httpx_mock.add_response(url=f"{ORACLE}/healthz", text="ok")
    result, doc = _doctor(monkeypatch, tmp_path, extra=("--attester", attester))
    assert result.exit_code == code, result.output
    assert _by_name(doc)["attester"]["status"] == status


def test_doctor_bad_attester_is_a_usage_error(monkeypatch, tmp_path):
    from integrity_cli import doctor_cmd

    monkeypatch.setattr(doctor_cmd, "get_w3", lambda url: _W3())
    dep = _deployments(tmp_path)
    assert runner.invoke(app, ["doctor", "--deployments-file", dep, "--attester", "nope"]).exit_code == 2


def test_doctor_without_agent_registry_is_a_no(httpx_mock, monkeypatch, tmp_path):
    httpx_mock.add_response(url=f"{ORACLE}/healthz", text="ok")
    dep = _deployments(tmp_path, singletons={"XibalbaNameService": XNS, "PolicyRegistry": POLICY})
    result, doc = _doctor(monkeypatch, tmp_path, deployments=dep)
    assert result.exit_code == 1
    checks = _by_name(doc)
    assert checks["agent_registry"]["status"] == "fail" and checks["trust_config"]["status"] == "fail"


@pytest.mark.parametrize("trust_config, code_map", [(ZERO, ALL_CODE), (TRUST, {XNS: b"\x60", POLICY: b"\x60", REGISTRY: b"\x60"})])
def test_doctor_trust_config_missing_is_a_no(httpx_mock, monkeypatch, tmp_path, trust_config, code_map):
    httpx_mock.add_response(url=f"{ORACLE}/healthz", text="ok")
    result, doc = _doctor(monkeypatch, tmp_path, w3=_W3(code=code_map), registry=_Registry(trust_config=trust_config))
    assert result.exit_code == 1
    assert _by_name(doc)["trust_config"]["status"] == "fail"


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
    for name in ("chain_id", "xns", "policy_registry", "agent_registry", "trust_config"):
        assert checks[name]["status"] == "unverified"


def test_doctor_chain_id_mismatch_is_a_no(httpx_mock, monkeypatch, tmp_path):
    httpx_mock.add_response(url=f"{ORACLE}/healthz", text="ok")
    result, doc = _doctor(monkeypatch, tmp_path, w3=_W3(chain_id=84532))
    assert result.exit_code == 1
    assert _by_name(doc)["chain_id"]["status"] == "fail"


def test_doctor_missing_contract_code_is_a_no(httpx_mock, monkeypatch, tmp_path):
    httpx_mock.add_response(url=f"{ORACLE}/healthz", text="ok")
    result, doc = _doctor(monkeypatch, tmp_path, w3=_W3(code={XNS: b"\x60", REGISTRY: b"\x60", TRUST: b"\x60"}))
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
