"""Policy pack on-chain section -> `PolicyRegistry` graph root and per-call Merkle proofs.

Registration v3 spec, Part 4 ("Policy pack -> on-chain policy"). A pack may carry an
``onchain.json`` file naming the contracts (``target``), functions (``selector``) and risk
weights its confined agents may call. Because it is a pack file, its bytes are covered by the
pack's signed ``pack_hash``; recompiling it reproduces the root governance publishes with
``PolicyRegistry.setGraphRoot(domainId, root)``, so anyone can check the on-chain map is the pack's
map.

Leaf: INTERFACE_CONTRACT §4.4c, byte-for-byte ``PolicyRegistry.leafOf``::

    keccak256(abi.encode(bytes32 fromNode, bytes32 relation, bytes32 toNode,
                         address target, bytes4 targetSelector, uint16 riskWeightBps))

Tree: OpenZeppelin sorted-pair (``core.merkle``). Leaves are sorted before building so the root
depends on the edge SET, not the order the pack author wrote them in.

Node naming for a plain contract call (left to the builder by the spec): ``from_node = "agent"``,
``relation = "calls"``, ``to_node = "<target lowercase hex>:<selector lowercase hex>"``; each name
is ``keccak256(utf8(name))``. A field given as 0x + 64 hex is taken as the raw bytes32, which is
how the §4.4c golden vector (``0x..01, 0x..02, 0x..03``) is expressed.

Section schema::

    {"domain": "<DomainRegistry name>",
     "edges": [{"target": "0x<20 bytes>", "selector": "0x<4 bytes>", "risk_weight_bps": 0..10000,
                "from_node"?: str, "relation"?: str, "to_node"?: str}, ...]}
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Sequence, Tuple

from .merkle import keccak256, merkle_proof, merkle_root
from .packs import CompiledPack

ONCHAIN_FILE = "onchain.json"
MAX_RISK_WEIGHT_BPS = 10_000

_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
_SELECTOR = re.compile(r"^0x[0-9a-fA-F]{8}$")
_RAW_NODE = re.compile(r"^0x[0-9a-fA-F]{64}$")
_EDGE_REQUIRED = ("target", "selector", "risk_weight_bps")
_EDGE_ALLOWED = set(_EDGE_REQUIRED) | {"from_node", "relation", "to_node"}


class OnchainSectionError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


@dataclass(frozen=True)
class OnchainEdge:
    from_node: bytes
    relation: bytes
    to_node: bytes
    target: str  # 0x-prefixed lowercase
    selector: str  # 0x-prefixed lowercase, 4 bytes
    risk_weight_bps: int
    leaf: bytes

    def execute_args(self) -> Tuple[bytes, bytes, bytes, int]:
        """(fromNode, relation, toNode, riskWeightBps) for `SovereignAgent.execute`'s edge claim."""
        return self.from_node, self.relation, self.to_node, self.risk_weight_bps


@dataclass(frozen=True)
class OnchainPolicy:
    domain: str
    domain_id: bytes
    edges: Tuple[OnchainEdge, ...]  # in the author's order
    leaves: Tuple[bytes, ...]  # sorted ascending; the tree's leaf order
    root: bytes
    pack_hash: Optional[str] = None


def node_id(name: str) -> bytes:
    """bytes32 for a node/relation name, or the raw value when given as 0x + 64 hex."""
    if _RAW_NODE.match(name):
        return bytes.fromhex(name[2:])
    return keccak256(name.encode("utf-8"))


def domain_id(name: str) -> bytes:
    """`DomainRegistry.domainId(name)`: keccak256(bytes(name))."""
    return keccak256(name.encode("utf-8"))


def _as_bytes32(v: bytes | str) -> bytes:
    b = node_id(v) if isinstance(v, str) else v
    if len(b) != 32:
        raise OnchainSectionError("BAD_NODE", "node ids are 32 bytes")
    return b


def edge_leaf(
    from_node: bytes | str,
    relation: bytes | str,
    to_node: bytes | str,
    target: str,
    selector: str,
    risk_weight_bps: int,
) -> bytes:
    """`PolicyRegistry.leafOf`, byte for byte (each field padded to one 32-byte word)."""
    target_b = bytes.fromhex(target[2:])
    selector_b = bytes.fromhex(selector[2:])
    preimage = (
        _as_bytes32(from_node)
        + _as_bytes32(relation)
        + _as_bytes32(to_node)
        + b"\x00" * 12 + target_b  # address: left-padded
        + selector_b + b"\x00" * 28  # bytes4: right-padded
        + risk_weight_bps.to_bytes(32, "big")  # uint16: left-padded
    )
    return keccak256(preimage)


