"""v3 CLI conventions: one JSON shape, one exit-code table, one config precedence.

Exit codes (every query command): 0 yes/ok, 1 definite no, 2 usage (Click's own),
3 unverified/unreachable, 4 the chain refused a write.
Config precedence: flag > env > --network profile > config file > built-in default.
"""
from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from integrity_cli import config, output
from integrity_cli.main import app

runner = CliRunner()


# --- output ----------------------------------------------------------------------------------

def test_exit_code_table():
    assert (output.EXIT_OK, output.EXIT_NO, output.EXIT_USAGE, output.EXIT_UNVERIFIED, output.EXIT_REVERT) == (0, 1, 2, 3, 4)


def test_schema_id():
    assert output.schema_id("policy", "compile") == "integrity.cli.policy.compile.v1"


def test_json_mode_puts_one_document_on_stdout_and_human_text_on_stderr(capsys):
    rep = output.Reporter("demo", "cmd", json_mode=True)
    rep.info("hello human")
    rep.result({"answer": 42})
    out, err = capsys.readouterr()
    assert json.loads(out) == {"schema": "integrity.cli.demo.cmd.v1", "answer": 42}
    assert "hello human" in err and "hello human" not in out


def test_human_mode_prints_to_stdout_and_emits_no_json(capsys):
    rep = output.Reporter("demo", "cmd", json_mode=False)
    rep.info("hello human")
    rep.result({"answer": 42})
    out, err = capsys.readouterr()
    assert "hello human" in out and "{" not in out and err == ""


def test_fail_emits_a_json_error_and_exits_with_the_code(capsys):
    import typer

    rep = output.Reporter("demo", "cmd", json_mode=True)
    with pytest.raises(typer.Exit) as e:
        rep.fail(output.EXIT_UNVERIFIED, "oracle down", code="UNREACHABLE")
    assert e.value.exit_code == 3
    doc = json.loads(capsys.readouterr().out)
    assert doc == {"schema": "integrity.cli.demo.cmd.v1", "ok": False, "error": {"code": "UNREACHABLE", "detail": "oracle down"}}


def test_chain_error_classification():
    import requests
    from web3.exceptions import ContractCustomError, ContractLogicError

    assert output.exit_code_for_chain_error(ContractLogicError("execution reverted")) == 4
    assert output.exit_code_for_chain_error(ContractCustomError("0xf6b72bbe")) == 4
    assert output.exit_code_for_chain_error(requests.ConnectionError("refused")) == 3
    assert output.exit_code_for_chain_error(TimeoutError()) == 3
    assert output.exit_code_for_chain_error(ValueError("other")) == 1


# --- config precedence -----------------------------------------------------------------------

def test_default_then_file_then_profile_then_env(monkeypatch):
    assert config.get_config_value("RPC_URL") == "http://localhost:8545"
    config.set_config_value("RPC_URL", "http://file:8545")
    assert config.value_with_source("RPC_URL") == ("http://file:8545", "config file")
    config.set_network("base-sepolia")
    assert config.value_with_source("RPC_URL") == ("https://sepolia.base.org", "profile:base-sepolia")
    monkeypatch.setenv("RPC_URL", "http://env:8545")
    assert config.value_with_source("RPC_URL") == ("http://env:8545", "env")


def test_profile_sets_rpc_deployments_and_oracle_together():
    config.set_network("base-sepolia")
    assert config.get_config_value("ORACLE_URL") == "https://integrity-oracle.onrender.com"
    assert config.get_config_value("DEPLOYMENTS_FILE").endswith("deployments.baseSepolia.json")
    # A real network refuses placeholder tokens: the profile is not ENVIRONMENT=local.
    assert config.get_config_value("ENVIRONMENT") != "local"


def test_profile_falls_through_for_keys_it_does_not_set():
    config.set_config_value("BCC_MIDDLEWARE_URL", "http://bcc.file")
    config.set_network("base-sepolia")
    assert config.value_with_source("BCC_MIDDLEWARE_URL") == ("http://bcc.file", "config file")


def test_network_from_env_and_config_file(monkeypatch):
    config.set_config_value("NETWORK", "base-sepolia")
    assert config.active_network() == "base-sepolia"
    monkeypatch.setenv("INTEGRITY_NETWORK", "local")
    assert config.active_network() == "local"


def test_unknown_network_is_rejected():
    with pytest.raises(ValueError):
        config.set_network("mainnet")


