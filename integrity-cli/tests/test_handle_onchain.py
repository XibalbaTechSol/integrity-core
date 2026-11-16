"""Registration v3 Phase 4, PR 4.1: `handle` writes are directory-first; on-chain is opt-in.

- `handle register H` claims H in the Oracle directory for the identity's DID: one HTTP call,
  no wallet, no RPC.
- `--onchain` does the XNS write, through the actor that the v3 `AgentRegistry` binds to the DID
  (`resolveDID(did).actor`), never the legacy Oracle `primitives.sovereign_agent` cache, which
  v3 agents never get.
- `set-primary` / `release` exist only on-chain and refuse to run without `--onchain`.
"""
from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from integrity_cli import chain, identity, status_cmd, wallet
from integrity_cli.main import app

runner = CliRunner()

ORACLE = "http://localhost:8080"
ZERO = "0x" + "00" * 20
REGISTRY_ACTOR = "0x" + "a1" * 20
ORACLE_CACHE_ACTOR = "0x" + "b2" * 20


class _FakeEth:
    chain_id = 31337


class _FakeW3:
    eth = _FakeEth()

    def is_connected(self) -> bool:
        return True


class _FakeRegistry:
    """AgentRegistry stand-in: `functions.resolveDID(did).call()` -> the v3 record tuple."""

    def __init__(self, actor: str, *, registered: bool = True, retired_at: int = 0, fail: bool = False):
        self.actor, self.registered, self.retired_at, self.fail = actor, registered, retired_at, fail
        self.functions = self
        self.calls: list[str] = []

    def resolveDID(self, did):  # noqa: N802 -- mirrors the Solidity name
        self.calls.append(did)
        return self

    def call(self):
        if self.fail:
            raise ConnectionError("node went away")
        pubkey = b"\x01" * 32 if self.registered else b"\x00" * 32
        return (pubkey, ZERO, self.actor, 1, "", 1700000000 if self.registered else 0, self.retired_at, b"")


def _deployments(tmp_path) -> str:
    f = tmp_path / "deployments.local.json"
    f.write_text(json.dumps({"singletons": {
        "XibalbaNameService": "0x" + "11" * 20,
        "AgentRegistry": "0x" + "22" * 20,
    }}))
    return str(f)


def _no_rpc(*_a, **_k):
    raise AssertionError("RPC must not be touched")


def _no_wallet(*_a, **_k):
    raise AssertionError("wallet must not be loaded")


@pytest.fixture
def did():
    assert runner.invoke(app, ["identity", "new"]).exit_code == 0
    return identity.did_document("default")["id"]


@pytest.fixture
def chain_ok(monkeypatch):
    """RPC connects; the registry fake is installed per test via `use_registry`."""
    monkeypatch.setattr(chain, "get_w3", lambda rpc_url: _FakeW3())
    monkeypatch.setattr(status_cmd, "get_w3", lambda rpc_url: _FakeW3())

    def use_registry(reg: _FakeRegistry) -> _FakeRegistry:
        monkeypatch.setattr(status_cmd, "agent_registry_contract", lambda w3, address: reg)
        return reg

    return use_registry


# --------------------------------------------------------------------------
# default: Oracle directory only
# --------------------------------------------------------------------------

def test_handle_register_default_is_directory_only(monkeypatch, did, httpx_mock):
    monkeypatch.setattr(chain, "get_w3", _no_rpc)
    monkeypatch.setattr(status_cmd, "get_w3", _no_rpc)
    monkeypatch.setattr(wallet, "generate_or_load_evm_wallet", _no_wallet)
    httpx_mock.add_response(
        method="POST", url=f"{ORACLE}/v1/xns/claim",
        json={"agent_id": did, "handle": "atlas"}, status_code=201,
    )

    result = runner.invoke(app, ["handle", "register", "atlas"])

    assert result.exit_code == 0, result.output
    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    assert json.loads(requests[0].content) == {"agent_id": did, "handle": "atlas"}