def _parse_edge(raw: Any, i: int) -> OnchainEdge:
    if not isinstance(raw, Mapping):
        raise OnchainSectionError("BAD_EDGE", f"edges[{i}] is not an object")
    unknown = set(raw) - _EDGE_ALLOWED
    if unknown:
        raise OnchainSectionError("UNKNOWN_FIELD", f"edges[{i}] has {sorted(unknown)}")
    for key in _EDGE_REQUIRED:
        if key not in raw:
            raise OnchainSectionError("MISSING_FIELD", f"edges[{i}].{key}")
    target, selector, weight = raw["target"], raw["selector"], raw["risk_weight_bps"]
    if not isinstance(target, str) or not _ADDRESS.match(target):
        raise OnchainSectionError("BAD_TARGET", f"edges[{i}].target must be a 20-byte 0x address")
    if not isinstance(selector, str) or not _SELECTOR.match(selector):
        raise OnchainSectionError("BAD_SELECTOR", f"edges[{i}].selector must be 0x + 8 hex")
    if isinstance(weight, bool) or not isinstance(weight, int) or not 0 <= weight <= MAX_RISK_WEIGHT_BPS:
        raise OnchainSectionError("BAD_RISK_WEIGHT", f"edges[{i}].risk_weight_bps must be 0..{MAX_RISK_WEIGHT_BPS}")
    target, selector = target.lower(), selector.lower()
    names = []
    for key, default in (("from_node", "agent"), ("relation", "calls"), ("to_node", f"{target}:{selector}")):
        value = raw.get(key, default)
        if not isinstance(value, str) or not value:
            raise OnchainSectionError("BAD_NODE", f"edges[{i}].{key} must be a non-empty string")
        names.append(node_id(value))
    leaf = edge_leaf(names[0], names[1], names[2], target, selector, weight)
    return OnchainEdge(names[0], names[1], names[2], target, selector, weight, leaf)


def compile_onchain(section: Any, *, pack_hash: Optional[str] = None) -> OnchainPolicy:
    """Validate an on-chain section and compile it to its canonical leaves and root."""
    if not isinstance(section, Mapping):
        raise OnchainSectionError("MALFORMED", "the on-chain section must be an object")
    for key in ("domain", "edges"):
        if key not in section:
            raise OnchainSectionError("MISSING_FIELD", key)
    unknown = set(section) - {"domain", "edges"}
    if unknown:
        raise OnchainSectionError("UNKNOWN_FIELD", f"section has {sorted(unknown)}")
    domain = section["domain"]
    if not isinstance(domain, str) or not domain:
        raise OnchainSectionError("BAD_DOMAIN", "domain must be a non-empty DomainRegistry name")
    raw_edges = section["edges"]
    if not isinstance(raw_edges, list):
        raise OnchainSectionError("MALFORMED", "edges must be a list")
    if not raw_edges:
        # An empty map would publish a root no proof can satisfy: every call reverts. Say so.
        raise OnchainSectionError("EMPTY", "an on-chain section needs at least one edge")
    edges = tuple(_parse_edge(e, i) for i, e in enumerate(raw_edges))
    leaves = sorted(e.leaf for e in edges)
    for a, b in zip(leaves, leaves[1:]):
        if a == b:
            raise OnchainSectionError("DUPLICATE_EDGE", "two edges compile to the same leaf")
    return OnchainPolicy(
        domain=domain,
        domain_id=domain_id(domain),
        edges=edges,
        leaves=tuple(leaves),
        root=merkle_root(leaves),
        pack_hash=pack_hash,
    )


def onchain_policy_of(pack: CompiledPack) -> Optional[OnchainPolicy]:
    """The pack's compiled on-chain policy, or None when the pack declares no on-chain section."""
    data = pack.files.get(ONCHAIN_FILE)
    if data is None:
        return None
    try:
        section = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OnchainSectionError("MALFORMED", f"{ONCHAIN_FILE} is not valid JSON") from exc
    return compile_onchain(section, pack_hash=pack.pack_hash)


def proof_for(policy: OnchainPolicy, edge: OnchainEdge) -> List[bytes]:
    """The Merkle proof an agent passes to `SovereignAgent.execute` for this edge."""
    try:
        index = policy.leaves.index(edge.leaf)
    except ValueError:
        raise OnchainSectionError("NOT_IN_MAP", "this edge is not in the pack's on-chain map") from None
    return merkle_proof(list(policy.leaves), index)


__all__: Sequence[str] = (
    "ONCHAIN_FILE",
    "OnchainEdge",
    "OnchainPolicy",
    "OnchainSectionError",
    "compile_onchain",
    "domain_id",
    "edge_leaf",
    "node_id",
    "onchain_policy_of",
    "proof_for",
)
