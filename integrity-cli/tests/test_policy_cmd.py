"""`integrity policy ...`: a pack's on-chain map, compiled and checked against PolicyRegistry.

Read-only except `publish`, which only PRINTS the governance transaction (decision D5): the CLI
never signs a root change.
"""
from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from integrity_cli.main import app
from integrity_sdk.core.pack_onchain import compile_onchain, edges_for_call, proof_for
from integrity_sdk.policy_registry import SET_GRAPH_ROOT_SIGNATURE

runner = CliRunner()

TOKEN = "0x00000000000000000000000000000000000000Ca"
REGISTRY = "0x00000000000000000000000000000000000000Ab"
MANIFEST = """\
pack_format: integrity.pack/1
name: demo
version: 0.1.0
kernel_range: ">=1.0.0 <2.0.0"
decision_contract: integrity.decision/1
entrypoint: data.integrity.pack.decision
event_classes:
  agent.tool_call: {no_match: deny}
"""
SECTION = {
    "domain": "health",
    "edges": [
        {"target": TOKEN, "selector": "0xa9059cbb", "risk_weight_bps": 500},
        {"target": TOKEN, "selector": "0x095ea7b3", "risk_weight_bps": 200},
        {"target": TOKEN, "selector": "0x095ea7b3", "risk_weight_bps": 900, "to_node": "big-approve"},
    ],
}


@pytest.fixture
def pack(tmp_path):
    root = tmp_path / "demo"
    root.mkdir()
    (root / "pack.yaml").write_text(MANIFEST)
    (root / "policy.rego").write_text('package integrity.pack\n\ndecision := {"decision": "permit"}\n')
    (root / "onchain.json").write_text(json.dumps(SECTION))
    return root


@pytest.fixture
def policy():
    return compile_onchain(SECTION)


def _json(result):
    assert result.stdout, result.output
    return json.loads(result.stdout)


def test_compile_reports_the_root_governance_publishes(pack, policy, tmp_path):
    result = runner.invoke(app, ["policy", "compile", str(pack), "--json"])
    assert result.exit_code == 0, result.output
    doc = _json(result)
    assert doc["schema"] == "integrity.cli.policy.compile.v1"
    assert doc["root"] == "0x" + policy.root.hex()
    assert doc["domain"] == "health" and doc["domain_id"] == "0x" + policy.domain_id.hex()
    assert doc["pack_hash"].startswith("sha256:")
    assert len(doc["edges"]) == 3 and len(doc["leaves"]) == 3

    out = tmp_path / "onchain.compiled.json"
    assert runner.invoke(app, ["policy", "compile", str(pack), "--out", str(out)]).exit_code == 0
    assert json.loads(out.read_text())["root"] == doc["root"]


def test_compile_without_an_onchain_section_is_a_no(pack):
    (pack / "onchain.json").unlink()
    result = runner.invoke(app, ["policy", "compile", str(pack)])
    assert result.exit_code == 1
    assert "no on-chain section" in result.output


def test_compile_malformed_section_is_a_no(pack):
    (pack / "onchain.json").write_text(json.dumps({"domain": "health", "edges": []}))
    result = runner.invoke(app, ["policy", "compile", str(pack), "--json"])
    assert result.exit_code == 1
    assert _json(result)["error"]["code"] == "EMPTY"


def test_map_lists_every_edge(pack):
    result = runner.invoke(app, ["policy", "map", str(pack)])
    assert result.exit_code == 0, result.output
    assert "0xa9059cbb" in result.stdout and "900" in result.stdout
    doc = _json(runner.invoke(app, ["policy", "map", str(pack), "--json"]))
    assert sorted(e["risk_weight_bps"] for e in doc["edges"]) == [200, 500, 900]


@pytest.mark.parametrize(
    "call, code",
    [
        (f"{TOKEN}:0xa9059cbb", 0),
        (f"{TOKEN}:0xa9059cbb:500", 0),
        (f"{TOKEN}:0xa9059cbb:900", 1),  # mapped, but not at that risk weight
        (f"{TOKEN}:0x23b872dd", 1),  # transferFrom: not mapped
        ("0x" + "11" * 20 + ":0xa9059cbb", 1),
    ],
)
def test_check(pack, call, code):
    result = runner.invoke(app, ["policy", "check", str(pack), "--call", call])
    assert result.exit_code == code, result.output


@pytest.mark.parametrize("call", ["nope", f"{TOKEN}", f"{TOKEN}:0xa9", f"{TOKEN}:0xa9059cbb:x"])
def test_check_malformed_call_is_a_usage_error(pack, call):
    assert runner.invoke(app, ["policy", "check", str(pack), "--call", call]).exit_code == 2


def test_prove_returns_the_execute_claim_and_a_proof_that_matches_the_sdk(pack, policy):
    result = runner.invoke(app, ["policy", "prove", str(pack), "--target", TOKEN, "--selector", "0xa9059cbb", "--json"])
    assert result.exit_code == 0, result.output
    doc = _json(result)
    (edge,) = edges_for_call(policy, TOKEN, "0xa9059cbb")
    assert doc["proof"] == ["0x" + p.hex() for p in proof_for(policy, edge)]
    assert doc["execute_args"] == {
        "fromNode": "0x" + edge.from_node.hex(), "relation": "0x" + edge.relation.hex(),
        "toNode": "0x" + edge.to_node.hex(), "riskWeightBps": 500,
    }
    assert doc["root"] == "0x" + policy.root.hex()


