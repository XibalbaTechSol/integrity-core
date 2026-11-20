"""`integrity erc8004`: Modular ERC-8004 / Agent0 Public Passport Bridge commands.

Commands:
- `integrity erc8004 card`: Build and output a canonical ERC-8004 registration-v1 JSON document
  (and `data:` URI) carrying the two-way Integrity DID backlink (`services[name=DID]`) and CAIP-10
  registry identifier (`eip155:<chain_id>:<registry>`).
- `integrity erc8004 publish`: Mint an ERC-8004 Public Passport on-chain, bind the agent's
  policy-confined `SovereignAgent` actor address as `agentWallet` when registered on-chain, and
  verify the two-way binding with the Integrity Oracle (`POST /v1/agent/{did}/erc8004`).
- `integrity erc8004 link`: Verify and record an existing on-chain ERC-8004 token ID with the
  Integrity Oracle (`POST /v1/agent/{did}/erc8004`).
- `integrity erc8004 status`: Query the agent's verified ERC-8004 discovery record from the
  Integrity Oracle (`GET /v1/agent/{did}/erc8004`).
- `integrity erc8004 feedback`: Post an on-chain AIS reputation feedback item to ReputationRegistry
  referencing an off-chain canonical data URI document committed via Keccak-256 hash.
- `integrity erc8004 reputation`: Query on-chain reputation summary and decode AIS score.
- `integrity erc8004 query`: Discover registered agents or read AIS history via Agent0 Subgraph.
"""
from __future__ import annotations

import dataclasses
from typing import List, Optional

import typer

from integrity_sdk import agent0_subgraph, erc8004

from . import chain, config, identity, output, wallet

erc8004_app = typer.Typer(
    help="Modular ERC-8004 / Agent0 Public Passport Bridge (two-way DID binding & confined SovereignAgent wallet)"
)


def _resolve_did(rep: output.Reporter, agent: Optional[str], identity_name: str) -> str:
    if agent is not None:
        return agent.strip()
    if not identity.identity_exists(identity_name):
        rep.fail(
            output.EXIT_NO,
            f"no AGENT given and no local identity {identity_name!r}; pass --did or run `integrity identity new`",
            code="NO_IDENTITY",
        )
    return identity.did_document(identity_name)["id"]


@erc8004_app.command("card")
def erc8004_card(
    name: str = typer.Option(..., "--name", help="Public agent display name"),
    description: str = typer.Option(..., "--description", help="Public agent capability description"),
    image: str = typer.Option(
        "https://integrity.xibalba.solutions/agent-avatar.png", "--image", help="Public agent image URI"
    ),
    did: Optional[str] = typer.Option(None, "--did", help="Agent DID (default: local --identity's DID)"),
    identity_name: str = typer.Option("default", "--identity", help="Local identity name when --did is omitted"),
    chain_id: int = typer.Option(erc8004.BASE_SEPOLIA_CHAIN_ID, "--chain-id", help="EVM chain ID for CAIP-10 registry ref"),
    registry: str = typer.Option(
        erc8004.BASE_SEPOLIA_ERC8004_REGISTRY, "--registry", help="ERC-8004 Identity Registry address"
    ),
    token_id: str = typer.Option("0", "--token-id", help="ERC-8004 token ID for registrations[] backlink"),
    mcp_endpoint: Optional[str] = typer.Option(None, "--mcp", help="Optional public MCP service endpoint"),
    a2a_endpoint: Optional[str] = typer.Option(None, "--a2a", help="Optional public A2A service endpoint"),
    a2a_version: str = typer.Option("0.3.0", "--a2a-version", help="A2A protocol version"),
    skills: Optional[List[str]] = typer.Option(None, "--skill", help="OASF skill capability (repeatable)"),
    domains: Optional[List[str]] = typer.Option(None, "--domain", help="OASF domain capability (repeatable)"),
    ens: Optional[str] = typer.Option(None, "--ens", help="ENS domain (e.g. agent.eth)"),
    web_endpoint: Optional[str] = typer.Option(None, "--web", help="Web service URL"),
    x402_support: bool = typer.Option(False, "--x402", help="Advertise HTTP x402 payment support"),
    json_output: bool = typer.Option(False, "--json", help=output.JSON_OPTION_HELP),
) -> None:
    """Build a canonical ERC-8004 registration-v1 JSON card with a two-way Integrity DID backlink."""
    rep = output.Reporter("erc8004", "card", json_mode=json_output)
    agent_did = _resolve_did(rep, did, identity_name)
    try:
        doc = erc8004.build_registration_document(
            did=agent_did,
            name=name,
            description=description,
            image=image,
            chain_id=chain_id,
            registry_address=registry,
            token_id=token_id,
            mcp_endpoint=mcp_endpoint,
            a2a_endpoint=a2a_endpoint,
            a2a_version=a2a_version,
            oasf_skills=skills,
            oasf_domains=domains,
            ens=ens,
            web_endpoint=web_endpoint,
            x402_support=x402_support,
        )
        data_uri, sha256_hex = erc8004.encode_registration_data_uri(doc)
    except ValueError as exc:
        rep.fail(output.EXIT_NO, str(exc), code="INVALID_CARD")

    caip10 = erc8004.caip10_registry(chain_id, registry)
    rep.info(f"DID:       {agent_did}")
    rep.info(f"CAIP-10:   {caip10} (token {token_id})")
    rep.info(f"SHA-256:   {sha256_hex}")
    rep.info(f"Data URI:  {data_uri[:72]}...")
    rep.result(
        {
            "agent_id": agent_did,
            "caip10_registry": caip10,
            "token_id": str(token_id),
            "sha256": sha256_hex,
            "data_uri": data_uri,
            "document": doc,
        }
    )


