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
"""
from __future__ import annotations

import dataclasses
from typing import Optional

import typer

from integrity_sdk import erc8004

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
