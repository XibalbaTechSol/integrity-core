"""`integrity policy ...`: a pack's on-chain map, compiled locally and checked against PolicyRegistry.

Everything here is read-only. `publish --print-tx` only PRINTS the `setGraphRoot` governance
transaction (decision D5): a root change is signed by the curator through governance, never by
this CLI, so there is no key handling in this module at all.

Exit codes follow `output`: 0 yes, 1 no (not in the map / roots differ), 2 usage, 3 the RPC
could not be read, so the comparison is unverified.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

import typer

from integrity_sdk.chain import get_w3  # noqa: F401  (module-level so tests can patch it)
from integrity_sdk.core.pack_onchain import (
    OnchainEdge,
    OnchainPolicy,
    OnchainSectionError,
    domain_id,
    edges_for_call,
    onchain_policy_of,
    proof_for,
)
from integrity_sdk.core.packs import PackError, compile_pack
from integrity_sdk.policy_registry import graph_root_of, set_graph_root_tx  # noqa: F401

from . import config, output

policy_app = typer.Typer(help="A pack's on-chain policy map: compile, inspect, prove, compare with PolicyRegistry")

_PACK_ARG = typer.Argument(..., help="Pack directory (pack.yaml + .rego + optional onchain.json)")
_JSON = typer.Option(False, "--json", help=output.JSON_OPTION_HELP)
_DEPLOYMENTS = typer.Option(None, "--deployments-file", help="Deployments JSON (env/profile/config DEPLOYMENTS_FILE)")
_RPC = typer.Option(None, "--rpc-url", help="JSON-RPC endpoint (env/profile/config RPC_URL)")
_CALL = re.compile(r"^(0x[0-9a-fA-F]{40}):(0x[0-9a-fA-F]{8})(?::(\d+))?$")


def _hex(b: bytes) -> str:
    return "0x" + b.hex()


def _edge_doc(e: OnchainEdge) -> dict[str, Any]:
    return {
        "target": e.target, "selector": e.selector, "risk_weight_bps": e.risk_weight_bps,
        "from_node": _hex(e.from_node), "relation": _hex(e.relation), "to_node": _hex(e.to_node),
        "leaf": _hex(e.leaf),
    }


def load_policy(pack_dir: str, rep: output.Reporter) -> OnchainPolicy:
    """Compile the pack (no signature check) and its on-chain section; any refusal is a 1."""
    try:
        policy = onchain_policy_of(compile_pack(pack_dir))
    except (PackError, OnchainSectionError) as e:
        rep.fail(output.EXIT_NO, str(e), code=e.code)
    except OSError as e:
        rep.fail(output.EXIT_NO, f"cannot read pack {pack_dir}: {e}", code="UNREADABLE")
    if policy is None:
        rep.fail(output.EXIT_NO, f"{pack_dir} has no on-chain section (onchain.json)", code="NO_ONCHAIN_SECTION")
    return policy


def read_deployments(path: str) -> dict[str, Any]:
    """Raises FileNotFoundError / ValueError; callers decide what that means for their exit code."""
    doc = json.loads(Path(path).read_text())
    if not isinstance(doc, dict):
        raise ValueError(f"{path} is not a JSON object")
    return doc


def _policy_registry(deployments_file: Optional[str], rep: output.Reporter) -> tuple[str, dict[str, Any]]:
    deployments_file = deployments_file or config.get_config_value("DEPLOYMENTS_FILE")
    try:
        deployments = read_deployments(deployments_file)
    except (OSError, ValueError) as e:
        rep.fail(output.EXIT_NO, f"cannot read deployments {deployments_file}: {e}", code="NO_DEPLOYMENTS")
    registry = (deployments.get("singletons") or {}).get("PolicyRegistry")
    if not registry:
        rep.fail(output.EXIT_NO, f"no singletons.PolicyRegistry in {deployments_file}", code="NO_POLICY_REGISTRY")
    return registry, deployments


@policy_app.command("compile")
def compile_cmd(
    pack_dir: str = _PACK_ARG,
    out: Optional[Path] = typer.Option(None, "--out", help="Also write the compiled map to this JSON file"),
    json_output: bool = _JSON,
):
    """Compile the pack's on-chain section to the Merkle root governance would publish."""
    rep = output.Reporter("policy", "compile", json_mode=json_output)
    policy = load_policy(pack_dir, rep)
    doc = {
        "domain": policy.domain, "domain_id": _hex(policy.domain_id), "root": _hex(policy.root),
        "pack_hash": policy.pack_hash, "edges": [_edge_doc(e) for e in policy.edges],
        "leaves": [_hex(leaf) for leaf in policy.leaves],
    }
    if out is not None:
        out.write_text(json.dumps({"schema": rep.schema, **doc}, indent=2, sort_keys=True) + "\n")
        rep.info(f"wrote {out}")
    rep.info(f"domain {policy.domain} ({_hex(policy.domain_id)})")
    rep.info(f"root   {_hex(policy.root)}  ({len(policy.edges)} edges, {policy.pack_hash})")
    rep.result(doc)


