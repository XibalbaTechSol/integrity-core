"""`integrity status [AGENT]`: one view of an agent, folding the old `agent show` / `agent ais`.

Off-chain state comes from the Oracle. The on-chain record/actor/trust rows need AgentRegistry
(registration v3 PR 3.2) and report "pending" until it lands -- never a guessed pass or fail.

Exit: 0 registered, 1 not registered / no identity, 3 Oracle unreachable or 5xx.
"""
from __future__ import annotations

from typing import Any, Optional

import typer

from . import config, identity, output
from .client import ApiError, IntegrityClient

PENDING_V3 = "not wired yet: needs the AgentRegistry read path (registration v3 PR 3.2); CLI follow-up"


def status(
    agent: Optional[str] = typer.Argument(None, help="Agent DID (default: the local --identity's DID)"),
    identity_name: str = typer.Option("default", "--identity", help="Local identity used when AGENT is omitted"),
    oracle_url: Optional[str] = typer.Option(None, "--oracle-url", help="integrity-oracle base URL (env/profile/config ORACLE_URL)"),
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
    onchain = {k: {"status": "pending", "detail": PENDING_V3} for k in ("record", "actor", "trust")}
    doc: dict[str, Any] = {"agent_id": agent, "identity": local_name, "oracle_url": oracle_url, "onchain": onchain}

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
