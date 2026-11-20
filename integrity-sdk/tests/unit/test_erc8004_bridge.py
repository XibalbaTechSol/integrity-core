"""Unit tests for the modular ERC-8004 / Agent0 Public Passport Bridge (`integrity_sdk.erc8004`)."""
from __future__ import annotations

import base64
import json

import pytest
import requests

from integrity_sdk import erc8004
from integrity_sdk.did import Keypair, fingerprint_for_pubkey


def _sample_did() -> str:
    kp = Keypair.generate()
    return "did:integrity:" + fingerprint_for_pubkey(kp.public_bytes())


def test_caip10_registry_lowercases_address_and_validates():
    assert (
        erc8004.caip10_registry(84532, "0x8004A818BFB912233c491871b3d84c89A494BD9e")
        == "eip155:84532:0x8004a818bfb912233c491871b3d84c89a494bd9e"
    )
    with pytest.raises(ValueError, match="chain_id"):
        erc8004.caip10_registry(0, "0x8004A818BFB912233c491871b3d84c89A494BD9e")
    with pytest.raises(ValueError, match="invalid registry"):
        erc8004.caip10_registry(84532, "not-an-address")


def test_build_registration_document_matches_oracle_erc8004_schema():
    did = _sample_did()
    doc = erc8004.build_registration_document(
        did=did,
        name="Xibalba Sentinel",
        description="Policy-confined autonomous agent",
        image="https://integrity.xibalba.solutions/sentinel.png",
        chain_id=84532,
        registry_address="0x8004A818BFB912233c491871b3d84c89A494BD9e",
        token_id=7,
        mcp_endpoint="https://mcp.xibalba.solutions/v1",
        a2a_endpoint="https://agent.xibalba.solutions/.well-known/agent-card.json",
        a2a_version="0.3.0",
        x402_support=True,
    )
    assert doc["type"] == "https://eips.ethereum.org/EIPS/eip-8004#registration-v1"
    assert doc["x402Support"] is True
    assert doc["active"] is True
    assert doc["registrations"] == [
        {
            "agentId": 7,
            "agentRegistry": "eip155:84532:0x8004a818bfb912233c491871b3d84c89a494bd9e",
        }
    ]
    did_svc = next(s for s in doc["services"] if s["name"] == "DID")
    assert did_svc["endpoint"] == did
    mcp_svc = next(s for s in doc["services"] if s["name"] == "MCP")
    assert mcp_svc["endpoint"] == "https://mcp.xibalba.solutions/v1"
    a2a_svc = next(s for s in doc["services"] if s["name"] == "A2A")
    assert a2a_svc == {
        "name": "A2A",
        "endpoint": "https://agent.xibalba.solutions/.well-known/agent-card.json",
        "version": "0.3.0",
    }

    data_uri, sha256_hex = erc8004.encode_registration_data_uri(doc)
    assert data_uri.startswith("data:application/json;base64,")
    assert len(sha256_hex) == 64
    decoded = json.loads(base64.b64decode(data_uri.split(",", 1)[1]))
    assert decoded == doc


def test_build_registration_document_rejects_invalid_did_or_empty_fields():
    with pytest.raises(ValueError, match="did:integrity:"):
        erc8004.build_registration_document(did="did:key:123", name="A", description="B")
    did = _sample_did()
    with pytest.raises(ValueError, match="non-empty"):
        erc8004.build_registration_document(did=did, name="  ", description="B")