@policy_app.command("map")
def map_cmd(pack_dir: str = _PACK_ARG, json_output: bool = _JSON):
    """List every (target, selector, risk weight) edge the pack's map permits."""
    rep = output.Reporter("policy", "map", json_mode=json_output)
    policy = load_policy(pack_dir, rep)
    rep.info(f"domain {policy.domain}  root {_hex(policy.root)}")
    for e in policy.edges:
        rep.info(f"  {e.target} {e.selector}  risk {e.risk_weight_bps} bps")
    rep.result({"domain": policy.domain, "root": _hex(policy.root), "edges": [_edge_doc(e) for e in policy.edges]})


@policy_app.command("check")
def check_cmd(
    pack_dir: str = _PACK_ARG,
    call: str = typer.Option(..., "--call", help="TARGET:SELECTOR[:RISK_BPS], e.g. 0xabc…:0xa9059cbb:500"),
    json_output: bool = _JSON,
):
    """Is this call in the pack's map? Exit 0 yes, 1 no."""
    m = _CALL.match(call)
    if not m:
        raise typer.BadParameter("expected TARGET:SELECTOR[:RISK_BPS] (20-byte address, 4-byte selector)", param_hint="--call")
    target, selector, risk = m.group(1), m.group(2), m.group(3)
    rep = output.Reporter("policy", "check", json_mode=json_output)
    policy = load_policy(pack_dir, rep)
    matches = edges_for_call(policy, target, selector)
    if risk is not None:
        matches = tuple(e for e in matches if e.risk_weight_bps == int(risk))
    allowed = bool(matches)
    rep.info(f"[green]in map[/green] {call}" if allowed else f"[red]not in map[/red] {call}")
    rep.result({"allowed": allowed, "call": call, "edges": [_edge_doc(e) for e in matches]})
    if not allowed:
        raise typer.Exit(output.EXIT_NO)


@policy_app.command("prove")
def prove_cmd(
    pack_dir: str = _PACK_ARG,
    target: str = typer.Option(..., "--target", help="Contract address being called"),
    selector: str = typer.Option(..., "--selector", help="4-byte function selector, 0x-prefixed"),
    risk: Optional[int] = typer.Option(None, "--risk", help="Risk weight (bps) to claim; needed when several edges match"),
    json_output: bool = _JSON,
):
    """Print the Merkle proof and execute() claim an agent passes to SovereignAgent.execute."""
    rep = output.Reporter("policy", "prove", json_mode=json_output)
    policy = load_policy(pack_dir, rep)
    try:
        matches = edges_for_call(policy, target, selector)
    except OnchainSectionError as e:
        raise typer.BadParameter(str(e))
    if risk is not None:
        matches = tuple(e for e in matches if e.risk_weight_bps == risk)
    if not matches:
        rep.fail(output.EXIT_NO, f"{target}:{selector} is not in the map" + (f" at {risk} bps" if risk is not None else ""), code="NOT_IN_MAP")
    if len(matches) > 1:
        weights = sorted(e.risk_weight_bps for e in matches)
        raise typer.BadParameter(f"{len(matches)} edges match (risk {weights}); pick one with --risk", param_hint="--risk")
    (edge,) = matches
    proof = [_hex(p) for p in proof_for(policy, edge)]
    execute_args = {
        "fromNode": _hex(edge.from_node), "relation": _hex(edge.relation),
        "toNode": _hex(edge.to_node), "riskWeightBps": edge.risk_weight_bps,
    }
    rep.info(f"root  {_hex(policy.root)}")
    rep.info(f"claim {json.dumps(execute_args)}")
    rep.info("proof " + json.dumps(proof))
    rep.result({"root": _hex(policy.root), "domain_id": _hex(policy.domain_id), "edge": _edge_doc(edge),
                "execute_args": execute_args, "proof": proof})