@erc8004_app.command("link")
def erc8004_link(
    token_id: str = typer.Option(..., "--token-id", help="Minted ERC-8004 token ID (uint256)"),
    registry: str = typer.Option(
        erc8004.BASE_SEPOLIA_ERC8004_REGISTRY, "--registry", help="ERC-8004 Identity Registry contract address"
    ),
    chain_id: int = typer.Option(erc8004.BASE_SEPOLIA_CHAIN_ID, "--chain-id", help="EVM chain ID"),
    did: Optional[str] = typer.Option(None, "--did", help="Agent DID (default: local --identity's DID)"),
    identity_name: str = typer.Option("default", "--identity", help="Local identity name when --did is omitted"),
    oracle_url: Optional[str] = typer.Option(None, "--oracle-url", help="Integrity Oracle base URL"),
    json_output: bool = typer.Option(False, "--json", help=output.JSON_OPTION_HELP),
) -> None:
    """Verify and bind an on-chain ERC-8004 token ID to an Integrity DID at the Oracle."""
    rep = output.Reporter("erc8004", "link", json_mode=json_output)
    agent_did = _resolve_did(rep, did, identity_name)
    oracle_url = oracle_url or config.get_config_value("ORACLE_URL")
    try:
        binding = erc8004.link_erc8004_with_oracle(
            oracle_url,
            agent_did,
            chain_id=chain_id,
            identity_registry_address=registry,
            agent_token_id=token_id,
        )
    except erc8004.Erc8004BridgeError as exc:
        if exc.unreachable:
            rep.fail(
                output.EXIT_UNVERIFIED,
                f"Oracle unreachable at {oracle_url}: {exc.detail}",
                code="UNREACHABLE" if exc.status is None else f"HTTP_{exc.status}",
            )
        rep.fail(
            output.EXIT_NO,
            f"Oracle rejected ERC-8004 binding ({exc.status}): {exc.detail}",
            code=f"HTTP_{exc.status}" if exc.status is not None else "REJECTED",
        )
    except ValueError as exc:
        rep.fail(output.EXIT_NO, str(exc), code="INVALID_ARGUMENT")

    rep.info(
        f"verified {binding.agent_id} <-> eip155:{binding.chain_id}:{binding.identity_registry_address.lower()}#{binding.agent_token_id} "
        f"(wallet={binding.agent_wallet_address or 'none'} confined={binding.wallet_confined})"
    )
    rep.result({"binding": dataclasses.asdict(binding), "oracle_url": oracle_url})


