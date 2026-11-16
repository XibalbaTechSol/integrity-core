"""Local-first tenant, agent, and device identity contracts.

This module is deliberately a small reference implementation rather than a hosted
control plane. It stores public registration metadata in an atomic JSON document,
keeps tenant scoping explicit, and refuses conflicting re-registration. Private
keys and credentials never belong in this registry.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


REGISTRY_VERSION = "integrity.registry/1"
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_DID_RE = re.compile(r"^did:integrity:[A-Za-z0-9._:-]+$")
_STATUSES = frozenset({"active", "suspended", "revoked"})
ROLES = frozenset({"admin", "operator", "auditor", "member"})


class RegistryError(ValueError):
    """A registration is malformed, conflicting, or outside its tenant scope."""


def _id(value: str, field: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise RegistryError(f"{field} must match {_ID_RE.pattern}")
    return value


def _actor(value: str, field: str = "actor_id") -> str:
    if not isinstance(value, str):
        raise RegistryError(f"{field} must be a string")
    if _ID_RE.fullmatch(value) or _DID_RE.fullmatch(value):
        return value
    raise RegistryError(f"{field} must be a valid identifier or did:integrity")


def _did(value: str) -> str:
    if not isinstance(value, str) or not _DID_RE.fullmatch(value):
        raise RegistryError("agent_did must be a did:integrity identifier")
    return value


def _status(value: str, field: str = "status") -> str:
    if value not in _STATUSES:
        raise RegistryError(f"{field} must be one of {sorted(_STATUSES)}")
    return value


def _role(value: str) -> str:
    if value not in ROLES:
        raise RegistryError(f"role must be one of {sorted(ROLES)}")
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
    revocation_reason: str | None = None
    revoked_at: str | None = None

    def __post_init__(self) -> None:
        _id(self.tenant_id, "tenant_id")
        _id(self.device_id, "device_id")
        _did(self.agent_did)
        if not isinstance(self.public_key, str) or not self.public_key:
            raise RegistryError("public_key must be non-empty; private keys are not accepted")
        if not isinstance(self.pack_hash, str) or not self.pack_hash.startswith("sha256:"):
            raise RegistryError("pack_hash must be a sha256:... identifier")
        _status(self.status)


@dataclass(frozen=True)
class TenantRoleAssignment:
    tenant_id: str
    actor_id: str
    role: str
    assigned_at: str | None = None
    status: str = "active"

    def __post_init__(self) -> None:
        _id(self.tenant_id, "tenant_id")
        _actor(self.actor_id, "actor_id")
        _role(self.role)
        _status(self.status)


@dataclass(frozen=True)
class TenantPolicy:
    tenant_id: str
    retention_days: int = 90
    region: str = "local"
    fail_closed: bool = True
    allowed_export_formats: tuple[str, ...] = ("json", "ocsf", "vanta")

    def __post_init__(self) -> None:
        _id(self.tenant_id, "tenant_id")
        if not isinstance(self.retention_days, int) or self.retention_days < 0:
            raise RegistryError("retention_days must be non-negative integer")
        if not isinstance(self.region, str) or not self.region:
            raise RegistryError("region must be non-empty")


@dataclass(frozen=True)
class TenantAuditEvent:
    event_id: str
    tenant_id: str
    actor_id: str
    action: str
    target: str
    timestamp: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _id(self.tenant_id, "tenant_id")
        _actor(self.actor_id, "actor_id")
        if not self.event_id or not isinstance(self.event_id, str):
            raise RegistryError("event_id must be non-empty string")
        if not self.action or not isinstance(self.action, str):
            raise RegistryError("action must be non-empty string")


def _record(kind: str, value: Any) -> dict[str, Any]:
    return {"kind": kind, **asdict(value)}


class LocalRegistry:
    """Atomic local reference registry for public tenant, role, policy, and device metadata."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "registry_version": REGISTRY_VERSION,
                "tenants": {},
                "agents": {},
                "devices": {},
                "roles": {},
                "policies": {},
                "audit": [],
            }
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RegistryError(f"unable to read registry: {exc}") from exc
        if document.get("registry_version") != REGISTRY_VERSION:
            raise RegistryError("unsupported registry version")
        for key in ("tenants", "agents", "devices"):
            if not isinstance(document.get(key), dict):
                raise RegistryError(f"registry field {key!r} must be an object")
        if "roles" not in document or not isinstance(document["roles"], dict):
            document["roles"] = {}
        if "policies" not in document or not isinstance(document["policies"], dict):
            document["policies"] = {}
        if "audit" not in document or not isinstance(document["audit"], list):
            document["audit"] = []
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

    def revoke_device(self, tenant_id: str, device_id: str, reason: str = "operator_revoked") -> DeviceRegistration:
        document = self._read()
        current = document["devices"].get(device_id)
        if current is None or current["tenant_id"] != tenant_id:
            raise RegistryError(f"device {device_id!r} is not registered in tenant {tenant_id!r}")
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        updated = DeviceRegistration(
            tenant_id=current["tenant_id"],
            device_id=current["device_id"],
            agent_did=current["agent_did"],
            public_key=current["public_key"],
            pack_hash=current["pack_hash"],
            status="revoked",
            revocation_reason=reason,
            revoked_at=now_iso,
        )
        document["devices"][device_id] = _record("device", updated)
        self._write(document)
        return updated

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
        return DeviceRegistration(**{
            key: value[key] for key in (
                "tenant_id", "device_id", "agent_did", "public_key", "pack_hash",
                "status", "revocation_reason", "revoked_at"
            ) if key in value
        })

    def authorize_device(self, *, tenant_id: str, agent_did: str, device_id: str) -> DeviceRegistration:
        device = self.get_device(device_id, tenant_id=tenant_id)
        if device is None or device.agent_did != agent_did or device.status != "active":
            raise RegistryError("device is not active for the requested tenant and agent")
        return device

    # --- Role-Based Access Control (RBAC) ---

    def assign_role(self, role: TenantRoleAssignment) -> TenantRoleAssignment:
        document = self._read()
        if role.tenant_id not in document["tenants"]:
            raise RegistryError(f"tenant {role.tenant_id!r} is not registered")
        key = f"{role.tenant_id}:{role.actor_id}:{role.role}"
        assigned = role
        if not assigned.assigned_at:
            now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
            assigned = TenantRoleAssignment(
                tenant_id=role.tenant_id,
                actor_id=role.actor_id,
                role=role.role,
                assigned_at=now_iso,
                status=role.status,
            )
        document["roles"][key] = _record("role_assignment", assigned)
        self._write(document)
        return assigned

    def revoke_role(self, tenant_id: str, actor_id: str, role: str) -> None:
        document = self._read()
        key = f"{tenant_id}:{actor_id}:{role}"
        if key in document["roles"]:
            del document["roles"][key]
            self._write(document)

    def get_roles(self, tenant_id: str, actor_id: str | None = None) -> list[TenantRoleAssignment]:
        document = self._read()
        results: list[TenantRoleAssignment] = []
        for key, value in document["roles"].items():
            if value.get("tenant_id") == tenant_id:
                if actor_id is None or value.get("actor_id") == actor_id:
                    results.append(TenantRoleAssignment(
                        tenant_id=value["tenant_id"],
                        actor_id=value["actor_id"],
                        role=value["role"],
                        assigned_at=value.get("assigned_at"),
                        status=value.get("status", "active"),
                    ))
        return results

    def check_role(self, tenant_id: str, actor_id: str, required_role: str) -> bool:
        roles = self.get_roles(tenant_id, actor_id=actor_id)
        # Admin subsumes all operational roles
        for r in roles:
            if r.status == "active":
                if r.role == required_role or r.role == "admin":
                    return True
        return False

    # --- Tenant Policies (Retention & Region) ---

    def set_policy(self, policy: TenantPolicy) -> TenantPolicy:
        document = self._read()
        if policy.tenant_id not in document["tenants"]:
            raise RegistryError(f"tenant {policy.tenant_id!r} is not registered")
        document["policies"][policy.tenant_id] = _record("tenant_policy", policy)
        self._write(document)
        return policy

    def get_policy(self, tenant_id: str) -> TenantPolicy | None:
        document = self._read()
        value = document["policies"].get(tenant_id)
        if not value:
            return None
        return TenantPolicy(
            tenant_id=value["tenant_id"],
            retention_days=value.get("retention_days", 90),
            region=value.get("region", "local"),
            fail_closed=value.get("fail_closed", True),
            allowed_export_formats=tuple(value.get("allowed_export_formats", ("json", "ocsf", "vanta"))),
        )

    # --- Audit Logging ---

    def record_audit(self, event: TenantAuditEvent) -> TenantAuditEvent:
        document = self._read()
        if event.tenant_id not in document["tenants"]:
            raise RegistryError(f"tenant {event.tenant_id!r} is not registered")
        record = _record("audit_event", event)
        document["audit"].append(record)
        self._write(document)
        return event

    def get_audit_log(self, tenant_id: str, limit: int = 100) -> list[TenantAuditEvent]:
        document = self._read()
        events: list[TenantAuditEvent] = []
        for record in reversed(document["audit"]):
            if record.get("tenant_id") == tenant_id:
                events.append(TenantAuditEvent(
                    event_id=record["event_id"],
                    tenant_id=record["tenant_id"],
                    actor_id=record["actor_id"],
                    action=record["action"],
                    target=record["target"],
                    timestamp=record["timestamp"],
                    metadata=record.get("metadata", {}),
                ))
                if len(events) >= limit:
                    break
        return events