@policy_app.command("publish")
def publish_cmd(
    pack_dir: str = _PACK_ARG,
    print_tx: bool = typer.Option(False, "--print-tx", help="Required: print the unsigned setGraphRoot transaction"),
    deployments_file: Optional[str] = _DEPLOYMENTS,
    json_output: bool = _JSON,
):
    """Print (never send) the PolicyRegistry.setGraphRoot transaction for governance to sign."""
    if not print_tx:
        raise typer.BadParameter(
            "this CLI never signs a root change; pass --print-tx and hand the transaction to governance",
            param_hint="--print-tx",
        )
    rep = output.Reporter("policy", "publish", json_mode=json_output)
    policy = load_policy(pack_dir, rep)
    registry, deployments = _policy_registry(deployments_file, rep)
    tx = set_graph_root_tx(registry, policy.domain_id, policy.root, chain_id=deployments.get("chainId"))
    rep.info("unsigned transaction (GRAPH_CURATOR_ROLE signs it through governance):")
    rep.info(json.dumps(tx, indent=2, sort_keys=True))
    rep.result({"tx": tx, "pack_hash": policy.pack_hash, "domain": policy.domain})


@policy_app.command("diff")
def diff_cmd(
    pack_dir: str = _PACK_ARG,
    domain: Optional[str] = typer.Option(None, "--domain", help="Compare against this domain instead of the pack's"),
    deployments_file: Optional[str] = _DEPLOYMENTS,
    rpc_url: Optional[str] = _RPC,
    json_output: bool = _JSON,
):
    """Does PolicyRegistry hold this pack's root? Exit 0 same, 1 different, 3 could not read."""
    rep = output.Reporter("policy", "diff", json_mode=json_output)
    policy = load_policy(pack_dir, rep)
    registry, _ = _policy_registry(deployments_file, rep)
    did = domain_id(domain) if domain else policy.domain_id
    rpc_url = rpc_url or config.get_config_value("RPC_URL")
    w3 = get_w3(rpc_url)
    try:
        if not w3.is_connected():
            rep.fail(output.EXIT_UNVERIFIED, f"RPC unreachable at {rpc_url}", code="UNREACHABLE")
        onchain = graph_root_of(w3, registry, did)
    except typer.Exit:
        raise
    except Exception as e:  # noqa: BLE001 -- reported, never swallowed
        # A failed READ is never evidence the roots differ: it is "can't tell" (3), not "no" (1).
        rep.fail(output.EXIT_UNVERIFIED, f"PolicyRegistry read failed: {e}", code="READ_FAILED")
    match = onchain == policy.root
    rep.info(f"local   {_hex(policy.root)}")
    rep.info(f"onchain {_hex(onchain)}")
    rep.info("[green]match[/green]" if match else "[red]differs[/red]")
    rep.result({"match": match, "local_root": _hex(policy.root), "onchain_root": _hex(onchain),
                "domain_id": _hex(did), "registry": registry})
    if not match:
        raise typer.Exit(output.EXIT_NO)