@erc8004_app.command("status")
def erc8004_status(
    did: Optional[str] = typer.Argument(None, help="Agent DID (default: local --identity's DID)"),
    identity_name: str = typer.Option("default", "--identity", help="Local identity name when DID is omitted"),
    oracle_url: Optional[str] = typer.Option(None, "--oracle-url", help="Integrity Oracle base URL"),
    json_output: bool = typer.Option(False, "--json", help=output.JSON_OPTION_HELP),
) -> None:
    """Query the verified ERC-8004 Public Passport binding for an Integrity DID."""
    rep = output.Reporter("erc8004", "status", json_mode=json_output)
    agent_did = _resolve_did(rep, did, identity_name)
    oracle_url = oracle_url or config.get_config_value("ORACLE_URL")
    try:
        binding = erc8004.get_erc8004_from_oracle(oracle_url, agent_did)
    except erc8004.Erc8004BridgeError as exc:
        if exc.unreachable:
            rep.fail(
                output.EXIT_UNVERIFIED,
                f"Oracle unreachable at {oracle_url}: {exc.detail}",
                code="UNREACHABLE" if exc.status is None else f"HTTP_{exc.status}",
            )
        rep.fail(
            output.EXIT_NO,
            f"ERC-8004 status failed ({exc.status}): {exc.detail}",
            code=f"HTTP_{exc.status}" if exc.status is not None else "NOT_FOUND",
        )

    if binding is None:
        rep.info(f"{agent_did}: no ERC-8004 binding recorded")
        rep.result({"agent_id": agent_did, "linked": False, "binding": None, "oracle_url": oracle_url})
        return

    rep.info(
        f"{agent_did}: {binding.get('binding_status')} token={binding.get('agent_token_id')} "
        f"registry={binding.get('identity_registry_address')} wallet={binding.get('agent_wallet_address') or 'none'}"
    )
    rep.result({"agent_id": agent_did, "linked": True, "binding": binding, "oracle_url": oracle_url})


@erc8004_app.command("publish")
def erc8004_publish(
    name: str = typer.Option(..., "--name", help="Public agent display name"),
    description: str = typer.Option(..., "--description", help="Public agent capability description"),
    image: str = typer.Option(
        "https://integrity.xibalba.solutions/agent-avatar.png", "--image", help="Public agent image URI"
    ),
    registry: str = typer.Option(
        erc8004.BASE_SEPOLIA_ERC8004_REGISTRY, "--registry", help="ERC-8004 Identity Registry contract address"
    ),
    identity_name: str = typer.Option("default", "--identity", help="Local identity & guardian wallet name"),
    mcp_endpoint: Optional[str] = typer.Option(None, "--mcp", help="Optional public MCP service endpoint"),
    a2a_endpoint: Optional[str] = typer.Option(None, "--a2a", help="Optional public A2A service endpoint"),
    a2a_version: str = typer.Option("0.3.0", "--a2a-version", help="A2A protocol version"),
    skills: Optional[List[str]] = typer.Option(None, "--skill", help="OASF skill capability (repeatable)"),
    domains: Optional[List[str]] = typer.Option(None, "--domain", help="OASF domain capability (repeatable)"),
    ens: Optional[str] = typer.Option(None, "--ens", help="ENS domain (e.g. agent.eth)"),
    web_endpoint: Optional[str] = typer.Option(None, "--web", help="Web service URL"),
    x402_support: bool = typer.Option(False, "--x402", help="Advertise HTTP x402 payment support"),
    oracle_url: Optional[str] = typer.Option(None, "--oracle-url", help="Integrity Oracle base URL"),
    rpc_url: Optional[str] = typer.Option(None, "--rpc-url", help="EVM RPC endpoint"),
    deployments_file: Optional[str] = typer.Option(None, "--deployments-file", help="Deployments JSON path"),
    json_output: bool = typer.Option(False, "--json", help=output.JSON_OPTION_HELP),
) -> None:
    """Mint an ERC-8004 Public Passport on-chain with confined SovereignAgent wallet & two-way DID binding, then verify with Oracle."""
    rep = output.Reporter("erc8004", "publish", json_mode=json_output)
    agent_did = _resolve_did(rep, None, identity_name)
    oracle_url = oracle_url or config.get_config_value("ORACLE_URL")
    rpc_url = rpc_url or config.get_config_value("RPC_URL")
    deployments_file = deployments_file or config.get_config_value("DEPLOYMENTS_FILE")

    agent_registry_address: Optional[str] = None
    try:
        agent_registry_address = chain.load_deployments(deployments_file).get("singletons", {}).get("AgentRegistry")
    except (chain.DeploymentsFileMissing, OSError, ValueError):
        agent_registry_address = None

    try:
        guardian = wallet.generate_or_load_evm_wallet(identity_name)
    except wallet.WalletPasswordNotSet as exc:
        rep.fail(output.EXIT_NO, str(exc), code="WALLET_PASSWORD")

    w3 = chain.get_w3(rpc_url)
    try:
        binding, tx_hash = erc8004.register_and_link_erc8004(
            w3,
            oracle_url,
            agent_did,
            guardian,
            name=name,
            description=description,
            image=image,
            identity_registry_address=registry,
            agent_registry_address=agent_registry_address,
            mcp_endpoint=mcp_endpoint,
            a2a_endpoint=a2a_endpoint,
            a2a_version=a2a_version,
            oasf_skills=skills,
            oasf_domains=domains,
            ens=ens,
            web_endpoint=web_endpoint,
            x402_support=x402_support,
        )
    except erc8004.Erc8004BridgeError as exc:
        if exc.unreachable:
            rep.fail(
                output.EXIT_UNVERIFIED,
                f"Oracle unreachable at {oracle_url}: {exc.detail}",
                code="UNREACHABLE" if exc.status is None else f"HTTP_{exc.status}",
            )
        rep.fail(
            output.EXIT_NO,
            f"Oracle rejected ERC-8004 binding ({exc.status}): {exc.detail}",
            code=f"HTTP_{exc.status}" if exc.status is not None else "REJECTED",
        )
    except Exception as exc:  # noqa: BLE001
        exit_code = output.exit_code_for_chain_error(exc)
        rep.fail(
            exit_code,
            f"ERC-8004 on-chain publish failed: {exc}",
            code="REVERT" if exit_code == output.EXIT_REVERT else ("UNREACHABLE" if exit_code == output.EXIT_UNVERIFIED else "CHAIN"),
        )

    rep.info(
        f"published ERC-8004 token={binding.agent_token_id} tx={tx_hash} "
        f"wallet={binding.agent_wallet_address or 'none'} confined={binding.wallet_confined}"
    )
    rep.result({"binding": dataclasses.asdict(binding), "tx": tx_hash, "oracle_url": oracle_url})


