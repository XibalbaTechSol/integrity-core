"""CLI tests for `integrity erc8004` (card, link, status, publish)."""
from __future__ import annotations

import json

from typer.testing import CliRunner

from integrity_cli import identity
from integrity_cli.main import app
from integrity_sdk import erc8004

runner = CliRunner()


def test_erc8004_card_generates_two_way_did_backlink_and_caip10():
    assert runner.invoke(app, ["identity", "new"]).exit_code == 0
    did = identity.did_document("default")["id"]

    result = runner.invoke(
        app,
        [
            "erc8004",
            "card",
            "--name",
            "Xibalba Core Agent",
            "--description",
            "Policy-confined agent with ERC-8004 passport",
            "--token-id",
            "42",
            "--mcp",
            "https://mcp.xibalba.solutions/sse",
            "--a2a",
            "https://agent.xibalba.solutions/.well-known/agent-card.json",
            "--x402",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    doc = json.loads(result.stdout)
    assert doc["schema"] == "integrity.cli.erc8004.card.v1"
    assert doc["agent_id"] == did
    assert doc["caip10_registry"] == "eip155:84532:0x8004a818bfb912233c491871b3d84c89a494bd9e"
    card = doc["document"]
    assert card["type"] == "https://eips.ethereum.org/EIPS/eip-8004#registration-v1"
    assert card["x402Support"] is True
    assert {"name": "DID", "endpoint": did} in card["services"]
    assert card["registrations"] == [
        {
            "agentId": 42,
            "agentRegistry": "eip155:84532:0x8004a818bfb912233c491871b3d84c89a494bd9e",
        }
    ]


def test_erc8004_link_and_status_cli(monkeypatch):
    assert runner.invoke(app, ["identity", "new"]).exit_code == 0
    did = identity.did_document("default")["id"]
    actor = "0x" + "55" * 20

    def fake_link(oracle_url, agent_did, *, chain_id, identity_registry_address, agent_token_id, timeout=30.0):
        return erc8004.Erc8004Binding(
            agent_id=agent_did,
            chain_id=chain_id,
            identity_registry_address=identity_registry_address,
            agent_token_id=str(agent_token_id),
            registration_uri="data:application/json;base64,e30=",
            registration_sha256="b" * 64,
            nft_owner_address="0x" + "11" * 20,
            agent_wallet_address=actor,
            sovereign_actor_address=actor,
            wallet_confined=True,
            binding_status="verified",
            name="Xibalba",
            description="Confined",
            x402_support=True,
            mcp_endpoint=None,
            a2a_endpoint=None,
            a2a_version=None,
        )

    monkeypatch.setattr(erc8004, "link_erc8004_with_oracle", fake_link)
    res = runner.invoke(app, ["erc8004", "link", "--token-id", "9", "--json"])
    assert res.exit_code == 0, res.output
    linked = json.loads(res.stdout)
    assert linked["schema"] == "integrity.cli.erc8004.link.v1"
    assert linked["binding"]["wallet_confined"] is True
    assert linked["binding"]["sovereign_actor_address"] == actor

    monkeypatch.setattr(
        erc8004,
        "get_erc8004_from_oracle",
        lambda url, d, timeout=30.0: {"agent_id": d, "agent_token_id": "9", "binding_status": "verified"},
    )
    st = runner.invoke(app, ["erc8004", "status", "--json"])
    assert st.exit_code == 0, st.output
    st_doc = json.loads(st.stdout)
    assert st_doc["linked"] is True
    assert st_doc["binding"]["agent_token_id"] == "9"


def test_erc8004_link_unreachable_exits_3(monkeypatch):
    assert runner.invoke(app, ["identity", "new"]).exit_code == 0

    def unreachable(*a, **k):
        raise erc8004.Erc8004BridgeError("link", None, "connection refused", unreachable=True)

    monkeypatch.setattr(erc8004, "link_erc8004_with_oracle", unreachable)
    res = runner.invoke(app, ["erc8004", "link", "--token-id", "9", "--json"])
    assert res.exit_code == 3, res.output
    assert json.loads(res.stdout)["error"]["code"] == "UNREACHABLE"