def test_prove_an_ambiguous_call_needs_risk(pack, policy):
    argv = ["policy", "prove", str(pack), "--target", TOKEN, "--selector", "0x095ea7b3"]
    assert runner.invoke(app, argv).exit_code == 2
    doc = _json(runner.invoke(app, argv + ["--risk", "900", "--json"]))
    assert doc["execute_args"]["riskWeightBps"] == 900


def test_prove_an_unmapped_call_is_a_no(pack):
    result = runner.invoke(app, ["policy", "prove", str(pack), "--target", TOKEN, "--selector", "0x23b872dd"])
    assert result.exit_code == 1


def _deployments(tmp_path, *, registry=REGISTRY, chain_id=84532):
    path = tmp_path / "deployments.json"
    singletons = {"PolicyRegistry": registry} if registry else {}
    path.write_text(json.dumps({"chainId": chain_id, "singletons": singletons}))
    return str(path)


def test_publish_only_prints_the_transaction(pack, policy, tmp_path):
    dep = _deployments(tmp_path)
    assert runner.invoke(app, ["policy", "publish", str(pack), "--deployments-file", dep]).exit_code == 2
    result = runner.invoke(app, ["policy", "publish", str(pack), "--print-tx", "--deployments-file", dep, "--json"])
    assert result.exit_code == 0, result.output
    doc = _json(result)
    tx = doc["tx"]
    assert tx["function"] == SET_GRAPH_ROOT_SIGNATURE
    assert tx["to"].lower() == REGISTRY.lower() and tx["chainId"] == 84532
    assert tx["args"] == {"domainId": "0x" + policy.domain_id.hex(), "root": "0x" + policy.root.hex()}
    assert doc["pack_hash"].startswith("sha256:")
    assert "nonce" not in tx and "signature" not in doc


def test_publish_without_a_policy_registry_is_a_no(pack, tmp_path):
    dep = _deployments(tmp_path, registry=None)
    assert runner.invoke(app, ["policy", "publish", str(pack), "--print-tx", "--deployments-file", dep]).exit_code == 1


class _W3:
    def __init__(self, connected=True):
        self._connected = connected

    def is_connected(self):
        return self._connected


@pytest.mark.parametrize("onchain_matches, code", [(True, 0), (False, 1)])
def test_diff_compares_with_policy_registry(pack, policy, tmp_path, monkeypatch, onchain_matches, code):
    from integrity_cli import policy_cmd

    seen = {}

    def fake_root(w3, registry, domain_id):
        seen["args"] = (registry, domain_id)
        return policy.root if onchain_matches else b"\x00" * 32

    monkeypatch.setattr(policy_cmd, "get_w3", lambda url: _W3())
    monkeypatch.setattr(policy_cmd, "graph_root_of", fake_root)
    result = runner.invoke(app, ["policy", "diff", str(pack), "--deployments-file", _deployments(tmp_path), "--json"])
    assert result.exit_code == code, result.output
    doc = _json(result)
    assert doc["match"] is onchain_matches
    assert doc["local_root"] == "0x" + policy.root.hex()
    assert seen["args"] == (REGISTRY, policy.domain_id)


def test_diff_domain_override(pack, policy, tmp_path, monkeypatch):
    from integrity_cli import policy_cmd
    from integrity_sdk.core.pack_onchain import domain_id

    seen = {}
    monkeypatch.setattr(policy_cmd, "get_w3", lambda url: _W3())
    monkeypatch.setattr(policy_cmd, "graph_root_of", lambda w3, r, d: seen.setdefault("d", d) and policy.root)
    runner.invoke(app, ["policy", "diff", str(pack), "--domain", "finance", "--deployments-file", _deployments(tmp_path)])
    assert seen["d"] == domain_id("finance")


def test_diff_unreachable_rpc_is_unverified(pack, tmp_path, monkeypatch):
    from integrity_cli import policy_cmd

    monkeypatch.setattr(policy_cmd, "get_w3", lambda url: _W3(connected=False))
    result = runner.invoke(app, ["policy", "diff", str(pack), "--deployments-file", _deployments(tmp_path)])
    assert result.exit_code == 3


def test_diff_read_error_is_unverified(pack, tmp_path, monkeypatch):
    import requests

    from integrity_cli import policy_cmd

    def boom(*a):
        raise requests.ConnectionError("reset")

    monkeypatch.setattr(policy_cmd, "get_w3", lambda url: _W3())
    monkeypatch.setattr(policy_cmd, "graph_root_of", boom)
    assert runner.invoke(app, ["policy", "diff", str(pack), "--deployments-file", _deployments(tmp_path)]).exit_code == 3


def test_diff_uses_the_network_profile_deployments(pack, tmp_path, monkeypatch):
    from integrity_cli import config, policy_cmd

    dep = _deployments(tmp_path)
    monkeypatch.setenv("DEPLOYMENTS_FILE", dep)
    seen = {}
    monkeypatch.setattr(policy_cmd, "get_w3", lambda url: seen.setdefault("url", url) and _W3())
    monkeypatch.setattr(policy_cmd, "graph_root_of", lambda *a: b"\x00" * 32)
    runner.invoke(app, ["--network", "base-sepolia", "policy", "diff", str(pack)])
    assert seen["url"] == "https://sepolia.base.org"