@erc8004_app.command("feedback")
def erc8004_feedback(
    token_id: int = typer.Option(..., "--token-id", help="Target agent token ID (uint256)"),
    score_bps: int = typer.Option(..., "--score-bps", min=0, max=10000, help="AIS score in basis points (0..10000, 9850 = 98.50%)"),
    evidence_root: Optional[str] = typer.Option(None, "--evidence-root", help="Hex Merkle root or provenance commitment"),
    reputation_registry: str = typer.Option(
        erc8004.BASE_SEPOLIA_ERC8004_REPUTATION_REGISTRY,
        "--reputation-registry",
        help="ERC-8004 Reputation Registry contract address",
    ),
    identity_registry: str = typer.Option(
        erc8004.BASE_SEPOLIA_ERC8004_REGISTRY,
        "--identity-registry",
        help="ERC-8004 Identity Registry contract address",
    ),
    chain_id: int = typer.Option(erc8004.BASE_SEPOLIA_CHAIN_ID, "--chain-id", help="EVM chain ID"),
    tag1: str = typer.Option("ais", "--tag1", help="Primary taxonomy tag (default: 'ais')"),
    tag2: str = typer.Option("oracle", "--tag2", help="Secondary taxonomy tag (default: 'oracle')"),
    endpoint: Optional[str] = typer.Option(None, "--endpoint", help="Evaluated agent endpoint"),
    identity_name: str = typer.Option("default", "--identity", help="Client signer identity profile"),
    rpc_url: Optional[str] = typer.Option(None, "--rpc-url", help="EVM RPC endpoint"),
    json_output: bool = typer.Option(False, "--json", help=output.JSON_OPTION_HELP),
) -> None:
    """Submit an on-chain AIS reputation rating referencing an off-chain canonical data URI document."""
    rep = output.Reporter("erc8004", "feedback", json_mode=json_output)
    rpc_url = rpc_url or config.get_config_value("RPC_URL")

    try:
        signer = wallet.generate_or_load_evm_wallet(identity_name)
    except wallet.WalletPasswordNotSet as exc:
        rep.fail(output.EXIT_NO, str(exc), code="WALLET_PASSWORD")

    w3 = chain.get_w3(rpc_url)
    try:
        tx_hash, uri, f_hash = erc8004.give_ais_feedback(
            w3,
            signer,
            reputation_registry,
            token_id,
            ais_score_bps=score_bps,
            chain_id=chain_id,
            identity_registry_address=identity_registry,
            evidence_root=evidence_root,
            endpoint=endpoint,
            tag1=tag1,
            tag2=tag2,
        )
    except erc8004.Erc8004BridgeError as exc:
        rep.fail(output.EXIT_NO, exc.detail, code="FORBIDDEN")
    except Exception as exc:  # noqa: BLE001
        exit_code = output.exit_code_for_chain_error(exc)
        rep.fail(
            exit_code,
            f"giveFeedback failed: {exc}",
            code="REVERT" if exit_code == output.EXIT_REVERT else "CHAIN",
        )

    rep.info(f"submitted AIS feedback for agent={token_id} score={score_bps}bps tx={tx_hash}")
    rep.result(
        {
            "schema": "integrity.cli.erc8004.feedback.v1",
            "agent_id": token_id,
            "score_bps": score_bps,
            "score_percent": round(score_bps / 100.0, 2),
            "tx_hash": tx_hash,
            "feedback_uri": uri,
            "feedback_hash": f_hash.hex() if hasattr(f_hash, "hex") else str(f_hash),
            "client_address": signer.address,
        }
    )


