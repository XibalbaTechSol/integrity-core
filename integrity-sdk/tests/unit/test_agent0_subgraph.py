"""Unit tests for `integrity_sdk.agent0_subgraph` (Agent0 ERC-8004 subgraph reader)."""
from __future__ import annotations

import pytest

from integrity_sdk import agent0_subgraph as sg
from integrity_sdk import erc8004

SCORER = "0xE7251742c6f4F8849600d44c6aed62e07DaA7Ea1"
SYBIL = "0xb0d39280Abd48F605459675142dc6243eb353270"
URL = "http://subgraph.test/graphql"


class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code, self.text = payload, status, str(payload)

    def json(self):
        return self._p


def _ais_row(index: int, bps: int, *, agent_id: int = 1, tamper: bool = False, mismatch: bool = False):
    doc = erc8004.build_ais_feedback_document(
        agent_id=agent_id, client_address=SCORER, ais_score_bps=bps + (1 if mismatch else 0),
        created_at="2026-11-20T04:00:00Z",
    )
    uri, h = erc8004.encode_feedback_data_uri(doc)
    if tamper:
        h = b"\x00" * 32
    return {
        "id": f"84532:{agent_id}:{SCORER.lower()}:{index}", "clientAddress": SCORER.lower(),
        "feedbackIndex": str(index), "value": str(bps / 100), "tag1": "ais", "tag2": "oracle",
        "endpoint": "", "feedbackURI": uri, "feedbackURIType": "data", "feedbackHash": "0x" + h.hex(),
        "isRevoked": False, "createdAt": str(1795140000 + index),
    }


def test_subgraph_url_requires_key_and_never_hardcodes(monkeypatch):
    monkeypatch.delenv("GRAPH_API_KEY", raising=False)
    monkeypatch.delenv("INTEGRITY_AGENT0_SUBGRAPH_URL", raising=False)
    with pytest.raises(sg.Agent0SubgraphError, match="API key"):
        sg.subgraph_url(84532)
    monkeypatch.setenv("GRAPH_API_KEY", "k123")
    assert sg.subgraph_url(84532) == (
        "https://gateway.thegraph.com/api/k123/subgraphs/id/4yYAvQLFjBhBtdRCY7eUWo181VNoTSLLFd5M7FXQAi6u"
    )
    monkeypatch.setenv("INTEGRITY_AGENT0_SUBGRAPH_URL", URL)
    assert sg.subgraph_url(84532) == URL
    monkeypatch.delenv("INTEGRITY_AGENT0_SUBGRAPH_URL")
    with pytest.raises(sg.Agent0SubgraphError, match="no Agent0 subgraph"):
        sg.subgraph_url(424242)


def test_list_agents_parses_registration_and_integrity_did(monkeypatch):
    captured = {}
    did = "did:integrity:" + "ab" * 32
    row = {
        "id": "84532:7", "chainId": "84532", "agentId": "7",
        "owner": "0x21fded74c901129977b8e28c2588595163e1e235", "agentWallet": None,
        "agentURI": "data:application/json;base64,e30=", "agentURIType": "data",
        "totalFeedback": "3", "lastActivity": "1795140000",
        "registrationFile": {
            "name": "Sentinel", "description": "d", "image": "", "active": True, "x402Support": True,
            "supportedTrusts": ["reputation"], "mcpEndpoint": "https://mcp.x", "mcpVersion": None,
            "a2aEndpoint": "https://a2a.x", "a2aVersion": "0.3.0", "webEndpoint": None,
            "did": did, "ens": None, "oasfSkills": ["trading"], "oasfDomains": [],
        },
    }

    def fake_post(url, json, timeout):
        captured.update(json)
        return _Resp({"data": {"agents": [row]}})

    monkeypatch.setattr(sg.requests, "post", fake_post)
    agents = sg.list_agents(84532, integrity_only=True, url=URL)
    assert 'did_starts_with: "did:integrity:"' in captured["query"]
    a = agents[0]
    assert (a.agent_id, a.integrity_did, a.mcp_endpoint, a.x402_support) == (7, did, "https://mcp.x", True)
    assert a.owner == "0x21fdEd74C901129977B8e28C2588595163E1e235"


def test_ais_history_decodes_and_verifies_data_uri(monkeypatch):
    captured = {}
    rows = [_ais_row(2, 9850), _ais_row(1, 9100, tamper=True), _ais_row(3, 9700, mismatch=True)]

    def fake_post(url, json, timeout):
        captured.update(json)
        return _Resp({"data": {"feedbacks": rows}})

    monkeypatch.setattr(sg.requests, "post", fake_post)
    hist = sg.ais_feedback_history(84532, 1, [SCORER], url=URL)
    assert captured["variables"]["clients"] == [SCORER.lower()]
    assert captured["variables"]["tag"] == "ais"
    good, tampered, mismatched = hist
    assert good.score_bps == 9850 and good.hash_verified and good.document["ais"]["scoreBps"] == 9850
    assert tampered.score_bps == 9100 and not tampered.hash_verified and tampered.document is None
    assert mismatched.score_bps == 9700 and not mismatched.hash_verified  # off-chain doc disagrees


def test_ais_history_requires_trusted_scorers_and_rejects_out_of_range(monkeypatch):
    with pytest.raises(ValueError, match="trusted_scorers"):
        sg.ais_feedback_history(84532, 1, [], url=URL)
    bad = dict(_ais_row(1, 9000), value="1500.00")  # e.g. a glicko rating mis-tagged "ais"
    monkeypatch.setattr(sg.requests, "post", lambda url, json, timeout: _Resp({"data": {"feedbacks": [bad]}}))
    assert sg.ais_feedback_history(84532, 1, [SCORER], url=URL) == []


def test_graphql_errors_raise(monkeypatch):
    monkeypatch.setattr(sg.requests, "post", lambda url, json, timeout: _Resp({"errors": [{"message": "auth error"}]}))
    with pytest.raises(sg.Agent0SubgraphError, match="auth error"):
        sg.get_agent(84532, 1, url=URL)


def test_decode_feedback_data_uri_edge_cases():
    assert sg.decode_feedback_data_uri(None, None) == (None, False)
    assert sg.decode_feedback_data_uri("ipfs://bafy", "0x00") == (None, False)
    assert sg.decode_feedback_data_uri("data:application/json;base64,!!!", "0x00") == (None, False)
