"""Read-side ERC-8004 discovery + AIS reputation via the Agent0 subgraph.

Source: https://github.com/agent0lab/subgraph (multi-chain ERC-8004 indexer).

Indexing behaviour this module relies on (verified against the subgraph source):
* Registration files are parsed for `ipfs://` **and** base64 `data:` URIs, so agents
  registered by `integrity_sdk.erc8004` (data URIs) expose `registrationFile.did`.
* Feedback files are parsed **only** for IPFS URIs. For `data:` feedback URIs the
  subgraph still stores the raw `feedbackURI` and `feedbackHash`, so AIS documents are
  decoded here and integrity-checked against the on-chain keccak-256 commitment.
* `Feedback.value` is already scaled (`raw / 10^valueDecimals`) as a BigDecimal string.

Endpoints on The Graph Gateway require an API key. Configure with:
  INTEGRITY_AGENT0_SUBGRAPH_URL  full GraphQL URL (overrides everything), or
  GRAPH_API_KEY                  combined with the per-chain subgraph id below.
"""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import requests
from web3 import Web3

# Subgraph deployment ids, from the agent0lab/subgraph README.
AGENT0_SUBGRAPH_IDS: dict[int, str] = {
    1: "FV6RR6y13rsnCxBAicKuQEwDp8ioEGiNaWaZUmvr1F8k",
    8453: "43s9hQRurMGjuYnC1r2ZwS6xSQktbFyXMPMqGKUFJojb",
    56: "D6aWqowLkWqBgcqmpNKXuNikPkob24ADXCciiP8Hvn1K",
    137: "9q16PZv1JudvtnCAf44cBoxg82yK9SSsFvrjCY9xnneF",
    143: "4tvLxkczjhSaMiqRrCV1EyheYHyJ7Ad8jub1UUyukBjg",
    11155111: "6wQRC7geo9XYAhckfmfo8kbMRLeWU8KQd3XsJqFKmZLT",
    84532: "4yYAvQLFjBhBtdRCY7eUWo181VNoTSLLFd5M7FXQAi6u",
    97: "BTjind17gmRZ6YhT9peaCM13SvWuqztsmqyfjpntbg3Z",
    10143: "8iiMH9sj471jbp7AwUuuyBXvPJqCEsobuHBeUEKQSxhU",
}

_DATA_URI_PREFIX = "data:application/json;base64,"

_AGENT_FIELDS = """
  id chainId agentId owner agentWallet agentURI agentURIType totalFeedback lastActivity
  registrationFile {
    name description image active x402Support supportedTrusts
    mcpEndpoint mcpVersion a2aEndpoint a2aVersion webEndpoint did ens
    oasfSkills oasfDomains
  }
"""

_FEEDBACK_FIELDS = """
  id clientAddress feedbackIndex value tag1 tag2 endpoint
  feedbackURI feedbackURIType feedbackHash isRevoked createdAt
"""


class Agent0SubgraphError(RuntimeError):
    """Raised on transport, auth, or GraphQL errors from the subgraph."""


def subgraph_url(chain_id: int, *, api_key: Optional[str] = None) -> str:
    """Resolve the GraphQL endpoint for `chain_id`; never embeds a key from source."""
    override = os.environ.get("INTEGRITY_AGENT0_SUBGRAPH_URL")
    if override:
        return override
    sid = AGENT0_SUBGRAPH_IDS.get(int(chain_id))
    if sid is None:
        raise Agent0SubgraphError(f"no Agent0 subgraph deployment for chain {chain_id}")
    key = api_key or os.environ.get("GRAPH_API_KEY")
    if not key:
        raise Agent0SubgraphError(
            "The Graph Gateway requires an API key: set GRAPH_API_KEY or INTEGRITY_AGENT0_SUBGRAPH_URL"
        )
    return f"https://gateway.thegraph.com/api/{key}/subgraphs/id/{sid}"


