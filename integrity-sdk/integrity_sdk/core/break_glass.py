"""Short-lived, signed break-glass approvals for local enforcement gates."""

from __future__ import annotations

import datetime as dt
import secrets
from typing import Collection, Mapping

from ..did import Keypair, public_key_multibase
from .jcs import canonical_bytes
from .signing import signer_matches, verify_multibase_signature


_DOMAIN = b"integrity.break-glass.v1\x00"
_VERSION = "integrity.break-glass/1"


class BreakGlassError(ValueError):
    """A break-glass approval is malformed, untrusted, tampered, or expired."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def _parse_timestamp(value: str, field: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise BreakGlassError("MALFORMED", f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise BreakGlassError("MALFORMED", f"{field} must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def create_approval(
    signer: Keypair,
    *,
    tenant_id: str,
    agent_did: str,
    reason: str,
    issued_at: str,
    expires_at: str,
    nonce: str | None = None,
) -> dict[str, str]:
    """Create a signed approval; callers must choose a bounded expiry."""
    issued = _parse_timestamp(issued_at, "issued_at")
    expires = _parse_timestamp(expires_at, "expires_at")
    if expires <= issued:
        raise BreakGlassError("MALFORMED", "expires_at must be after issued_at")
    if not tenant_id or not agent_did or not reason.strip():
        raise BreakGlassError("MALFORMED", "tenant_id, agent_did, and reason are required")
    body = {
        "schema_version": _VERSION,
        "tenant_id": tenant_id,
        "agent_did": agent_did,
        "reason": reason,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "nonce": nonce or secrets.token_hex(16),
        "signer_key": public_key_multibase(signer.public_bytes()),
    }
    return {**body, "signature": signer.sign(_DOMAIN + canonical_bytes(body)).hex()}


def verify_approval(
    approval: Mapping[str, object],
    *,
    trusted_signers: Collection[str],
    now: dt.datetime | None = None,
) -> dict[str, str]:
    """Verify an approval and return its normalized string fields."""
    required = {"schema_version", "tenant_id", "agent_did", "reason", "issued_at", "expires_at", "nonce", "signer_key", "signature"}
    if set(approval) != required or not all(isinstance(approval[key], str) for key in required):
        raise BreakGlassError("MALFORMED", "approval fields are incomplete or have invalid types")
    value = {key: str(approval[key]) for key in required}
    if value["schema_version"] != _VERSION or not value["reason"].strip():
        raise BreakGlassError("MALFORMED", "unsupported version or empty reason")
    issued = _parse_timestamp(value["issued_at"], "issued_at")
    expires = _parse_timestamp(value["expires_at"], "expires_at")
    current = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    if expires <= issued:
        raise BreakGlassError("MALFORMED", "expires_at must be after issued_at")
    if current < issued or current >= expires:
        raise BreakGlassError("EXPIRED", "approval is outside its validity window")
    if not trusted_signers or not signer_matches(value["signer_key"], trusted_signers):
        raise BreakGlassError("UNTRUSTED_SIGNER", "approval signer is not trusted")
    signed_body = {key: value[key] for key in required if key != "signature"}
    if not verify_multibase_signature(value["signer_key"], _DOMAIN + canonical_bytes(signed_body), value["signature"]):
        raise BreakGlassError("BAD_SIGNATURE", "approval signature does not verify")
    return value