def test_network_flag_on_the_cli_and_its_usage_error():
    result = runner.invoke(app, ["--network", "base-sepolia", "config", "show"])
    assert result.exit_code == 0, result.output
    rpc_row = next(line for line in result.stdout.splitlines() if "RPC_URL" in line)
    rpc_value = [cell.strip() for cell in rpc_row.split("\u2502") if cell.strip()][1]
    assert rpc_value == "https://sepolia.base.org"
    assert "profile:base-sepolia" in result.stdout
    assert runner.invoke(app, ["--network", "mainnet", "config", "show"]).exit_code == 2


def test_bad_network_in_env_is_a_usage_error(monkeypatch):
    monkeypatch.setenv("INTEGRITY_NETWORK", "nope")
    assert runner.invoke(app, ["config", "show"]).exit_code == 2


# --- hard renames: the old names are gone (decision D2) ---------------------------------------

@pytest.mark.parametrize(
    "argv",
    [
        ["agent", "register"],
        ["agent", "show", "did:integrity:abc"],
        ["agent", "ais", "did:integrity:abc"],
        ["agent", "intercept", "-t", "payment"],
        ["identity", "keygen"],
        ["verify", "--receipts", "x.json"],
        ["xns", "available", "atlas"],
        ["xns", "resolve", "atlas.integrity"],
    ],
)
def test_old_command_names_are_usage_errors(argv):
    assert runner.invoke(app, argv).exit_code == 2


def test_new_command_tree_is_registered():
    for argv in (["register", "--help"], ["gate", "check", "--help"], ["receipts", "verify", "--help"],
                 ["identity", "new", "--help"], ["identity", "list", "--help"], ["status", "--help"],
                 ["doctor", "--help"], ["handle", "available", "--help"], ["handle", "claim", "--help"],
                 ["handle", "resolve", "--help"], ["policy", "compile", "--help"], ["policy", "publish", "--help"],
                 ["vault", "sync", "--help"]):
        assert runner.invoke(app, argv).exit_code == 0, argv


def test_identity_list(tmp_path):
    assert runner.invoke(app, ["identity", "list", "--json"]).stdout.strip()
    empty = json.loads(runner.invoke(app, ["identity", "list", "--json"]).stdout)
    assert empty == {"schema": "integrity.cli.identity.list.v1", "identities": []}
    runner.invoke(app, ["identity", "new", "--name", "beta"])
    runner.invoke(app, ["identity", "new", "--name", "alpha"])
    doc = json.loads(runner.invoke(app, ["identity", "list", "--json"]).stdout)
    assert [i["name"] for i in doc["identities"]] == ["alpha", "beta"]
    assert all(i["did"].startswith("did:integrity:") for i in doc["identities"])
    human = runner.invoke(app, ["identity", "list"])
    assert "alpha" in human.stdout and "beta" in human.stdout


def test_register_json(monkeypatch):
    from integrity_cli import main as cli_main
    from integrity_sdk.registration_offchain import OffchainRegistration

    monkeypatch.setattr(
        cli_main, "register_offchain",
        lambda url, did, kp, **kw: OffchainRegistration(agent_id=did, verification_tier=1, outcome="created", handle=kw.get("handle")),
    )
    runner.invoke(app, ["identity", "new"])
    result = runner.invoke(app, ["register", "--handle", "atlas", "--json"])
    assert result.exit_code == 0, result.output
    doc = json.loads(result.stdout)
    assert doc["schema"] == "integrity.cli.register.v1"
    assert doc["verification_tier"] == 1 and doc["outcome"] == "created" and doc["handle"] == "atlas"


def test_receipts_verify_json_carries_the_schema(tmp_path):
    bundle = tmp_path / "bundle.json"
    bundle.write_text("[{}]")  # malformed receipt: a definite no (1), not "unverified" (3)
    result = runner.invoke(app, ["receipts", "verify", "--receipts", str(bundle), "--trusted-signer", "zX", "--json"])
    doc = json.loads(result.stdout)
    assert doc["schema"] == "integrity.cli.receipts.verify.v1"
    assert result.exit_code == 1 and doc["valid"] is False


def test_receipts_verify_anchor_unavailable_is_unverified(tmp_path, monkeypatch):
    from integrity_cli import verify

    def boom(*a, **k):
        raise verify.VerifyError("ANCHOR_UNAVAILABLE", "rpc down")

    monkeypatch.setattr(verify, "verify_bundle", boom)
    bundle = tmp_path / "bundle.json"
    bundle.write_text("[]")
    result = runner.invoke(app, ["receipts", "verify", "--receipts", str(bundle), "--trusted-signer", "zX", "--json"])
    assert result.exit_code == 3