def test_link_erc8004_with_oracle_parses_confined_wallet_response(monkeypatch):
    did = _sample_did()
    actor = "0x" + "33" * 20
    owner = "0x" + "22" * 20
    seen = {}

    class _Resp:
        status_code = 200
        text = "{}"

        def json(self):
            return {
                "agent_id": did,
                "chain_id": 84532,
                "identity_registry_address": erc8004.BASE_SEPOLIA_ERC8004_REGISTRY,
                "agent_token_id": "7",
                "registration_uri": "data:application/json;base64,e30=",
                "registration_sha256": "a" * 64,
                "nft_owner_address": owner,
                "agent_wallet_address": actor,
                "sovereign_actor_address": actor,
                "wallet_confined": True,
                "binding_status": "verified",
                "name": "Xibalba",
                "description": "Confined Agent",
                "x402_support": True,
                "mcp_endpoint": "https://mcp.example",
                "a2a_endpoint": None,
                "a2a_version": None,
            }

    def fake_post(url, json, timeout):
        seen["url"] = url
        seen["json"] = json
        return _Resp()

    monkeypatch.setattr(erc8004.requests, "post", fake_post)
    binding = erc8004.link_erc8004_with_oracle(
        "http://oracle:8080/",
        did,
        chain_id=84532,
        identity_registry_address=erc8004.BASE_SEPOLIA_ERC8004_REGISTRY,
        agent_token_id=7,
    )
    assert seen["url"] == f"http://oracle:8080/v1/agent/{did}/erc8004"
    assert seen["json"]["agent_token_id"] == "7"
    assert binding.wallet_confined is True
    assert binding.sovereign_actor_address == actor
    assert binding.agent_wallet_address == actor


def test_link_erc8004_maps_unreachable_and_refused(monkeypatch):
    did = _sample_did()

    def down(url, json, timeout):
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(erc8004.requests, "post", down)
    with pytest.raises(erc8004.Erc8004BridgeError) as exc_info:
        erc8004.link_erc8004_with_oracle(
            "http://oracle:8080",
            did,
            chain_id=84532,
            identity_registry_address=erc8004.BASE_SEPOLIA_ERC8004_REGISTRY,
            agent_token_id=7,
        )
    assert exc_info.value.unreachable is True

    class _Refused:
        status_code = 400
        text = '{"error":"registration file has no matching Integrity DID service"}'

        def json(self):
            return {"error": "registration file has no matching Integrity DID service"}

    monkeypatch.setattr(erc8004.requests, "post", lambda url, json, timeout: _Refused())
    with pytest.raises(erc8004.Erc8004BridgeError) as exc_info2:
        erc8004.link_erc8004_with_oracle(
            "http://oracle:8080",
            did,
            chain_id=84532,
            identity_registry_address=erc8004.BASE_SEPOLIA_ERC8004_REGISTRY,
            agent_token_id=7,
        )
    assert exc_info2.value.status == 400
    assert exc_info2.value.unreachable is False
    assert "matching Integrity DID" in exc_info2.value.detail


def test_caip10_account_validation():
    assert (
        erc8004.caip10_account(84532, "0xE7251742c6f4F8849600d44c6aed62e07DaA7Ea1")
        == "eip155:84532:0xe7251742c6f4f8849600d44c6aed62e07daa7ea1"
    )
    with pytest.raises(ValueError, match="chain_id"):
        erc8004.caip10_account(0, "0xE7251742c6f4F8849600d44c6aed62e07DaA7Ea1")
    with pytest.raises(ValueError, match="invalid address"):
        erc8004.caip10_account(84532, "invalid-addr")


