"""Stable provider and store identity for local and hosted memory backends."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .memory import MemoryProvider


class StoreIdentityError(ValueError):
    """A provider/store identity is malformed or does not match its scope."""


_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")
_DID_RE = re.compile(r"^did:integrity:[A-Za-z0-9._:-]+$")


def _required(value: str, field: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise StoreIdentityError(f"{field} must be a non-empty lowercase-safe identifier")
    return value


@dataclass(frozen=True)
class StoreIdentity:
    """The stable namespace a memory provider must preserve across deployments."""

    provider_id: str
    store_id: str
    tenant_id: str
    agent_did: str

    def __post_init__(self) -> None:
        _required(self.provider_id, "provider_id")
        _required(self.store_id, "store_id")
        _required(self.tenant_id, "tenant_id")
        if not isinstance(self.agent_did, str) or not _DID_RE.fullmatch(self.agent_did):
            raise StoreIdentityError("agent_did must be a did:integrity identifier")

    @property
    def namespace_key(self) -> str:
        return f"{self.tenant_id}/{self.agent_did}/{self.store_id}"

    @classmethod
    def for_provider(
        cls,
        provider: MemoryProvider,
        *,
        tenant_id: str,
        agent_did: str,
        store_id: str,
    ) -> "StoreIdentity":
        provider_id = getattr(provider, "provider_id", None)
        if not isinstance(provider_id, str) or not provider_id:
            raise StoreIdentityError("provider must expose a non-empty provider_id")
        return cls(provider_id, store_id, tenant_id, agent_did)

    def assert_provider(self, provider: MemoryProvider) -> None:
        if getattr(provider, "provider_id", None) != self.provider_id:
            raise StoreIdentityError("provider_id does not match the store identity")

    def to_dict(self) -> dict[str, str]:
        return {
            "provider_id": self.provider_id,
            "store_id": self.store_id,
            "tenant_id": self.tenant_id,
            "agent_did": self.agent_did,
            "namespace_key": self.namespace_key,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "StoreIdentity":
        required = ("provider_id", "store_id", "tenant_id", "agent_did")
        if not isinstance(value, dict) or any(key not in value for key in required):
            raise StoreIdentityError("store identity is missing required fields")
        identity = cls(*(value[key] for key in required))
        if "namespace_key" in value and value["namespace_key"] != identity.namespace_key:
            raise StoreIdentityError("store identity namespace_key does not match its fields")
        return identity
