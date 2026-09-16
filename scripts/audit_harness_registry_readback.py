#!/usr/bin/env python3
"""Read-only on-chain registration readback for the named harness DIDs.

This script deliberately does not import wallet helpers, inspect keystores, sign,
or broadcast. It reads public DID document identifiers and calls the registry's
``resolveDID`` view through the SDK.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from integrity_sdk import chain


def did_from_document(path: Path) -> str:
    document = json.loads(path.read_text(encoding="utf-8"))
    did = document.get("id") or document.get("did")
    if not isinstance(did, str) or not did.startswith("did:integrity:"):
        raise ValueError(f"invalid public DID document: {path}")
    return did


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rpc-url", default=os.environ.get("RPC_URL", "https://sepolia.base.org"))
    parser.add_argument(
        "--deployments-file",
        default=os.environ.get("DEPLOYMENTS_FILE", "deployments.baseSepolia.json"),
    )
    parser.add_argument(
        "--did-home",
        type=Path,
        default=Path(os.environ.get("INTEGRITY_DID_HOME", Path.home() / ".integrity" / "did")),
    )
    args = parser.parse_args()

    web3 = chain.get_w3(args.rpc_url)
    chain_id = int(web3.eth.chain_id)
    deployments = chain.load_deployments(args.deployments_file)
    registry = deployments["singletons"]["XibalbaAgentRegistry"]

    print(f"chain_id={chain_id}")
    print(f"registry={registry}")
    for harness in ("claude", "codex", "agy"):
        did = did_from_document(args.did_home / harness / "document.json")
        record = chain.resolve_did(web3, registry, did)
        print(f"{harness}: onchain_registered={record is not None}")
        if record is not None:
            print(f"{harness}: controller_present={bool(record.controller)} domain_present={bool(record.domain_id)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
