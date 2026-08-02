#!/usr/bin/env python3
"""
Anchor the memory DAG's current root-of-heads on-chain.

Companion to `import_memory_dag.py`, and step 5 of `docs/design/memory-dag.md`:
"Root-of-heads + `anchorRoot` of the head" -> `latestRoot != 0`, gate passes.

Deliberately NOT the same code path as `anchor_vault.py` (~/.claude/xibalba/), even
though both end in a `StateAnchor.anchorRoot` call: that script is hardcoded to
`TrustVault.session_root()`, the vault's own root. This script anchors
`memory_dag.root_of_heads(graph.refs().values())` instead -- a different tree over a
different structure. They anchor independently and do not supersede each other; the
vault records "this leaf happened", the DAG records "this is the current head set".

Uses the SAME controller-signed path as anchor_vault.py (`SovereignAgent.execute` ->
`StateAnchor.anchorRoot`), because `StateAnchor`'s admin is the `SovereignAgent`
contract, not any EOA -- a raw `ANCHOR_ROLE` key calling `anchorRoot` directly
reverts unless it holds that role explicitly (as bcc-middleware's oracle signer
does for vault-batch anchoring; this script does not assume that role exists).

    integrity-sdk/.venv/bin/python scripts/anchor_memory_dag.py --dry-run
    integrity-sdk/.venv/bin/python scripts/anchor_memory_dag.py

Idempotent by construction: checks `isAnchoredRoot` before submitting, so a
re-run against an unchanged DAG costs zero gas rather than a redundant tx.
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

    primitives_path = Path.home() / ".integrity" / "did" / args.agent / "primitives.json"
    password_path = Path.home() / ".integrity" / f"{args.agent}.wallet-password"
    keystore_path = Path.home() / ".integrity" / "wallet" / args.agent / "keystore.json"
    for label, p in (("primitives.json", primitives_path),
                      ("wallet password", password_path),
                      ("keystore", keystore_path)):
        if not p.exists():
            print(f"missing {label} at {p} — cannot anchor")
            return 1

    primitives = json.loads(primitives_path.read_text())

    from integrity_sdk import chain

    rpc = os.environ.get("INTEGRITY_RPC_URL", DEFAULT_RPC)
    w3 = chain.get_w3(rpc)

    state_anchor = chain._contract(w3, "StateAnchor", address=primitives["state_anchor"])
    if state_anchor.functions.isAnchoredRoot(root).call():
        print("already anchored — nothing to do")
        return 0

    if args.dry_run:
        print(f"[dry-run] would anchor 0x{root.hex()} via SovereignAgent.execute")
        return 0

    from eth_account import Account

    controller = Account.from_key(
        Account.decrypt(json.loads(keystore_path.read_text()), password_path.read_text().strip())
    )
    tx = chain.anchor_vault_root(
        w3,
        controller,
        primitives["sovereign_agent"],
        primitives["state_anchor"],
        w3.eth.chain_id,
        root,
    )
    print(f"anchored 0x{root.hex()} tx {tx}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
