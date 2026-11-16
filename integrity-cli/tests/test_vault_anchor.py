"""`vault sync` anchors under the DID's actor on `ActionAnchor` (v2 graph deletion, slice D1).

With no bound actor the result is `NO_ACTOR`: no wallet is loaded and no transaction is built,
so the vault stays local and verifiable off-chain (owner question 8b).
"""
from __future__ import annotations

import json

import pytest

from integrity_cli import chain, identity, vault, wallet

DID = "did:integrity:" + "ab" * 32
ACTOR = "0x" + "a1" * 20
REGISTRY = "0x" + "11" * 20
ACTION_ANCHOR = "0x" + "22" * 20


@pytest.fixture
def sync_env(tmp_path, monkeypatch):
    monkeypatch.setattr(vault, "VAULT_DIR", tmp_path / "vault")
    monkeypatch.setattr(identity, "did_document", lambda _name: {"id": DID})
    monkeypatch.setattr(chain, "get_w3", lambda _url: type("W3", (), {"eth": type("E", (), {"chain_id": 31337})()})())
    deployments = tmp_path / "deployments.json"
    deployments.write_text(json.dumps({"singletons": {"AgentRegistry": REGISTRY, "ActionAnchor": ACTION_ANCHOR}}))
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(json.dumps({"type": "USER_INPUT", "content": "hello"}) + "\n")
    return transcript, str(deployments)


def test_no_actor_skips_without_a_wallet_or_a_transaction(sync_env, monkeypatch):
    transcript, deployments = sync_env
    monkeypatch.setattr(chain, "resolve_actor", lambda _w3, registry, did: None)

    def forbidden(*_a, **_k):
        raise AssertionError("must not load a wallet or send for an agent with no actor")

    monkeypatch.setattr(wallet, "generate_or_load_evm_wallet", forbidden)
    monkeypatch.setattr(chain, "anchor_root", forbidden)

    result = vault.sync_vault("agent", transcript, "http://rpc", deployments)

    assert result["anchor_status"] == chain.NO_ACTOR
    assert result["anchored_on_chain"] is False


def test_bound_actor_anchors_under_the_actor_on_action_anchor(sync_env, monkeypatch):
    transcript, deployments = sync_env
    seen = {}
    monkeypatch.setattr(chain, "resolve_actor", lambda _w3, registry, did: seen.update(registry=registry, did=did) or ACTOR)
    monkeypatch.setattr(wallet, "generate_or_load_evm_wallet", lambda _name: "controller")

    def fake_anchor(_w3, account, actor, action_anchor, chain_id, root):
        seen.update(account=account, actor=actor, action_anchor=action_anchor, root=root)
        return "0xtx"

    monkeypatch.setattr(chain, "anchor_root", fake_anchor)

    result = vault.sync_vault("agent", transcript, "http://rpc", deployments)

    assert result["anchor_status"] == "anchored"
    assert result["anchored_on_chain"] is True
    assert seen["registry"] == REGISTRY and seen["did"] == DID
    assert seen["actor"] == ACTOR and seen["action_anchor"] == ACTION_ANCHOR
    assert seen["account"] == "controller"
    assert "0x" + seen["root"].hex() == result["state_root"] or seen["root"].hex() == result["state_root"]
