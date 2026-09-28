"""Local-first entitlement and capability checks without billing semantics."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass


class CapabilityDenied(PermissionError):
    """A tenant or capability is not entitled to perform an operation."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


_CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")


def _timestamp(value: str | None, field: str) -> dt.datetime | None:
    if value is None:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


@dataclass(frozen=True)
class EntitlementSet:
    tenant_id: str
    capabilities: frozenset[str]
    revision: int = 0
    expires_at: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, str) or not _ID_RE.fullmatch(self.tenant_id):
            raise ValueError("tenant_id must be a valid tenant identifier")
        if not isinstance(self.capabilities, frozenset) or not all(
            isinstance(capability, str) and _CAPABILITY_RE.fullmatch(capability)
            for capability in self.capabilities
        ):
            raise ValueError("capabilities must be a frozenset of valid capability identifiers")
        if not isinstance(self.revision, int) or self.revision < 0:
            raise ValueError("revision must be a non-negative integer")
        _timestamp(self.expires_at, "expires_at")

    def allows(self, capability: str, *, now: dt.datetime | None = None) -> bool:
        if not isinstance(capability, str) or not _CAPABILITY_RE.fullmatch(capability):
            return False
        expiry = _timestamp(self.expires_at, "expires_at")
        current = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
        return capability in self.capabilities and (expiry is None or current < expiry)

    def require(self, capability: str, *, tenant_id: str | None = None, now: dt.datetime | None = None) -> None:
        if tenant_id is not None and tenant_id != self.tenant_id:
            raise CapabilityDenied("TENANT_MISMATCH", "capability was issued for a different tenant")
        if not self.allows(capability, now=now):
            raise CapabilityDenied("CAPABILITY_DENIED", f"tenant {self.tenant_id!r} is not entitled to {capability!r}")

    def to_dict(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "capabilities": sorted(self.capabilities),
            "revision": self.revision,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "EntitlementSet":
        capabilities = value.get("capabilities")
        if not isinstance(capabilities, list):
            raise ValueError("capabilities must be a list in serialized entitlements")
        return cls(
            tenant_id=value.get("tenant_id", ""),
            capabilities=frozenset(capabilities),
            revision=value.get("revision", 0),
            expires_at=value.get("expires_at"),
        )


def require_capability(
    entitlements: EntitlementSet,
    capability: str,
    *,
    tenant_id: str,
    now: dt.datetime | None = None,
) -> None:
    """Shared guard used by local implementations before an operation starts."""
    entitlements.require(capability, tenant_id=tenant_id, now=now)
