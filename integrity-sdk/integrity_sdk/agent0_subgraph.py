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

_AGENT_WITH_FEEDBACK_FIELDS = f"""
  {_AGENT_FIELDS}
  feedback(where: {{ isRevoked: false, tag1: "ais" }}, orderBy: createdAt, orderDirection: desc, first: 10) {{
    {_FEEDBACK_FIELDS}
  }}
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
    oasf_domains: list[str] = field(default_factory=list)

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


@dataclass(frozen=True)
class AgentSearchResult:
    """Search result pairing an indexed ERC-8004 agent with verified AIS reputation."""
    agent: Agent0Agent
    ais_score_bps: Optional[int]
    ais_score_percent: Optional[float]
    verified_scorer: Optional[str]
    recent_feedbacks: list[AisFeedbackRecord] = field(default_factory=list)


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
        oasf_domains=list(reg.get("oasfDomains") or []),
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
        rec = _parse_ais_feedback_row(row, agent_id)
        if rec is not None:
            out.append(rec)
    return out


def _parse_ais_feedback_row(row: dict[str, Any], agent_id: int) -> Optional[AisFeedbackRecord]:
    bps = _score_bps(row.get("value"))
    if bps is None:
        return None
    doc, ok = decode_feedback_data_uri(row.get("feedbackURI"), row.get("feedbackHash"))
    if doc is not None and ok:
        ais = doc.get("ais") if isinstance(doc.get("ais"), dict) else {}
        # Off-chain doc must agree with the on-chain value, else ignore the document.
        if ais.get("scoreBps") != bps or int(doc.get("agentId", -1)) != int(agent_id):
            doc, ok = None, False
    return AisFeedbackRecord(
        feedback_id=row["id"],
        client_address=Web3.to_checksum_address(row["clientAddress"]),
        feedback_index=int(row["feedbackIndex"]),
        score_bps=bps,
        tag2=row.get("tag2"),
        created_at=int(row["createdAt"]),
        document=doc if ok else None,
        hash_verified=ok,
    )


def latest_ais_score(chain_id: int, agent_id: int, trusted_scorers: list[str], **kw: Any) -> Optional[int]:
    hist = ais_feedback_history(chain_id, agent_id, trusted_scorers, first=1, **kw)
    return hist[0].score_bps if hist else None


def search_agents(
    chain_id: int = 84532,
    *,
    query_text: Optional[str] = None,
    skill: Optional[str] = None,
    domain: Optional[str] = None,
    min_ais_bps: Optional[int] = None,
    trusted_scorers: Optional[list[str]] = None,
    mcp_required: bool = False,
    a2a_required: bool = False,
    x402_required: bool = False,
    confined_wallet_only: bool = False,
    integrity_only: bool = False,
    active_only: bool = False,
    min_feedback: int = 0,
    order_by: str = "ais",
    first: int = 20,
    skip: int = 0,
    url: Optional[str] = None,
    timeout: float = 20.0,
) -> list[AgentSearchResult]:
    """Search ERC-8004 agents by AIS reputation, OASF skills/domains, protocol endpoints, and Integrity binding."""
    if min_ais_bps is not None and not (0 <= min_ais_bps <= 10000):
        raise ValueError(f"min_ais_bps must be in 0..10000, got {min_ais_bps}")

    reg_filters: list[str] = []
    if integrity_only:
        reg_filters.append('did_starts_with: "did:integrity:"')
    if active_only:
        reg_filters.append("active: true")
    if x402_required:
        reg_filters.append("x402Support: true")

    where_parts: list[str] = []
    if reg_filters:
        where_parts.append("registrationFile_: {" + ", ".join(reg_filters) + "}")
    if min_feedback > 0:
        where_parts.append(f"totalFeedback_gte: {int(min_feedback)}")
    where_clause = "{" + ", ".join(where_parts) + "}" if where_parts else "{}"

    # Fetch a wider window when client-side filtering/sorting is active so `first` is well-populated.
    fetch_limit = min(max(first * 5, 100), 1000)
    gql_order = "totalFeedback" if order_by == "totalFeedback" else "lastActivity"
    query = (
        f"query($first:Int!,$skip:Int!){{ agents(first:$first, skip:$skip, where:{where_clause}, "
        f"orderBy: {gql_order}, orderDirection: desc) {{ {_AGENT_WITH_FEEDBACK_FIELDS} }} }}"
    )
    data = _post(url or subgraph_url(chain_id), query, {"first": fetch_limit, "skip": 0}, timeout)

    trusted_set = {Web3.to_checksum_address(a) for a in trusted_scorers} if trusted_scorers else None
    q_norm = query_text.lower().strip() if query_text else None
    skill_norm = skill.lower().strip() if skill else None
    domain_norm = domain.lower().strip() if domain else None

    results: list[tuple[int, AgentSearchResult]] = []
    for row in data.get("agents", []):
        agent = _parse_agent(row)

        if integrity_only and not agent.integrity_did:
            continue
        if confined_wallet_only and not agent.agent_wallet:
            continue
        if mcp_required and not agent.mcp_endpoint:
            continue
        if a2a_required and not agent.a2a_endpoint:
            continue
        if x402_required and not agent.x402_support:
            continue
        if active_only and agent.active is not True:
            continue
        if agent.total_feedback < min_feedback:
            continue

        if q_norm:
            haystack = " ".join(
                filter(None, [agent.name, agent.description, agent.did, " ".join(agent.oasf_skills)])
            ).lower()
            if q_norm not in haystack:
                continue

        if skill_norm and not any(skill_norm in s.lower() for s in agent.oasf_skills):
            continue
        if domain_norm and not any(domain_norm in d.lower() for d in agent.oasf_domains):
            continue

        feedback_rows = row.get("feedback") or []
        parsed_feedbacks: list[AisFeedbackRecord] = []
        for f_row in feedback_rows:
            if f_row.get("isRevoked"):
                continue
            rec = _parse_ais_feedback_row(f_row, agent.agent_id)
            if rec is None:
                continue
            if trusted_set is not None and rec.client_address not in trusted_set:
                continue
            parsed_feedbacks.append(rec)

        parsed_feedbacks.sort(key=lambda r: (r.created_at, r.feedback_index), reverse=True)
        latest = parsed_feedbacks[0] if parsed_feedbacks else None
        ais_bps = latest.score_bps if latest else None

        if min_ais_bps is not None and (ais_bps is None or ais_bps < min_ais_bps):
            continue

        last_act = int(row.get("lastActivity") or 0)
        results.append(
            (
                last_act,
                AgentSearchResult(
                    agent=agent,
                    ais_score_bps=ais_bps,
                    ais_score_percent=round(ais_bps / 100.0, 2) if ais_bps is not None else None,
                    verified_scorer=latest.client_address if latest else None,
                    recent_feedbacks=parsed_feedbacks,
                ),
            )
        )

    if order_by == "ais":
        results.sort(
            key=lambda item: (
                item[1].ais_score_bps if item[1].ais_score_bps is not None else -1,
                item[1].agent.total_feedback,
                item[0],
            ),
            reverse=True,
        )
    elif order_by == "totalFeedback":
        results.sort(key=lambda item: (item[1].agent.total_feedback, item[0]), reverse=True)
    else:
        results.sort(key=lambda item: item[0], reverse=True)

    return [item[1] for item in results[skip : skip + first]]


__all__ = [
    "AGENT0_SUBGRAPH_IDS",
    "Agent0Agent",
    "Agent0SubgraphError",
    "AgentSearchResult",
    "AisFeedbackRecord",
    "ais_feedback_history",
    "decode_feedback_data_uri",
    "get_agent",
    "latest_ais_score",
    "list_agents",
    "search_agents",
    "subgraph_url",
]
