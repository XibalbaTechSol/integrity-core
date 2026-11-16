#!/usr/bin/env python3
"""
Anchor the memory DAG's current root-of-heads on-chain.

Companion to `import_memory_dag.py`, and step 5 of `docs/design/memory-dag.md`:
"Root-of-heads + `anchorRoot` of the head" -> `latestRoot != 0`, gate passes.

Deliberately NOT the same root as `anchor_vault.py` (~/.claude/xibalba/): that script is
hardcoded to `TrustVault.session_root()`, the vault's own root. This script anchors
`memory_dag.root_of_heads(graph.refs().values())` instead -- a different tree over a
different structure. Both land under the same actor on `ActionAnchor`, which keeps only the
latest root per actor; each anchor stays provable from its `RootAnchored` event.

Anchors through the actor's `SovereignAgent.execute` -> `ActionAnchor.anchorRoot`, signed
by the controller (v2 graph deletion slice D1): `ActionAnchor` keys roots on `msg.sender`,
so this route is what puts the root under the actor. The actor is
`AgentRegistry.resolveDID(did).actor`; a DID with no bound actor exits with `NO_ACTOR` and
sends nothing.

    integrity-sdk/.venv/bin/python scripts/anchor_memory_dag.py --deployments deployments.baseSepolia.json --dry-run
    integrity-sdk/.venv/bin/python scripts/anchor_memory_dag.py --deployments deployments.baseSepolia.json

Idempotent: skips the transaction when the actor's latest root already equals this root.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "integrity-sdk"))

DEFAULT_AGENT = "xibalba"
DEFAULT_DID = "did:integrity:68fed1331613937555a59398223e8e87520a87dd0305aac4fd7ecdc32a14a861"
DEFAULT_RPC = "https://base-sepolia-rpc.publicnode.com"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default=DEFAULT_AGENT)
    ap.add_argument("--did", default=DEFAULT_DID)
    ap.add_argument("--deployments", default=str(REPO / "deployments.baseSepolia.json"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    from integrity_sdk.memory_dag import MemoryGraph, MemoryGraphError, root_of_heads

    graph = MemoryGraph(args.did)
    heads = list(graph.refs().values())
    if not heads:
        print("no refs in the DAG — nothing to anchor")
        return 0

    try:
        root = root_of_heads(heads)
    except MemoryGraphError as exc:
        print(f"cannot compute root_of_heads: {exc}")
        return 1

    print(f"{len(graph.all_nodes())} nodes, {len(heads)} head(s), root_of_heads = 0x{root.hex()}")

    password_path = Path.home() / ".integrity" / f"{args.agent}.wallet-password"
    keystore_path = Path.home() / ".integrity" / "wallet" / args.agent / "keystore.json"
    for label, p in (("wallet password", password_path), ("keystore", keystore_path)):
        if not p.exists():
            print(f"missing {label} at {p} — cannot anchor")
            return 1

    from integrity_sdk import chain

    rpc = os.environ.get("INTEGRITY_RPC_URL", DEFAULT_RPC)
    w3 = chain.get_w3(rpc)
    singletons = chain.load_deployments(args.deployments).get("singletons") or {}
    if not singletons.get("AgentRegistry") or not singletons.get("ActionAnchor"):
        print(f"{args.deployments} lacks singletons.AgentRegistry / singletons.ActionAnchor")
        return 1

    actor = chain.resolve_actor(w3, singletons["AgentRegistry"], args.did)
    if actor is None:
        print(f"{chain.NO_ACTOR}: {args.did} has no bound actor — the DAG stays local")
        return 0

    if bytes(chain.actor_latest_root(w3, singletons["ActionAnchor"], actor)) == root:
        print("already anchored — nothing to do")
        return 0

    if args.dry_run:
        print(f"[dry-run] would anchor 0x{root.hex()} via SovereignAgent.execute")
        return 0

    from eth_account import Account

    controller = Account.from_key(
        Account.decrypt(json.loads(keystore_path.read_text()), password_path.read_text().strip())
    )
    tx = chain.anchor_vault_root(w3, controller, actor, singletons["ActionAnchor"], w3.eth.chain_id, root)
    print(f"anchored 0x{root.hex()} tx {tx}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