def test_handle_register_default_json(did, httpx_mock):
    httpx_mock.add_response(method="POST", url=f"{ORACLE}/v1/xns/claim", json={"agent_id": did, "handle": "atlas"})
    result = runner.invoke(app, ["handle", "register", "atlas", "--json"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["schema"] == "integrity.cli.handle.register.v1"
    assert doc == {**doc, "agent_id": did, "handle": "atlas", "namespace": "directory"}


@pytest.mark.parametrize("status, code", [(409, 1), (422, 1), (503, 3)])
def test_handle_register_default_maps_oracle_errors(did, httpx_mock, status, code):
    httpx_mock.add_response(method="POST", url=f"{ORACLE}/v1/xns/claim", status_code=status, text="nope")
    assert runner.invoke(app, ["handle", "register", "atlas"]).exit_code == code


# --------------------------------------------------------------------------
# --onchain: actor from AgentRegistry
# --------------------------------------------------------------------------

def test_handle_register_onchain_requires_bound_actor(monkeypatch, tmp_path, did, chain_ok):
    reg = chain_ok(_FakeRegistry(ZERO))
    monkeypatch.setattr(wallet, "generate_or_load_evm_wallet", _no_wallet)

    result = runner.invoke(app, ["handle", "register", "atlas", "--onchain", "--deployments-file", _deployments(tmp_path)])

    assert result.exit_code == 1, result.output
    assert "no bound actor" in result.output
    assert reg.calls == [did]


def test_handle_register_onchain_refuses_retired_record(monkeypatch, tmp_path, did, chain_ok):
    chain_ok(_FakeRegistry(REGISTRY_ACTOR, retired_at=1700000500))
    monkeypatch.setattr(wallet, "generate_or_load_evm_wallet", _no_wallet)
    result = runner.invoke(app, ["handle", "register", "atlas", "--onchain", "--deployments-file", _deployments(tmp_path)])
    assert result.exit_code == 1
    assert "retired" in result.output


def test_handle_register_onchain_unreadable_registry_is_unverified(monkeypatch, tmp_path, did, chain_ok):
    chain_ok(_FakeRegistry(REGISTRY_ACTOR, fail=True))
    monkeypatch.setattr(wallet, "generate_or_load_evm_wallet", _no_wallet)
    result = runner.invoke(app, ["handle", "register", "atlas", "--onchain", "--deployments-file", _deployments(tmp_path)])
    assert result.exit_code == 3, result.output


def test_handle_onchain_actor_comes_from_agent_registry(monkeypatch, tmp_path, did, chain_ok, httpx_mock):
    # The legacy Oracle cache disagrees with the registry. If the CLI ever read it again, the
    # XNS write below would target ORACLE_CACHE_ACTOR and this test fails.
    httpx_mock.add_response(
        method="GET", url=f"{ORACLE}/v1/agent/{did}",
        json={"primitives": {"sovereign_agent": ORACLE_CACHE_ACTOR}}, is_optional=True,
    )
    chain_ok(_FakeRegistry(REGISTRY_ACTOR))
    monkeypatch.setattr(wallet, "generate_or_load_evm_wallet", lambda name: object())
    targeted: list[str] = []

    def fake_xns_register(w3, account, sovereign_agent, xns_address, handle, chain_id):
        targeted.append(sovereign_agent)
        return {"transactionHash": b"\xab" * 32}

    monkeypatch.setattr(chain, "xns_register", fake_xns_register)

    result = runner.invoke(
        app, ["handle", "register", "atlas", "--onchain", "--json", "--deployments-file", _deployments(tmp_path)]
    )

    assert result.exit_code == 0, result.output
    assert targeted == [REGISTRY_ACTOR]
    doc = json.loads(result.stdout)
    assert doc["namespace"] == "onchain" and doc["actor"] == REGISTRY_ACTOR


# --------------------------------------------------------------------------
# set-primary / release: on-chain only
# --------------------------------------------------------------------------

@pytest.mark.parametrize("cmd", ["set-primary", "release"])
def test_onchain_only_commands_require_flag(monkeypatch, did, cmd):
    monkeypatch.setattr(chain, "get_w3", _no_rpc)
    monkeypatch.setattr(status_cmd, "get_w3", _no_rpc)
    monkeypatch.setattr(wallet, "generate_or_load_evm_wallet", _no_wallet)
    result = runner.invoke(app, ["handle", cmd, "atlas"])
    assert result.exit_code == 1
    assert "on-chain only; pass --onchain" in result.output


@pytest.mark.parametrize("cmd", ["set-primary", "release"])
def test_onchain_only_commands_require_bound_actor(monkeypatch, tmp_path, did, chain_ok, cmd):
    chain_ok(_FakeRegistry(ZERO, registered=False))
    monkeypatch.setattr(wallet, "generate_or_load_evm_wallet", _no_wallet)
    result = runner.invoke(app, ["handle", cmd, "atlas", "--onchain", "--deployments-file", _deployments(tmp_path)])
    assert result.exit_code == 1
    assert "no bound actor" in result.output