@erc8004_app.command("reputation")
def erc8004_reputation(
    token_id: int = typer.Option(..., "--token-id", help="Target agent token ID (uint256)"),
    trusted_scorer: Optional[List[str]] = typer.Option(
        None, "--trusted-scorer", help="Trusted scorer EVM address (repeatable, for Sybil resistance)"
    ),
    reputation_registry: str = typer.Option(
        erc8004.BASE_SEPOLIA_ERC8004_REPUTATION_REGISTRY,
        "--reputation-registry",
        help="ERC-8004 Reputation Registry contract address",
    ),
    tag1: str = typer.Option("ais", "--tag1", help="Primary taxonomy tag filter"),
    rpc_url: Optional[str] = typer.Option(None, "--rpc-url", help="EVM RPC endpoint"),
    json_output: bool = typer.Option(False, "--json", help=output.JSON_OPTION_HELP),
) -> None:
    """Read on-chain ERC-8004 reputation summary and filter verified AIS score."""
    rep = output.Reporter("erc8004", "reputation", json_mode=json_output)
    rpc_url = rpc_url or config.get_config_value("RPC_URL")
    w3 = chain.get_w3(rpc_url)

    try:
        summary = erc8004.read_agent_reputation(
            w3,
            reputation_registry,
            token_id,
            tag1=tag1,
        )
    except Exception as exc:  # noqa: BLE001
        exit_code = output.exit_code_for_chain_error(exc)
        rep.fail(exit_code, f"reading reputation failed: {exc}", code="CHAIN")

    ais_bps: Optional[int] = None
    if trusted_scorer:
        try:
            ais_bps = erc8004.ais_score_from_reputation(summary, trusted_scorer, tag1=tag1)
        except ValueError as exc:
            rep.fail(output.EXIT_NO, str(exc), code="SCORER_FILTER")

    rep.result(
        {
            "schema": "integrity.cli.erc8004.reputation.v1",
            "agent_id": token_id,
            "count": summary.count,
            "summary_value": summary.summary_value,
            "summary_value_decimals": summary.summary_value_decimals,
            "ais_score_bps": ais_bps,
            "ais_score_percent": round(ais_bps / 100.0, 2) if ais_bps is not None else None,
            "clients": summary.clients,
            "feedbacks_count": len(summary.feedbacks),
        }
    )


