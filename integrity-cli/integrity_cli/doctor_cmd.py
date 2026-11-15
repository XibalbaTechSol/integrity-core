"""`integrity doctor`: is this machine's view of the network sane? Fails closed.

Each check is pass / fail / unverified / pending / skipped. The exit code is the worst of them:
any unverified -> 3 (something could not be reached, so nothing downstream is trusted), else any
fail -> 1, else 0. "pending" marks checks that need AgentRegistry (registration v3 PR 3.2): they
are listed so nobody mistakes their absence for a pass, and they do not fail the run.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx
import typer

from integrity_sdk.chain import get_w3  # noqa: F401  (module-level so tests can patch it)
from integrity_sdk.policy_registry import graph_root_of  # noqa: F401

from . import config, output, policy_cmd

PENDING = "not wired yet: AgentRegistry landed in registration v3 PR 3.2; the CLI check is a follow-up"


def _check(checks: list, name: str, status: str, detail: str) -> str:
    checks.append({"name": name, "status": status, "detail": detail})
    return status


def doctor(
    deployments_file: Optional[str] = typer.Option(None, "--deployments-file", help="Deployments JSON (env/profile/config DEPLOYMENTS_FILE)"),
    rpc_url: Optional[str] = typer.Option(None, "--rpc-url", help="JSON-RPC endpoint (env/profile/config RPC_URL)"),
    oracle_url: Optional[str] = typer.Option(None, "--oracle-url", help="integrity-oracle base URL (env/profile/config ORACLE_URL)"),
    pack: Optional[str] = typer.Option(None, "--pack", help="Also check this pack's on-chain root against PolicyRegistry"),
    json_output: bool = typer.Option(False, "--json", help=output.JSON_OPTION_HELP),
):
    """Check Oracle, deployments, RPC, chain id and contract code. Exit 0 ok, 1 fail, 3 unverified."""
    rep = output.Reporter("doctor", json_mode=json_output)
    deployments_file = deployments_file or config.get_config_value("DEPLOYMENTS_FILE")
    rpc_url = rpc_url or config.get_config_value("RPC_URL")
    oracle_url = (oracle_url or config.get_config_value("ORACLE_URL")).rstrip("/")
    checks: list[dict[str, Any]] = []

    # Oracle
    try:
        r = httpx.get(f"{oracle_url}/healthz", timeout=10.0)
        if r.status_code >= 500:
            _check(checks, "oracle", "unverified", f"{oracle_url} answered {r.status_code}")
        elif r.is_error:
            _check(checks, "oracle", "fail", f"{oracle_url}/healthz answered {r.status_code}")
        else:
            _check(checks, "oracle", "pass", oracle_url)
    except httpx.HTTPError as e:
        _check(checks, "oracle", "unverified", f"{oracle_url} unreachable: {e}")

    # Deployments
    deployments: Optional[dict] = None
    try:
        deployments = policy_cmd.read_deployments(deployments_file)
        _check(checks, "deployments", "pass", deployments_file)
    except (OSError, ValueError) as e:
        _check(checks, "deployments", "fail", f"{deployments_file}: {e}")
    singletons = (deployments or {}).get("singletons") or {}

    # RPC and everything that reads through it
    w3 = None
    try:
        w3 = get_w3(rpc_url)
        connected = w3.is_connected()
    except Exception as e:  # noqa: BLE001
        connected, w3 = False, None
        rpc_detail = f"{rpc_url}: {e}"
    else:
        rpc_detail = rpc_url if connected else f"{rpc_url} not reachable"
    _check(checks, "rpc", "pass" if connected else "unverified", rpc_detail)

    def chain_check(name: str, fn) -> None:
        if not connected:
            _check(checks, name, "unverified", "RPC unreachable")
        elif deployments is None:
            _check(checks, name, "skipped", "no deployments file")
        else:
            try:
                status, detail = fn()
            except Exception as e:  # noqa: BLE001 -- a failed read is "can't tell"
                status, detail = "unverified", f"read failed: {e}"
            _check(checks, name, status, detail)

    def chain_id():
        live, want = w3.eth.chain_id, deployments.get("chainId")
        return ("pass", str(live)) if live == want else ("fail", f"RPC is chain {live}, deployments say {want}")

    def has_code(key: str):
        def fn():
            address = singletons.get(key)
            if not address:
                return "fail", f"no singletons.{key} in deployments"
            code = w3.eth.get_code(address)
            return ("pass", address) if code and len(code) > 0 else ("fail", f"no contract code at {address}")
        return fn

    chain_check("chain_id", chain_id)
    chain_check("xns", has_code("XibalbaNameService"))
    chain_check("policy_registry", has_code("PolicyRegistry"))

    if pack is not None:
        def pack_root():
            prep = output.Reporter("doctor", json_mode=True)
            try:
                policy = policy_cmd.load_policy(pack, prep)
            except typer.Exit:
                return "fail", f"{pack} has no valid on-chain section"
            registry = singletons.get("PolicyRegistry")
            if not registry:
                return "fail", "no singletons.PolicyRegistry in deployments"
            onchain = graph_root_of(w3, registry, policy.domain_id)
            if onchain == policy.root:
                return "pass", "0x" + policy.root.hex()
            return "fail", f"PolicyRegistry holds 0x{onchain.hex()}, pack compiles to 0x{policy.root.hex()}"
        chain_check("pack_root", pack_root)

    for name in ("agent_registry", "attester", "trust_config"):
        _check(checks, name, "pending", PENDING)

    statuses = {c["status"] for c in checks}
    code = output.EXIT_UNVERIFIED if "unverified" in statuses else output.EXIT_NO if "fail" in statuses else output.EXIT_OK
    colour = {"pass": "green", "fail": "red", "unverified": "red", "pending": "yellow", "skipped": "yellow"}
    for c in checks:
        rep.info(f"[{colour[c['status']]}]{c['status']:>10}[/{colour[c['status']]}]  {c['name']:<16} {c['detail']}")
    rep.result({"ok": code == output.EXIT_OK, "checks": checks, "network": config.active_network()})
    raise typer.Exit(code)