@dataclass(frozen=True)
class Agent0Agent:
    entity_id: str  # "chainId:agentId"
    chain_id: int
    agent_id: int
    owner: str
    agent_wallet: Optional[str]
    agent_uri: Optional[str]
    total_feedback: int
    name: Optional[str] = None
    description: Optional[str] = None
    did: Optional[str] = None
    mcp_endpoint: Optional[str] = None
    a2a_endpoint: Optional[str] = None
    x402_support: bool = False
    active: Optional[bool] = None
    supported_trust: list[str] = field(default_factory=list)
    oasf_skills: list[str] = field(default_factory=list)

    @property
    def integrity_did(self) -> Optional[str]:
        return self.did if self.did and self.did.startswith("did:integrity:") else None


@dataclass(frozen=True)
class AisFeedbackRecord:
    feedback_id: str
    client_address: str
    feedback_index: int
    score_bps: int
    tag2: Optional[str]
    created_at: int
    document: Optional[dict[str, Any]]  # decoded off-chain AIS doc, if present + verified
    hash_verified: bool


def _post(url: str, query: str, variables: dict[str, Any], timeout: float) -> dict[str, Any]:
    try:
        resp = requests.post(url, json={"query": query, "variables": variables}, timeout=timeout)
    except requests.RequestException as exc:
        raise Agent0SubgraphError(f"subgraph unreachable: {exc}") from exc
    try:
        payload = resp.json()
    except ValueError as exc:
        raise Agent0SubgraphError(f"non-JSON response ({resp.status_code}): {resp.text[:200]}") from exc
    if resp.status_code != 200 or payload.get("errors"):
        raise Agent0SubgraphError(f"subgraph error ({resp.status_code}): {payload.get('errors') or resp.text[:200]}")
    return payload.get("data") or {}


def _parse_agent(row: dict[str, Any]) -> Agent0Agent:
    reg = row.get("registrationFile") or {}
    return Agent0Agent(
        entity_id=row["id"],
        chain_id=int(row["chainId"]),
        agent_id=int(row["agentId"]),
        owner=Web3.to_checksum_address(row["owner"]),
        agent_wallet=Web3.to_checksum_address(row["agentWallet"]) if row.get("agentWallet") else None,
        agent_uri=row.get("agentURI"),
        total_feedback=int(row.get("totalFeedback") or 0),
        name=reg.get("name"),
        description=reg.get("description"),
        did=reg.get("did"),
        mcp_endpoint=reg.get("mcpEndpoint"),
        a2a_endpoint=reg.get("a2aEndpoint"),
        x402_support=bool(reg.get("x402Support")),
        active=reg.get("active"),
        supported_trust=list(reg.get("supportedTrusts") or []),
        oasf_skills=list(reg.get("oasfSkills") or []),
    )


def list_agents(
    chain_id: int = 84532,
    *,
    first: int = 50,
    skip: int = 0,
    integrity_only: bool = False,
    url: Optional[str] = None,
    timeout: float = 20.0,
) -> list[Agent0Agent]:
    """Most recently active agents; `integrity_only` keeps those with a did:integrity backlink."""
    where = '{registrationFile_: {did_starts_with: "did:integrity:"}}' if integrity_only else "{}"
    query = (
        f"query($first:Int!,$skip:Int!){{ agents(first:$first, skip:$skip, where:{where}, "
        f"orderBy: lastActivity, orderDirection: desc) {{ {_AGENT_FIELDS} }} }}"
    )
    data = _post(url or subgraph_url(chain_id), query, {"first": min(first, 1000), "skip": skip}, timeout)
    return [_parse_agent(r) for r in data.get("agents", [])]


def get_agent(chain_id: int, agent_id: int, *, url: Optional[str] = None, timeout: float = 20.0) -> Optional[Agent0Agent]:
    query = f"query($id:ID!){{ agent(id:$id) {{ {_AGENT_FIELDS} }} }}"
    data = _post(url or subgraph_url(chain_id), query, {"id": f"{chain_id}:{agent_id}"}, timeout)
    row = data.get("agent")
    return _parse_agent(row) if row else None


