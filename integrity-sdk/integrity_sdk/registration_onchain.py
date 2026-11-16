"""On-chain agent registration (registration v3 Phase 4, PR 4.4): the `register --onchain` flow.

`register_onchain` runs the four steps of the plan, in order:

1. `register_offchain` (idempotent): the Oracle must already hold the DID's Ed25519 key.
2. `POST /v1/agent/{id}/onchain/attestation`: the agent signs the EIP-712 `RegisterAgent` digest
   with its Ed25519 key, and the Oracle returns its attester's ECDSA signature over the same digest.
3. One `AgentRegistry.register(...)` transaction from the guardian wallet. With `confined=True`,
   the guardian first deploys a `SovereignAgent` it controls, and the register call goes
   through that agent's own `execute`: `msg.sender == actor` is the actor's consent, so no
   EIP-1271 signature is needed.
4. `POST /v1/agent/{id}/onchain/sync`: the Oracle re-reads the record from the chain.

The digest is computed locally (`register_digest`) and must equal the one the Oracle attests, so
a misconfigured Oracle is refused before any gas is spent. Its golden vector is shared with the
Oracle (`onchain_registration.rs::digest_matches_independent_eip712_vector`).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Optional

import requests
from eth_account.messages import encode_typed_data
from eth_account.signers.local import LocalAccount
from eth_utils import keccak
from web3 import Web3

from integrity_sdk import chain
from integrity_sdk.did import Keypair, fingerprint_for_pubkey
from integrity_sdk.registration_offchain import OffchainRegistrationError, register_offchain

EIP712_NAME = "IntegrityAgentRegistry"
EIP712_VERSION = "1"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
ZERO_BYTES32 = b"\x00" * 32
PROOF_ATTESTATION = 1
# The Oracle refuses deadlines more than 24 h ahead; 15 minutes covers a slow RPC comfortably.
DEFAULT_DEADLINE_SECS = 900
_DID_PREFIX = "did:integrity:"

_REGISTER_AGENT_TYPES = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
    "RegisterAgent": [
        {"name": "pubkey", "type": "bytes32"},
        {"name": "guardian", "type": "address"},
        {"name": "actor", "type": "address"},
        {"name": "domainId", "type": "bytes32"},
        {"name": "uriHash", "type": "bytes32"},
        {"name": "deadline", "type": "uint256"},
    ],
}


class OnchainRegistrationError(RuntimeError):
    """A refused or failed Oracle step.

    `status` is the HTTP status, or None when the Oracle was unreachable or answered with
    something unusable. `stage` is "attestation" or "sync". `unreachable` means "can't tell right
    now": no answer, or a 5xx (which includes the Oracle having no AgentRegistry configured).
    """

    def __init__(self, stage: str, status: Optional[int], detail: str, *, unreachable: bool = False):
        super().__init__(f"on-chain {stage} failed ({status if status is not None else 'no status'}): {detail}")
        self.stage, self.status, self.detail = stage, status, detail
        self.unreachable = unreachable or (status is not None and status >= 500)


@dataclass(frozen=True)
class OnchainAttestation:
    digest: bytes
    attestation: bytes
    attester: str
    proof_kind: int
    chain_id: int
    agent_registry: str
    pubkey: bytes
    guardian: str
    actor: str
    domain_id: bytes
    uri: str
    deadline: int


@dataclass(frozen=True)
class OnchainRegistration:
    agent_id: str
    outcome: str  # "registered" | "already_registered"
    guardian: str
    actor: Optional[str]
    domain_id: Optional[str]
    tx: Optional[str]
    record: dict[str, Any]  # the Oracle's synced `agent_onchain_records` row


def _b32(value: bytes | str) -> bytes:
    raw = bytes.fromhex(value[2:] if value[:2] in ("0x", "0X") else value) if isinstance(value, str) else value
    if len(raw) != 32:
        raise ValueError(f"expected 32 bytes, got {len(raw)}")
    return raw


def domain_id(value: str) -> bytes:
    """A `--domain` argument: a 0x-prefixed bytes32 id, or a name hashed as `keccak256(bytes(name))`
    (the id `integrity domain register NAME` creates)."""
    if value[:2] in ("0x", "0X"):
        return _b32(value)
    return keccak(text=value)


def register_digest(
    chain_id: int,
    agent_registry: str,
    *,
    pubkey: bytes,
    guardian: str,
    actor: str = ZERO_ADDRESS,
    domain_id: bytes = ZERO_BYTES32,
    uri: str = "",
    deadline: int,
) -> bytes:
    """`AgentRegistry.registerDigest(...)`: the EIP-712 `RegisterAgent` digest, computed locally."""
    message = encode_typed_data(full_message={
        "types": _REGISTER_AGENT_TYPES,
        "primaryType": "RegisterAgent",
        "domain": {
            "name": EIP712_NAME, "version": EIP712_VERSION, "chainId": chain_id,
            "verifyingContract": Web3.to_checksum_address(agent_registry),
        },
        "message": {
            "pubkey": _b32(pubkey), "guardian": Web3.to_checksum_address(guardian),
            "actor": Web3.to_checksum_address(actor), "domainId": _b32(domain_id),
            "uriHash": keccak(text=uri), "deadline": deadline,
        },
    })
    return keccak(b"\x19" + message.version + message.header + message.body)


def _post(stage: str, url: str, body: dict, timeout: float) -> dict:
    try:
        resp = requests.post(url, json=body, timeout=timeout)
    except requests.RequestException as exc:
        raise OnchainRegistrationError(stage, None, str(exc), unreachable=True) from exc
    try:
        payload = resp.json()
    except ValueError:
        payload = None
    if resp.status_code not in (200, 201):
        detail = payload.get("error") if isinstance(payload, dict) and isinstance(payload.get("error"), str) else None
        raise OnchainRegistrationError(stage, resp.status_code, detail or resp.text)
    if not isinstance(payload, dict):
        raise OnchainRegistrationError(stage, resp.status_code, f"malformed response: {resp.text}")
    return payload


def request_attestation(
    oracle_url: str,
    did: str,
    keypair: Keypair,
    *,
    chain_id: int,
    agent_registry: str,
    guardian: str,
    actor: str = ZERO_ADDRESS,
    domain: bytes = ZERO_BYTES32,
    uri: str = "",
    deadline: int,
    timeout: float = 30.0,
) -> OnchainAttestation:
    """Signs the `RegisterAgent` digest with the agent's Ed25519 key and asks the Oracle to attest it.

    Refuses an attestation over any other digest: an Oracle configured for another chain or
    registry would otherwise hand back a proof that `register` reverts on.
    """
    digest = register_digest(chain_id, agent_registry, pubkey=keypair.public_bytes(), guardian=guardian,
                             actor=actor, domain_id=domain, uri=uri, deadline=deadline)
    body = {
        "guardian": Web3.to_checksum_address(guardian),
        "actor": Web3.to_checksum_address(actor),
        "domain_id": "0x" + _b32(domain).hex(),
        "uri": uri,
        "deadline": deadline,
        "signature": keypair.sign(digest).hex(),
    }
    data = _post("attestation", f"{oracle_url.rstrip('/')}/v1/agent/{did}/onchain/attestation", body, timeout)
    try:
        attested = _b32(data["digest"])
        attestation = OnchainAttestation(
            digest=attested,
            attestation=bytes.fromhex(data["attestation"].removeprefix("0x")),
            attester=data["attester"],
            proof_kind=int(data["proof_kind"]),
            chain_id=int(data["chain_id"]),
            agent_registry=data["agent_registry"],
            pubkey=_b32(data["pubkey"]),
            guardian=data["guardian"],
            actor=data["actor"],
            domain_id=_b32(data["domain_id"]),
            uri=data["uri"],
            deadline=int(data["deadline"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise OnchainRegistrationError("attestation", None, f"malformed attestation: {data}") from exc
    if attested != digest:
        raise OnchainRegistrationError(
            "attestation", None,
            f"the Oracle attested digest 0x{attested.hex()} but this chain's AgentRegistry digest is "
            f"0x{digest.hex()} (Oracle chain {attestation.chain_id}, registry {attestation.agent_registry}; "
            f"expected chain {chain_id}, registry {agent_registry})",
        )
    return attestation


def sync_onchain(oracle_url: str, did: str, *, timeout: float = 30.0) -> dict[str, Any]:
    """`POST /v1/agent/{id}/onchain/sync`: the Oracle re-reads the record from the chain."""
    return _post("sync", f"{oracle_url.rstrip('/')}/v1/agent/{did}/onchain/sync", {}, timeout)


@lru_cache(maxsize=1)
def _error_selectors() -> dict[str, str]:
    names: dict[str, str] = {}
    for contract in ("AgentRegistry", "SovereignAgent", "DomainRegistry"):
        for item in chain._load_artifact(contract)["abi"]:
            if item.get("type") == "error":
                sig = f"{item['name']}({','.join(i['type'] for i in item['inputs'])})"
                names["0x" + keccak(text=sig)[:4].hex()] = item["name"]
    return names


def revert_name(exc: BaseException) -> Optional[str]:
    """The custom-error name of a registry/agent revert (`AlreadyRegistered`, ...), else None."""
    data = getattr(exc, "data", None)
    if not isinstance(data, str) or len(data) < 10:
        return None
    return _error_selectors().get(data[:10].lower())


def register_onchain(
    w3: Web3,
    oracle_url: str,
    did: str,
    keypair: Keypair,
    guardian: LocalAccount,
    agent_registry: str,
    *,
    confined: bool = False,
    domain: Optional[bytes] = None,
    uri: str = "",
    did_document: Optional[dict] = None,
    deadline_secs: int = DEFAULT_DEADLINE_SECS,
    timeout: float = 30.0,
) -> OnchainRegistration:
    """Off-chain register, attest, one `AgentRegistry.register` transaction, then sync.

    Idempotent: when the DID already has an on-chain record, nothing is deployed or sent, and the
    record is just synced (`outcome="already_registered"`).

    Raises `OffchainRegistrationError` / `OnchainRegistrationError` for Oracle refusals and
    outages, and web3's `ContractLogicError` / `ContractCustomError` for a revert
    (`revert_name` decodes the name).
    """
    if did != _DID_PREFIX + fingerprint_for_pubkey(keypair.public_bytes()):
        raise ValueError("did does not match the keypair's public key")
    if confined and domain is None:
        raise ValueError("a confined agent needs a domain: AgentRegistry requires one when an actor is bound")

    register_offchain(oracle_url, did, keypair, did_document=did_document, timeout=timeout)

    registry = chain._contract(w3, "AgentRegistry", address=agent_registry)
    existing = chain._call_with_retry(registry.functions.resolveDID(did).call)
    if existing[5]:  # registeredAt
        record = sync_onchain(oracle_url, did, timeout=timeout)
        actor = existing[2] if existing[2] != ZERO_ADDRESS else None
        return OnchainRegistration(did, "already_registered", existing[1], actor,
                                   "0x" + existing[3].hex(), None, record)

    chain_id = w3.eth.chain_id
    actor = ZERO_ADDRESS
    if confined:
        actor = chain.deploy_sovereign_agent(w3, guardian, did, ZERO_ADDRESS, chain_id, agent_registry)
    dom = domain if domain is not None else ZERO_BYTES32
    deadline = int(time.time()) + deadline_secs
    att = request_attestation(oracle_url, did, keypair, chain_id=chain_id, agent_registry=agent_registry,
                              guardian=guardian.address, actor=actor, domain=dom, uri=uri,
                              deadline=deadline, timeout=timeout)

    register_call = registry.functions.register(
        keypair.public_bytes(), guardian.address, Web3.to_checksum_address(actor), dom, uri, deadline,
        att.proof_kind, att.attestation, b"",  # no EIP-1271 consent: msg.sender is the actor itself
    )
    if confined:
        calldata = register_call.build_transaction({"gas": 0})["data"]
        sovereign_agent = chain._contract(w3, "SovereignAgent", address=actor)
        call = sovereign_agent.functions.execute(Web3.to_checksum_address(agent_registry), 0, calldata)
    else:
        call = register_call
    receipt, tx_hash = chain._send_signed(
        w3, guardian,
        lambda nonce: call.build_transaction({"from": guardian.address, "nonce": nonce, "chainId": chain_id}),
        action="agent_registry_register",
    )
    record = sync_onchain(oracle_url, did, timeout=timeout)
    return OnchainRegistration(
        did, "registered", guardian.address, actor if confined else None,
        "0x" + dom.hex() if domain is not None else None, tx_hash.hex(), record,
    )


__all__ = [
    "DEFAULT_DEADLINE_SECS", "OffchainRegistrationError", "OnchainAttestation", "OnchainRegistration",
    "OnchainRegistrationError", "domain_id", "register_digest", "register_onchain", "request_attestation",
    "revert_name", "sync_onchain",
]
