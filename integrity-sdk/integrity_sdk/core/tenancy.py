"""Local-first tenant, agent, and device identity contracts.

This module is deliberately a small reference implementation rather than a hosted
control plane. It stores public registration metadata in an atomic JSON document,
keeps tenant scoping explicit, and refuses conflicting re-registration. Private
keys and credentials never belong in this registry.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


REGISTRY_VERSION = "integrity.registry/1"
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_DID_RE = re.compile(r"^did:integrity:[A-Za-z0-9._:-]+$")
_STATUSES = frozenset({"active", "suspended", "revoked"})


class RegistryError(ValueError):
    """A registration is malformed, conflicting, or outside its tenant scope."""


def _id(value: str, field: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise RegistryError(f"{field} must match {_ID_RE.pattern}")
    return value


def _did(value: str) -> str:
    if not isinstance(value, str) or not _DID_RE.fullmatch(value):
        raise RegistryError("agent_did must be a did:integrity identifier")
    return value


def _status(value: str, field: str = "status") -> str:
    if value not in _STATUSES:
        raise RegistryError(f"{field} must be one of {sorted(_STATUSES)}")
    return value


@dataclass(frozen=True)
class TenantIdentity:
    organization_id: str
    tenant_id: str
    display_name: str
    status: str = "active"

    def __post_init__(self) -> None:
        _id(self.organization_id, "organization_id")
        _id(self.tenant_id, "tenant_id")
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            raise RegistryError("display_name must be non-empty")
        _status(self.status)


@dataclass(frozen=True)
class AgentRegistration:
    tenant_id: str
    agent_did: str
    display_name: str
    status: str = "active"

    def __post_init__(self) -> None:
        _id(self.tenant_id, "tenant_id")
        _did(self.agent_did)
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            raise RegistryError("display_name must be non-empty")
        _status(self.status)


@dataclass(frozen=True)
class DeviceRegistration:
    tenant_id: str
    device_id: str
    agent_did: str
    public_key: str
    pack_hash: str
    status: str = "active"

    def __post_init__(self) -> None:
        _id(self.tenant_id, "tenant_id")
        _id(self.device_id, "device_id")
        _did(self.agent_did)
        if not isinstance(self.public_key, str) or not self.public_key:
            raise RegistryError("public_key must be non-empty; private keys are not accepted")
        if not isinstance(self.pack_hash, str) or not self.pack_hash.startswith("sha256:"):
            raise RegistryError("pack_hash must be a sha256:... identifier")
        _status(self.status)


def _record(kind: str, value: Any) -> dict[str, Any]:
    return {"kind": kind, **asdict(value)}


class LocalRegistry:
    """Atomic local reference registry for public tenant and device metadata."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"registry_version": REGISTRY_VERSION, "tenants": {}, "agents": {}, "devices": {}}
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RegistryError(f"unable to read registry: {exc}") from exc
        if document.get("registry_version") != REGISTRY_VERSION:
            raise RegistryError("unsupported registry version")
        for key in ("tenants", "agents", "devices"):
            if not isinstance(document.get(key), dict):
                raise RegistryError(f"registry field {key!r} must be an object")
        return document

    def _write(self, document: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(document, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    def register_tenant(self, tenant: TenantIdentity) -> TenantIdentity:
        document = self._read()
        current = document["tenants"].get(tenant.tenant_id)
        value = _record("tenant", tenant)
        if current is not None and current != value:
            raise RegistryError(f"tenant {tenant.tenant_id!r} is already registered with different metadata")
        document["tenants"][tenant.tenant_id] = value
        self._write(document)
        return tenant

    def register_agent(self, agent: AgentRegistration) -> AgentRegistration:
        document = self._read()
        if agent.tenant_id not in document["tenants"]:
            raise RegistryError(f"tenant {agent.tenant_id!r} is not registered")
        key = agent.agent_did
        value = _record("agent", agent)
        current = document["agents"].get(key)
        if current is not None and current != value:
            raise RegistryError(f"agent {key!r} is already registered with different metadata")
        document["agents"][key] = value
        self._write(document)
        return agent

    def register_device(self, device: DeviceRegistration) -> DeviceRegistration:
        document = self._read()
        if device.tenant_id not in document["tenants"]:
            raise RegistryError(f"tenant {device.tenant_id!r} is not registered")
        agent = document["agents"].get(device.agent_did)
        if agent is None or agent["tenant_id"] != device.tenant_id:
            raise RegistryError("device agent is not registered in the same tenant")
        value = _record("device", device)
        current = document["devices"].get(device.device_id)
        if current is not None and current != value:
            raise RegistryError(f"device {device.device_id!r} is already registered with different metadata")
        document["devices"][device.device_id] = value
        self._write(document)
        return device

    def get_tenant(self, tenant_id: str) -> TenantIdentity | None:
        value = self._read()["tenants"].get(tenant_id)
        return TenantIdentity(**{key: value[key] for key in ("organization_id", "tenant_id", "display_name", "status")}) if value else None

    def get_agent(self, agent_did: str, *, tenant_id: str | None = None) -> AgentRegistration | None:
        value = self._read()["agents"].get(agent_did)
        if value is None or (tenant_id is not None and value["tenant_id"] != tenant_id):
            return None
        return AgentRegistration(**{key: value[key] for key in ("tenant_id", "agent_did", "display_name", "status")})

    def get_device(self, device_id: str, *, tenant_id: str | None = None) -> DeviceRegistration | None:
        value = self._read()["devices"].get(device_id)
        if value is None or (tenant_id is not None and value["tenant_id"] != tenant_id):
            return None
        return DeviceRegistration(**{key: value[key] for key in ("tenant_id", "device_id", "agent_did", "public_key", "pack_hash", "status")})

    def authorize_device(self, *, tenant_id: str, agent_did: str, device_id: str) -> DeviceRegistration:
        device = self.get_device(device_id, tenant_id=tenant_id)
        if device is None or device.agent_did != agent_did or device.status != "active":
            raise RegistryError("device is not active for the requested tenant and agent")
        return device
