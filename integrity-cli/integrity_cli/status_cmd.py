"""`integrity status [AGENT]`: one view of an agent, folding the old `agent show` / `agent ais`.

Off-chain state comes from the Oracle. The on-chain rows read the v3 AgentRegistry
(`singletons.AgentRegistry`): `record` is present / absent / retired, `actor` is the bound
SovereignAgent or none. An on-chain record is optional in v3, so "absent" is not a failure; a
read that cannot be made is "unverified", never guessed. `trust` (stake, freeze) is the Phase 4
`trust status` and stays "pending".

Exit: 0 registered with the Oracle, 1 not registered / no identity, 3 Oracle unreachable or 5xx.
The on-chain rows do not change the exit code: they are optional evidence, reported as such.
"""
from __future__ import annotations

from typing import Any, Optional

import typer

from integrity_sdk.chain import get_w3  # noqa: F401  (module-level so tests can patch it)

from . import chain, config, identity, output, policy_cmd
from .client import ApiError, IntegrityClient

_ZERO_ADDR = "0x" + "00" * 20
TRUST_PENDING = "per-agent trust (stake, freeze) is `trust status`, registration v3 Phase 4"


def agent_registry_contract(w3, address: str):
    """Module-level so tests can substitute a fake registry."""
    return chain._contract(w3, "AgentRegistry", address=address)


def onchain_rows(did: str, rpc_url: str, deployments_file: str) -> dict[str, dict[str, Any]]:
    """record/actor/trust rows from AgentRegistry.resolveDID; any read failure -> unverified."""
    trust = {"status": "pending", "detail": TRUST_PENDING}

    def unverified(detail: str) -> dict[str, dict[str, Any]]:
        row = {"status": "unverified", "detail": detail}
        return {"record": row, "actor": dict(row), "trust": trust}

    try:
        deployments = policy_cmd.read_deployments(deployments_file)
    except (OSError, ValueError) as e:
        return unverified(f"cannot read deployments {deployments_file}: {e}")
    address = (deployments.get("singletons") or {}).get("AgentRegistry")
    if not address:
        return unverified(f"no singletons.AgentRegistry in {deployments_file}")
    try:
        w3 = get_w3(rpc_url)
        if not w3.is_connected():
            return unverified(f"RPC unreachable at {rpc_url}")
        rec = agent_registry_contract(w3, address).functions.resolveDID(did).call()
    except Exception as e:  # noqa: BLE001 -- a failed read is "can't tell", never "absent"
        return unverified(f"AgentRegistry read failed: {e}")
    pubkey, _guardian, actor, _domain, _uri, registered_at, retired_at, _proof = rec
    if not any(pubkey):
        record = {"status": "absent", "detail": "no on-chain record (optional in v3)"}
    elif retired_at:
        record = {"status": "retired", "detail": f"retired at {retired_at}", "registered_at": registered_at}
    else:
        record = {"status": "present", "detail": f"registered at {registered_at}", "registered_at": registered_at}
    if actor and actor.lower() != _ZERO_ADDR:
        actor_row = {"status": "bound", "detail": actor, "actor": actor}
    else:
        actor_row = {"status": "none", "detail": "no SovereignAgent bound"}
    return {"record": record, "actor": actor_row, "trust": trust}


def status(
    agent: Optional[str] = typer.Argument(None, help="Agent DID (default: the local --identity's DID)"),
    identity_name: str = typer.Option("default", "--identity", help="Local identity used when AGENT is omitted"),
    oracle_url: Optional[str] = typer.Option(None, "--oracle-url", help="integrity-oracle base URL (env/profile/config ORACLE_URL)"),
    rpc_url: Optional[str] = typer.Option(None, "--rpc-url", help="JSON-RPC endpoint for the on-chain rows (env/profile/config RPC_URL)"),
    deployments_file: Optional[str] = typer.Option(None, "--deployments-file", help="Deployments JSON (env/profile/config DEPLOYMENTS_FILE)"),
    json_output: bool = typer.Option(False, "--json", help=output.JSON_OPTION_HELP),
):
    """Registration, verification tier and AIS for an agent (was `agent show` + `agent ais`)."""
    rep = output.Reporter("status", json_mode=json_output)
    local_name: Optional[str] = None
    if agent is None:
        if not identity.identity_exists(identity_name):
            rep.fail(output.EXIT_NO, f"no AGENT given and no local identity {identity_name!r}; "
                     "pass a DID or run `integrity identity new`", code="NO_IDENTITY")
        agent = identity.did_document(identity_name)["id"]
        local_name = identity_name
    oracle_url = oracle_url or config.get_config_value("ORACLE_URL")
    client = IntegrityClient(base_url=oracle_url)
    doc: dict[str, Any] = {"agent_id": agent, "identity": local_name, "oracle_url": oracle_url}

    try:
        record = client.get(f"/v1/agent/{agent}")
    except ApiError as e:
        if e.status == 404:
            rep.info(f"{agent}\n  registered: [red]no[/red] (Oracle has no record) -- `integrity register`")
            rep.result({**doc, "registered": False, "verification_tier": None, "record": None, "ais": None, "ais_error": None})
            raise typer.Exit(output.EXIT_NO)
        rep.fail(output.EXIT_UNVERIFIED if e.unverified else output.EXIT_NO,
                 f"Oracle lookup failed at {oracle_url}: {e}", code="UNREACHABLE" if e.unverified else f"HTTP_{e.status}")

    ais: Optional[dict] = None
    ais_error: Optional[str] = None
    try:
        ais = client.get(f"/v1/agent/{agent}/ais")
    except ApiError as e:
        ais_error = str(e)  # AIS is supplementary: its failure must not hide a known registration

    onchain = onchain_rows(
        agent,
        rpc_url or config.get_config_value("RPC_URL"),
        deployments_file or config.get_config_value("DEPLOYMENTS_FILE"),
    )
    doc["onchain"] = onchain
    tier = record.get("verification_tier")
    rep.info(agent)
    rep.info(f"  registered: [green]yes[/green] (tier {tier})")
    if ais is not None:
        rep.info(f"  AIS:        {ais.get('ais')}")
    else:
        rep.info(f"  AIS:        [yellow]unavailable[/yellow] ({ais_error})")
    for key, row in onchain.items():
        rep.info(f"  onchain {key}: [yellow]{row['status']}[/yellow] ({row['detail']})")
    rep.result({**doc, "registered": True, "verification_tier": tier, "record": record, "ais": ais, "ais_error": ais_error})
