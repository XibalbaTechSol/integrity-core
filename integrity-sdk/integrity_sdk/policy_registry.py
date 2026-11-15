"""`PolicyRegistry`: read a domain's published action-graph root; build (never sign) a new one.

`graphRootOf(domainId)` is the Merkle root a pack's on-chain section must reproduce
(`core.pack_onchain.compile_onchain`). Changing it is `setGraphRoot`, gated by
`GRAPH_CURATOR_ROLE`: a governance action. This module therefore only *builds* that transaction
for governance (a Safe, a multisig) to review and sign. It holds no keys and sends nothing.

The ABI is inlined (two functions) rather than synced from `contracts/out`, so this read works
without a Foundry build or an ABI-sync step.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from eth_utils import keccak
from web3 import Web3

SET_GRAPH_ROOT_SIGNATURE = "setGraphRoot(bytes32,bytes32)"

_ABI = [
    {
        "type": "function",
        "name": "graphRootOf",
        "stateMutability": "view",
        "inputs": [{"name": "", "type": "bytes32"}],
        "outputs": [{"name": "", "type": "bytes32"}],
    },
]


def _bytes32(value: bytes, what: str) -> bytes:
    if not isinstance(value, (bytes, bytearray)) or len(value) != 32:
        raise ValueError(f"{what} must be exactly 32 bytes")
    return bytes(value)


def graph_root_of(w3: Web3, registry_address: str, domain_id: bytes) -> bytes:
    """The root currently published for `domain_id` (32 zero bytes when none is set)."""
    registry = w3.eth.contract(address=Web3.to_checksum_address(registry_address), abi=_ABI)
    return bytes(registry.functions.graphRootOf(_bytes32(domain_id, "domain_id")).call())


def set_graph_root_tx(
    registry_address: str, domain_id: bytes, root: bytes, *, chain_id: Optional[int] = None
) -> Dict[str, Any]:
    """An unsigned `setGraphRoot(domainId, root)` call, ready to paste into a Safe transaction.

    No nonce, gas or sender: whoever holds GRAPH_CURATOR_ROLE fills those in when they sign.
    """
    domain_id = _bytes32(domain_id, "domain_id")
    root = _bytes32(root, "root")
    data = keccak(text=SET_GRAPH_ROOT_SIGNATURE)[:4] + domain_id + root
    tx: Dict[str, Any] = {
        "to": Web3.to_checksum_address(registry_address),
        "value": "0",
        "data": "0x" + data.hex(),
        "function": SET_GRAPH_ROOT_SIGNATURE,
        "args": {"domainId": "0x" + domain_id.hex(), "root": "0x" + root.hex()},
    }
    if chain_id is not None:
        tx["chainId"] = chain_id
    return tx


__all__ = ["SET_GRAPH_ROOT_SIGNATURE", "graph_root_of", "set_graph_root_tx"]