def decode_feedback_data_uri(uri: Optional[str], feedback_hash: Optional[str]) -> tuple[Optional[dict[str, Any]], bool]:
    """Decode a base64 JSON data URI and verify keccak256(body) == on-chain feedbackHash."""
    if not uri or not uri.startswith(_DATA_URI_PREFIX):
        return None, False
    try:
        body = base64.b64decode(uri[len(_DATA_URI_PREFIX):], validate=True)
        doc = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None, False
    if not isinstance(doc, dict):
        return None, False
    verified = bool(feedback_hash) and Web3.keccak(body).hex().removeprefix("0x") == feedback_hash.lower().removeprefix("0x")
    return doc, verified


def _score_bps(value: str) -> Optional[int]:
    try:
        bps = (Decimal(value) * 100).to_integral_value()
    except (InvalidOperation, TypeError):
        return None
    return int(bps) if 0 <= bps <= 10000 else None


def ais_feedback_history(
    chain_id: int,
    agent_id: int,
    trusted_scorers: list[str],
    *,
    tag1: str = "ais",
    first: int = 100,
    url: Optional[str] = None,
    timeout: float = 20.0,
) -> list[AisFeedbackRecord]:
    """Non-revoked AIS feedback from trusted scorers, newest first.

    Filtering by scorer address is mandatory: ERC-8004 feedback is permissionless and
    Sybil-exposed, and agents carry unrelated tags (Glicko ratings, latency, etc.).
    """
    if not trusted_scorers:
        raise ValueError("trusted_scorers must be non-empty (Sybil resistance)")
    clients = [Web3.to_checksum_address(a).lower() for a in trusted_scorers]
    query = (
        "query($agent:String!,$tag:String!,$clients:[Bytes!]!,$first:Int!){ feedbacks("
        "first:$first, orderBy: createdAt, orderDirection: desc, "
        "where:{agent:$agent, tag1:$tag, clientAddress_in:$clients, isRevoked:false})"
        f"{{ {_FEEDBACK_FIELDS} }} }}"
    )
    variables = {"agent": f"{chain_id}:{agent_id}", "tag": tag1, "clients": clients, "first": min(first, 1000)}
    data = _post(url or subgraph_url(chain_id), query, variables, timeout)

    out: list[AisFeedbackRecord] = []
    for row in data.get("feedbacks", []):
        bps = _score_bps(row.get("value"))
        if bps is None:
            continue
        doc, ok = decode_feedback_data_uri(row.get("feedbackURI"), row.get("feedbackHash"))
        if doc is not None and ok:
            ais = doc.get("ais") if isinstance(doc.get("ais"), dict) else {}
            # Off-chain doc must agree with the on-chain value, else ignore the document.
            if ais.get("scoreBps") != bps or int(doc.get("agentId", -1)) != int(agent_id):
                doc, ok = None, False
        out.append(
            AisFeedbackRecord(
                feedback_id=row["id"],
                client_address=Web3.to_checksum_address(row["clientAddress"]),
                feedback_index=int(row["feedbackIndex"]),
                score_bps=bps,
                tag2=row.get("tag2"),
                created_at=int(row["createdAt"]),
                document=doc if ok else None,
                hash_verified=ok,
            )
        )
    return out


def latest_ais_score(chain_id: int, agent_id: int, trusted_scorers: list[str], **kw: Any) -> Optional[int]:
    hist = ais_feedback_history(chain_id, agent_id, trusted_scorers, first=1, **kw)
    return hist[0].score_bps if hist else None


__all__ = [
    "AGENT0_SUBGRAPH_IDS",
    "Agent0Agent",
    "Agent0SubgraphError",
    "AisFeedbackRecord",
    "ais_feedback_history",
    "decode_feedback_data_uri",
    "get_agent",
    "latest_ais_score",
    "list_agents",
    "subgraph_url",
]
