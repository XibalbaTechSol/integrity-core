"""Modular ERC-8004 / Agent0 Public Passport Bridge for the Integrity Protocol.

ERC-8004 ("Trustless Agents") is an optional public discovery layer (Tier 2).
Integrity Protocol's Ed25519 DID (`did:integrity:<sha256(pubkey)>`) and v3
`AgentRegistry` / policy-confined `SovereignAgent` remain the authoritative
source of identity, wallet confinement, and AIS reputation.

This module:
1. Builds ERC-8004 registration documents (`registration-v1`) carrying a
   cryptographic two-way `DID` service backlink to `did:integrity:...` and
   CAIP-10 `registrations` references (`eip155:<chain_id>:<registry>`), matching
   the exact invariant enforced by `integrity-oracle/backend/src/erc8004.rs`.
2. Resolves the agent's policy-confined `SovereignAgent` actor from `AgentRegistry`
   (when present) so the ERC-8004 `agentWallet` metadata points to the confined
   `SovereignAgent` smart contract rather than an unconfined EOA.
3. Links or unlinks/queries the verified ERC-8004 projection at the Integrity Oracle
   (`POST / GET /v1/agent/{did}/erc8004`).
"""
from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Optional

import requests
from web3 import Web3

from integrity_sdk import chain

REGISTRATION_TYPE = "https://eips.ethereum.org/EIPS/eip-8004#registration-v1"
BASE_SEPOLIA_CHAIN_ID = 84532
BASE_SEPOLIA_ERC8004_REGISTRY = "0x8004A818BFB912233c491871b3d84c89A494BD9e"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
_DID_PREFIX = "did:integrity:"

# Minimal ABI for external ERC-8004 Identity Registry deployments (register + read + URI update).
ERC8004_IDENTITY_REGISTRY_ABI: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "register",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "agentURI", "type": "string"},
            {
                "name": "metadata",
                "type": "tuple[]",
                "components": [
                    {"name": "key", "type": "string"},
                    {"name": "value", "type": "bytes"},
                ],
            },
        ],
        "outputs": [{"name": "agentId", "type": "uint256"}],
    },
    {
        "type": "function",
        "name": "setAgentURI",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "agentId", "type": "uint256"},
            {"name": "newURI", "type": "string"},
        ],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "tokenURI",
        "stateMutability": "view",
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "outputs": [{"name": "", "type": "string"}],
    },
    {
        "type": "function",
        "name": "ownerOf",
        "stateMutability": "view",
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "outputs": [{"name": "", "type": "address"}],
    },
    {
        "type": "function",
        "name": "getAgentWallet",
        "stateMutability": "view",
        "inputs": [{"name": "agentId", "type": "uint256"}],
        "outputs": [{"name": "", "type": "address"}],
    },
    {
        "type": "event",
        "name": "Registered",
        "inputs": [
            {"name": "agentId", "type": "uint256", "indexed": True},
            {"name": "agentURI", "type": "string", "indexed": False},
            {"name": "owner", "type": "address", "indexed": True},
        ],
    },
    {
        "type": "event",
        "name": "AgentRegistered",
        "inputs": [
            {"name": "agentId", "type": "uint256", "indexed": True},
            {"name": "owner", "type": "address", "indexed": True},
            {"name": "agentURI", "type": "string", "indexed": False},
        ],
    },
]


class Erc8004BridgeError(RuntimeError):
    """Raised when an Oracle or ERC-8004 registration/linking step fails."""

    def __init__(self, stage: str, status: Optional[int], detail: str, *, unreachable: bool = False):
        super().__init__(
            f"ERC-8004 {stage} failed ({status if status is not None else 'no status'}): {detail}"
        )
        self.stage = stage
        self.status = status
        self.detail = detail
        self.unreachable = unreachable or (status is not None and status >= 500)


@dataclass(frozen=True)
class Erc8004Binding:
    agent_id: str
    chain_id: int
    identity_registry_address: str
    agent_token_id: str
    registration_uri: str
    registration_sha256: str
    nft_owner_address: str
    agent_wallet_address: Optional[str]
    binding_status: str
    name: str
    description: str
    x402_support: bool
    mcp_endpoint: Optional[str]
    a2a_endpoint: Optional[str]
    a2a_version: Optional[str]
    sovereign_actor_address: Optional[str] = None
    wallet_confined: bool = False