def test_build_ais_feedback_document_and_encode():
    client_addr = "0xE7251742c6f4F8849600d44c6aed62e07DaA7Ea1"
    doc = erc8004.build_ais_feedback_document(
        agent_id=1,
        client_address=client_addr,
        chain_id=84532,
        identity_registry_address=erc8004.BASE_SEPOLIA_ERC8004_REGISTRY,
        ais_score_bps=9850,
        evidence_root="0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        window_end=1795147200,
        factors={"executionIntegrity": 0.99, "economicSafety": 0.98},
        grpo_advantage=0.45,
        dpo_preference="positive",
        created_at="2026-11-20T04:20:00Z",
        endpoint="https://oracle.integrity.xibalba.io",
        tag1="ais",
        tag2="oracle",
        mcp_tool="execute_trade",
        a2a_context_id="ctx-001",
        a2a_task_id="task-001",
        proof_of_payment={
            "fromAddress": client_addr,
            "toAddress": "0x21fdEd74C901129977B8e28C2588595163E1e235",
            "chainId": "84532",
            "txHash": "0xabcdef1234567890",
        },
    )

    assert "type" not in doc
    assert doc["ais"]["schema"] == erc8004.AIS_FEEDBACK_EXTENSION
    assert doc["agentRegistry"] == "eip155:84532:0x8004a818bfb912233c491871b3d84c89a494bd9e"
    assert doc["agentId"] == 1
    assert doc["clientAddress"] == "eip155:84532:0xe7251742c6f4f8849600d44c6aed62e07daa7ea1"
    assert doc["value"] == 9850
    assert doc["valueDecimals"] == 2
    assert doc["tag1"] == "ais"
    assert doc["tag2"] == "oracle"
    assert doc["ais"]["scoreBps"] == 9850
    assert doc["ais"]["scorePercent"] == 98.5
    assert doc["ais"]["grpoAdvantage"] == 0.45
    assert doc["ais"]["dpoPreference"] == "positive"
    assert doc["mcp"]["tool"] == "execute_trade"
    assert doc["a2a"]["contextId"] == "ctx-001"
    assert doc["proofOfPayment"]["chainId"] == "84532"

    uri, f_hash = erc8004.encode_feedback_data_uri(doc)
    assert uri.startswith("data:application/json;base64,")
    assert len(f_hash) == 32

    # Roundtrip decoding
    b64_payload = uri.split("data:application/json;base64,")[1]
    decoded = json.loads(base64.b64decode(b64_payload).decode("utf-8"))
    assert decoded["agentId"] == 1
    assert decoded["ais"]["scoreBps"] == 9850


def test_build_ais_feedback_document_validations():
    client_addr = "0xE7251742c6f4F8849600d44c6aed62e07DaA7Ea1"
    with pytest.raises(ValueError, match="ais_score_bps"):
        erc8004.build_ais_feedback_document(
            agent_id=1,
            client_address=client_addr,
            ais_score_bps=10001,
        )
    with pytest.raises(ValueError, match="ais_score_bps"):
        erc8004.build_ais_feedback_document(
            agent_id=1,
            client_address=client_addr,
            ais_score_bps=-1,
        )
    with pytest.raises(ValueError, match="agent_id"):
        erc8004.build_ais_feedback_document(
            agent_id=0,
            client_address=client_addr,
            ais_score_bps=9500,
        )


def test_ais_score_from_reputation_filters_tag_scorer_and_revocation():
    scorer = "0xE7251742c6f4F8849600d44c6aed62e07DaA7Ea1"
    other = "0xb0d39280Abd48F605459675142dc6243eb353270"
    F = erc8004.Erc8004FeedbackItem
    summary = erc8004.Erc8004ReputationSummary(
        agent_id=1, count=5, summary_value=0, summary_value_decimals=0,
        clients=[scorer, other],
        feedbacks=[
            F(scorer, 1, 9100, 2, "ais", "oracle", False),
            F(scorer, 2, 9850, 2, "ais", "oracle", False),
            F(scorer, 3, 1000, 2, "ais", "oracle", True),         # revoked
            F(other, 9, 10000, 2, "ais", "oracle", False),        # untrusted
            F(scorer, 4, 150000, 2, "glicko2-mu", "ipd", False),  # wrong tag
        ],
    )
    assert erc8004.ais_score_from_reputation(summary, [scorer]) == 9850
    assert erc8004.ais_score_from_reputation(summary, [other.lower()]) == 10000
    assert erc8004.ais_score_from_reputation(summary, ["0x21fdEd74C901129977B8e28C2588595163E1e235"]) is None
    with pytest.raises(ValueError, match="trusted_scorers"):
        erc8004.ais_score_from_reputation(summary, [])
