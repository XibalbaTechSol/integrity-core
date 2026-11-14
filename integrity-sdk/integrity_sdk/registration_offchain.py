"""Client for the Oracle's gas-free off-chain agent registration route.

Proves control of an Ed25519 key by signing an RFC 8785 canonical JSON message;
no chain state is touched and no funder key is needed. The signed message is
byte-identical to the Oracle's `offchain_registration::signing_message`.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import requests

from integrity_sdk.core.jcs import canonical_bytes
from integrity_sdk.did import Keypair, fingerprint_for_pubkey

DOMAIN = "integrity.agent.register.offchain.v1"
_DID_PREFIX = "did:integrity:"


@dataclass(frozen=True)
class OffchainRegistration:
    agent_id: str
    verification_tier: int
    outcome: str  # "created" | "already_registered" | "key_attached"
    handle: str | None


class OffchainRegistrationError(RuntimeError):
    """`status` is the HTTP status, or None when the Oracle was unreachable."""

    def __init__(self, status: int | None, detail: str):
        super().__init__(f"off-chain registration failed ({status if status is not None else 'unreachable'}): {detail}")
        self.status = status
        self.detail = detail


def _normalize_hex(value: str) -> str:
    v = value.strip()
    if v[:2] in ("0x", "0X"):
        v = v[2:]
    return v.lower()


def signing_message(did: str, pubkey_hex: str, timestamp: int) -> bytes:
    return canonical_bytes({
        "did": did,
        "domain": DOMAIN,
        "ed25519_pubkey_hex": _normalize_hex(pubkey_hex),
        "timestamp": timestamp,
    })


def register_offchain(
    oracle_url: str,
    did: str,
    keypair: Keypair,
    *,
    handle: str | None = None,
    did_document: dict | None = None,
    timeout: float = 30.0,  # covers a Render free-tier cold start
    now: int | None = None,
) -> OffchainRegistration:
    pubkey = keypair.public_bytes()
    if did != _DID_PREFIX + fingerprint_for_pubkey(pubkey):
        raise ValueError("did does not match the keypair's public key")
    pubkey_hex = pubkey.hex()
    timestamp = int(time.time()) if now is None else now
    body: dict = {
        "did": did,
        "ed25519_pubkey_hex": pubkey_hex,
        "timestamp": timestamp,
        "signature": keypair.sign(signing_message(did, pubkey_hex, timestamp)).hex(),
    }
    if did_document is not None:
        body["did_document"] = did_document
    if handle is not None:
        body["handle"] = handle

    try:
        resp = requests.post(
            f"{oracle_url.rstrip('/')}/v1/agent/register/offchain", json=body, timeout=timeout
        )
    except requests.RequestException as exc:
        raise OffchainRegistrationError(None, str(exc)) from exc

    if resp.status_code not in (200, 201):
        detail = ""
        try:
            payload = resp.json()
            if isinstance(payload, dict) and isinstance(payload.get("error"), str):
                detail = payload["error"]
        except ValueError:
            pass
        raise OffchainRegistrationError(resp.status_code, detail or resp.text)

    try:
        data = resp.json()
        return OffchainRegistration(
            agent_id=data["agent_id"],
            verification_tier=int(data["verification_tier"]),
            outcome=data["outcome"],
            handle=data.get("handle"),
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise OffchainRegistrationError(resp.status_code, f"malformed response: {resp.text}") from exc