def caip10_registry(chain_id: int, registry_address: str) -> str:
    """CAIP-10 identifier for an ERC-8004 Identity Registry, matching `erc8004::caip10` in the Oracle."""
    if chain_id <= 0:
        raise ValueError(f"chain_id must be positive, got {chain_id}")
    addr = registry_address.strip()
    if not Web3.is_address(addr):
        raise ValueError(f"invalid registry address: {registry_address!r}")
    return f"eip155:{chain_id}:{addr.lower()}"


def build_registration_document(
    *,
    did: str,
    name: str,
    description: str,
    image: str = "https://integrity.xibalba.solutions/agent-avatar.png",
    chain_id: int = BASE_SEPOLIA_CHAIN_ID,
    registry_address: str = BASE_SEPOLIA_ERC8004_REGISTRY,
    token_id: int | str = 0,
    mcp_endpoint: Optional[str] = None,
    a2a_endpoint: Optional[str] = None,
    a2a_version: Optional[str] = "0.3.0",
    x402_support: bool = False,
    active: bool = True,
    supported_trust: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Build a canonical ERC-8004 registration-v1 JSON dictionary with two-way Integrity DID binding."""
    if not did.startswith(_DID_PREFIX) or len(did) <= len(_DID_PREFIX):
        raise ValueError(f"did must be a valid did:integrity:<fingerprint>, got {did!r}")
    if not name.strip() or not description.strip() or not image.strip():
        raise ValueError("name, description, and image must all be non-empty")

    services: list[dict[str, Any]] = [{"name": "DID", "endpoint": did.strip()}]
    if mcp_endpoint and mcp_endpoint.strip():
        services.append({"name": "MCP", "endpoint": mcp_endpoint.strip()})
    if a2a_endpoint and a2a_endpoint.strip():
        a2a_entry: dict[str, Any] = {"name": "A2A", "endpoint": a2a_endpoint.strip()}
        if a2a_version and a2a_version.strip():
            a2a_entry["version"] = a2a_version.strip()
        services.append(a2a_entry)

    caip10 = caip10_registry(chain_id, registry_address)
    tok = int(token_id) if isinstance(token_id, int) or (isinstance(token_id, str) and token_id.isdigit()) else str(token_id)

    return {
        "type": REGISTRATION_TYPE,
        "name": name.strip(),
        "description": description.strip(),
        "image": image.strip(),
        "services": services,
        "x402Support": bool(x402_support),
        "active": bool(active),
        "registrations": [
            {
                "agentId": tok,
                "agentRegistry": caip10,
            }
        ],
        "supportedTrust": list(supported_trust) if supported_trust is not None else ["reputation", "crypto-economic"],
    }


def encode_registration_data_uri(document: dict[str, Any]) -> tuple[str, str]:
    """Encode an ERC-8004 registration document as a `data:application/json;base64,...` URI and its SHA-256 hex."""
    raw = json.dumps(document, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sha256_hex = hashlib.sha256(raw).hexdigest()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:application/json;base64,{b64}", sha256_hex


def resolve_confined_actor(w3: Web3, agent_registry_address: str, did: str) -> Optional[str]:
    """Return the bound `SovereignAgent` actor address from v3 `AgentRegistry.resolveDID(did)`, or None."""
    registry = chain._contract(w3, "AgentRegistry", address=agent_registry_address)
    rec = chain._call_with_retry(registry.functions.resolveDID(did).call)
    # AgentRecord: (pubkey, guardian, actor, domainId, uri, registeredAt, retiredAt, proofKind)
    registered_at = rec[5]
    retired_at = rec[6]
    actor = rec[2]
    if not registered_at or retired_at:
        return None
    if not actor or actor.lower() == ZERO_ADDRESS:
        return None
    return Web3.to_checksum_address(actor)


def _extract_registered_token_id(contract: Any, receipt: Any) -> int:
    """Extract the minted `agentId` (`uint256`) from `Registered` or `AgentRegistered` event logs."""
    for event_name in ("Registered", "AgentRegistered"):
        event_cls = getattr(contract.events, event_name, None)
        if event_cls is None:
            continue
        try:
            logs = event_cls().process_receipt(receipt)
            for log in logs:
                if "agentId" in log["args"]:
                    return int(log["args"]["agentId"])
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError("ERC-8004 register transaction succeeded but emitted no Registered(agentId, ...) event")


def register_and_link_erc8004(
    w3: Web3,
    oracle_url: str,
    did: str,
    guardian: Any,
    *,
    name: str,
    description: str,
    image: str = "https://integrity.xibalba.solutions/agent-avatar.png",
    identity_registry_address: str = BASE_SEPOLIA_ERC8004_REGISTRY,
    agent_registry_address: Optional[str] = None,
    mcp_endpoint: Optional[str] = None,
    a2a_endpoint: Optional[str] = None,
    a2a_version: Optional[str] = "0.3.0",
    x402_support: bool = False,
    active: bool = True,
    supported_trust: Optional[list[str]] = None,
    timeout: float = 30.0,
) -> tuple[Erc8004Binding, str]:
    """Mint an ERC-8004 Public Passport on-chain with a two-way DID backlink and confined actor wallet, then link with the Oracle.

    1. If `agent_registry_address` is supplied, reads `AgentRegistry.resolveDID(did).actor` so the
       ERC-8004 `agentWallet` metadata entry is set to the policy-confined `SovereignAgent` contract
       address (rather than an unconfined EOA).
    2. Calls `register(initial_uri, metadata)` on the ERC-8004 Identity Registry to obtain the
       assigned `tokenId`.
    3. Finalizes the `agentURI` via `setAgentURI(tokenId, final_uri)` if the contract exposes
       `setAgentURI` so `registrations[].agentId` in the JSON matches the exact minted `tokenId`.
    4. Calls `POST /v1/agent/{did}/erc8004` on the Integrity Oracle to verify the two-way binding.
    """
    chain_id = int(w3.eth.chain_id)
    erc8004_registry = w3.eth.contract(
        address=Web3.to_checksum_address(identity_registry_address),
        abi=ERC8004_IDENTITY_REGISTRY_ABI,
    )

    confined_actor: Optional[str] = None
    if agent_registry_address:
        confined_actor = resolve_confined_actor(w3, agent_registry_address, did)

    metadata_entries: list[tuple[str, bytes]] = [
        ("integrityDid", did.encode("utf-8")),
    ]
    if confined_actor:
        metadata_entries.append(("agentWallet", bytes.fromhex(confined_actor[2:])))
        metadata_entries.append(("sovereignActor", confined_actor.encode("utf-8")))

    initial_doc = build_registration_document(
        did=did,
        name=name,
        description=description,
        image=image,
        chain_id=chain_id,
        registry_address=identity_registry_address,
        token_id=0,
        mcp_endpoint=mcp_endpoint,
        a2a_endpoint=a2a_endpoint,
        a2a_version=a2a_version,
        x402_support=x402_support,
        active=active,
        supported_trust=supported_trust,
    )
    initial_uri, _ = encode_registration_data_uri(initial_doc)

    reg_call = erc8004_registry.functions.register(initial_uri, metadata_entries)
    receipt, tx_hash = chain._send_signed(
        w3,
        guardian,
        lambda nonce: reg_call.build_transaction(
            {"from": guardian.address, "nonce": nonce, "chainId": chain_id}
        ),
        action="erc8004_register",
    )
    token_id = _extract_registered_token_id(erc8004_registry, receipt)

    if token_id != 0:
        final_doc = build_registration_document(
            did=did,
            name=name,
            description=description,
            image=image,
            chain_id=chain_id,
            registry_address=identity_registry_address,
            token_id=token_id,
            mcp_endpoint=mcp_endpoint,
            a2a_endpoint=a2a_endpoint,
            a2a_version=a2a_version,
            x402_support=x402_support,
            active=active,
            supported_trust=supported_trust,
        )
        final_uri, _ = encode_registration_data_uri(final_doc)
        set_uri_call = erc8004_registry.functions.setAgentURI(token_id, final_uri)
        _, tx_hash = chain._send_signed(
            w3,
            guardian,
            lambda nonce: set_uri_call.build_transaction(
                {"from": guardian.address, "nonce": nonce, "chainId": chain_id}
            ),
            action="erc8004_set_agent_uri",
        )

    binding = link_erc8004_with_oracle(
        oracle_url,
        did,
        chain_id=chain_id,
        identity_registry_address=identity_registry_address,
        agent_token_id=token_id,
        timeout=timeout,
    )
    return binding, tx_hash.hex()


def link_erc8004_with_oracle(
    oracle_url: str,
    did: str,
    *,
    chain_id: int,
    identity_registry_address: str,
    agent_token_id: str | int,
    timeout: float = 30.0,
) -> Erc8004Binding:
    """Call `POST /v1/agent/{did}/erc8004` to verify and bind an on-chain ERC-8004 identity."""
    url = f"{oracle_url.rstrip('/')}/v1/agent/{did}/erc8004"
    body = {
        "chain_id": int(chain_id),
        "identity_registry_address": Web3.to_checksum_address(identity_registry_address),
        "agent_token_id": str(agent_token_id),
    }
    try:
        resp = requests.post(url, json=body, timeout=timeout)
    except requests.RequestException as exc:
        raise Erc8004BridgeError("link", None, str(exc), unreachable=True) from exc

    try:
        payload = resp.json()
    except ValueError:
        payload = None

    if resp.status_code not in (200, 201):
        detail = (
            payload.get("error")
            if isinstance(payload, dict) and isinstance(payload.get("error"), str)
            else resp.text
        )
        raise Erc8004BridgeError("link", resp.status_code, detail or f"HTTP {resp.status_code}")

    if not isinstance(payload, dict):
        raise Erc8004BridgeError("link", resp.status_code, f"malformed response: {resp.text}")

    return Erc8004Binding(
        agent_id=payload["agent_id"],
        chain_id=int(payload["chain_id"]),
        identity_registry_address=payload["identity_registry_address"],
        agent_token_id=str(payload["agent_token_id"]),
        registration_uri=payload["registration_uri"],
        registration_sha256=payload["registration_sha256"],
        nft_owner_address=payload["nft_owner_address"],
        agent_wallet_address=payload.get("agent_wallet_address"),
        binding_status=payload["binding_status"],
        name=payload["name"],
        description=payload["description"],
        x402_support=bool(payload.get("x402_support", False)),
        mcp_endpoint=payload.get("mcp_endpoint"),
        a2a_endpoint=payload.get("a2a_endpoint"),
        a2a_version=payload.get("a2a_version"),
        sovereign_actor_address=payload.get("sovereign_actor_address"),
        wallet_confined=bool(payload.get("wallet_confined", False)),
    )


def get_erc8004_from_oracle(
    oracle_url: str,
    did: str,
    *,
    timeout: float = 30.0,
) -> Optional[dict[str, Any]]:
    """Call `GET /v1/agent/{did}/erc8004` to read the Oracle's verified ERC-8004 binding row."""
    url = f"{oracle_url.rstrip('/')}/v1/agent/{did}/erc8004"
    try:
        resp = requests.get(url, timeout=timeout)
    except requests.RequestException as exc:
        raise Erc8004BridgeError("get", None, str(exc), unreachable=True) from exc

    if resp.status_code == 404:
        raise Erc8004BridgeError("get", 404, f"agent {did} is not registered with the Oracle")

    try:
        payload = resp.json()
    except ValueError as exc:
        raise Erc8004BridgeError("get", resp.status_code, f"malformed JSON: {resp.text}") from exc

    if resp.status_code != 200:
        detail = payload.get("error") if isinstance(payload, dict) else resp.text
        raise Erc8004BridgeError("get", resp.status_code, str(detail))

    return payload


__all__ = [
    "BASE_SEPOLIA_CHAIN_ID",
    "BASE_SEPOLIA_ERC8004_REGISTRY",
    "ERC8004_IDENTITY_REGISTRY_ABI",
    "Erc8004Binding",
    "Erc8004BridgeError",
    "REGISTRATION_TYPE",
    "build_registration_document",
    "caip10_registry",
    "encode_registration_data_uri",
    "get_erc8004_from_oracle",
    "link_erc8004_with_oracle",
    "register_and_link_erc8004",
    "resolve_confined_actor",
]