@erc8004_app.command("subgraph")
def erc8004_subgraph(
    token_id: Optional[int] = typer.Option(None, "--token-id", help="Agent token ID to inspect"),
    chain_id: int = typer.Option(erc8004.BASE_SEPOLIA_CHAIN_ID, "--chain-id", help="Chain ID (default: 84532)"),
    trusted_scorer: Optional[List[str]] = typer.Option(
        None, "--trusted-scorer", help="Trusted scorer EVM address for AIS history filter"
    ),
    integrity_only: bool = typer.Option(False, "--integrity-only", help="Only list agents with did:integrity: backlink"),
    first: int = typer.Option(20, "--first", help="Maximum records to return"),
    json_output: bool = typer.Option(False, "--json", help=output.JSON_OPTION_HELP),
) -> None:
    """Query Agent0 Subgraph for indexed ERC-8004 agent passports or AIS feedback history."""
    rep = output.Reporter("erc8004", "subgraph", json_mode=json_output)

    try:
        if token_id is not None:
            agent = agent0_subgraph.get_agent(chain_id, token_id)
            history = (
                agent0_subgraph.ais_feedback_history(chain_id, token_id, trusted_scorer, first=first)
                if trusted_scorer
                else []
            )
            rep.result(
                {
                    "schema": "integrity.cli.erc8004.subgraph.agent.v1",
                    "agent": dataclasses.asdict(agent) if agent else None,
                    "ais_history": [dataclasses.asdict(h) for h in history],
                }
            )
            return

        agents = agent0_subgraph.list_agents(chain_id, first=first, integrity_only=integrity_only)
        rep.result(
            {
                "schema": "integrity.cli.erc8004.subgraph.list.v1",
                "count": len(agents),
                "agents": [dataclasses.asdict(a) for a in agents],
            }
        )
    except agent0_subgraph.Agent0SubgraphError as exc:
        rep.fail(output.EXIT_UNVERIFIED, str(exc), code="SUBGRAPH_ERROR")


@erc8004_app.command("search")
def erc8004_search(
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Search text in agent name, description, DID, or skills"),
    skill: Optional[str] = typer.Option(None, "--skill", help="Filter by OASF skill (substring match)"),
    domain: Optional[str] = typer.Option(None, "--domain", help="Filter by OASF domain (substring match)"),
    min_ais: Optional[int] = typer.Option(None, "--min-ais", min=0, max=10000, help="Minimum AIS reputation score (bps, 0..10000)"),
    trusted_scorer: Optional[List[str]] = typer.Option(
        None, "--trusted-scorer", help="Trusted scorer EVM address (repeatable)"
    ),
    mcp: bool = typer.Option(False, "--mcp", help="Require an MCP endpoint"),
    a2a: bool = typer.Option(False, "--a2a", help="Require an A2A endpoint"),
    x402: bool = typer.Option(False, "--x402", help="Require x402 payment support"),
    confined_wallet: bool = typer.Option(False, "--confined-wallet", help="Require a bound agentWallet"),
    integrity_only: bool = typer.Option(False, "--integrity-only", help="Only agents with did:integrity: backlink"),
    active_only: bool = typer.Option(False, "--active", help="Only active agents"),
    min_feedback: int = typer.Option(0, "--min-feedback", min=0, help="Minimum total feedback count"),
    order_by: str = typer.Option("ais", "--order-by", help="Sort order: ais, totalFeedback, or lastActivity"),
    chain_id: int = typer.Option(erc8004.BASE_SEPOLIA_CHAIN_ID, "--chain-id", help="Chain ID (default: 84532)"),
    first: int = typer.Option(20, "--first", help="Maximum results to return"),
    json_output: bool = typer.Option(False, "--json", help=output.JSON_OPTION_HELP),
) -> None:
    """Search ERC-8004 agents by AIS reputation, OASF skills, protocol endpoints, and Integrity binding."""
    rep = output.Reporter("erc8004", "search", json_mode=json_output)

    try:
        results = agent0_subgraph.search_agents(
            chain_id,
            query_text=query,
            skill=skill,
            domain=domain,
            min_ais_bps=min_ais,
            trusted_scorers=trusted_scorer,
            mcp_required=mcp,
            a2a_required=a2a,
            x402_required=x402,
            confined_wallet_only=confined_wallet,
            integrity_only=integrity_only,
            active_only=active_only,
            min_feedback=min_feedback,
            order_by=order_by,
            first=first,
        )
    except (agent0_subgraph.Agent0SubgraphError, ValueError) as exc:
        code = "SUBGRAPH_ERROR" if isinstance(exc, agent0_subgraph.Agent0SubgraphError) else "INVALID_FILTER"
        rep.fail(output.EXIT_UNVERIFIED if isinstance(exc, agent0_subgraph.Agent0SubgraphError) else output.EXIT_NO, str(exc), code=code)

    rep.info(f"found {len(results)} matching ERC-8004 agents on chain {chain_id}")
    rep.result(
        {
            "schema": "integrity.cli.erc8004.search.v1",
            "chain_id": chain_id,
            "count": len(results),
            "results": [dataclasses.asdict(r) for r in results],
        }
    )
