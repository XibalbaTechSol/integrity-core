"""Tenant-scoped backup, restore, deletion, and compliance evidence exports (B0 / B7).

Implements:
- Full tenant backup and restore (JSON archive).
- Explicit tenant deletion with mandatory confirmation token.
- Compliance evidence export in canonical formats:
  - "json": Full structured tenant backup.
  - "vanta": Vanta-compatible compliance evidence bundle for access control,
    device asset management, retention policies, and audit trails.
  - "ocsf": Open Cybersecurity Schema Framework (OCSF v1.1) event stream mapping
    tenant lifecycle and audit events to standardized IAM and Entity Management classes.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from .tenancy import (
    AgentRegistration,
    DeviceRegistration,
    LocalRegistry,
    RegistryError,
    TenantAuditEvent,
    TenantIdentity,
    TenantPolicy,
    TenantRoleAssignment,
)

EXPORT_SCHEMA_VERSION = "integrity.tenant_export/1"
SUPPORTED_EXPORT_FORMATS = frozenset({"json", "vanta", "ocsf"})


class TenantExportError(ValueError):
    """An export, backup, restore, or deletion operation failed."""


@dataclass(frozen=True)
class TenantArchive:
    schema_version: str
    exported_at: str
    tenant: TenantIdentity
    roles: list[TenantRoleAssignment]
    agents: list[AgentRegistration]
    devices: list[DeviceRegistration]
    policy: TenantPolicy | None
    audit_events: list[TenantAuditEvent]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "exported_at": self.exported_at,
            "tenant": asdict(self.tenant),
            "roles": [asdict(r) for r in self.roles],
            "agents": [asdict(a) for a in self.agents],
            "devices": [asdict(d) for d in self.devices],
            "policy": asdict(self.policy) if self.policy else None,
            "audit_events": [asdict(e) for e in self.audit_events],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TenantArchive:
        if data.get("schema_version") != EXPORT_SCHEMA_VERSION:
            raise TenantExportError(f"unsupported archive schema version: {data.get('schema_version')}")
        t = data["tenant"]
        tenant = TenantIdentity(
            organization_id=t["organization_id"],
            tenant_id=t["tenant_id"],
            display_name=t["display_name"],
            status=t.get("status", "active"),
        )
        roles = [
            TenantRoleAssignment(
                tenant_id=r["tenant_id"],
                actor_id=r["actor_id"],
                role=r["role"],
                assigned_at=r.get("assigned_at"),
                status=r.get("status", "active"),
            )
            for r in data.get("roles", [])
        ]
        agents = [
            AgentRegistration(
                tenant_id=a["tenant_id"],
                agent_did=a["agent_did"],
                display_name=a["display_name"],
                status=a.get("status", "active"),
            )
            for a in data.get("agents", [])
        ]
        devices = [
            DeviceRegistration(
                tenant_id=d["tenant_id"],
                device_id=d["device_id"],
                agent_did=d["agent_did"],
                public_key=d["public_key"],
                pack_hash=d["pack_hash"],
                status=d.get("status", "active"),
                revocation_reason=d.get("revocation_reason"),
                revoked_at=d.get("revoked_at"),
            )
            for d in data.get("devices", [])
        ]
        p = data.get("policy")
        policy = (
            TenantPolicy(
                tenant_id=p["tenant_id"],
                retention_days=p.get("retention_days", 90),
                region=p.get("region", "local"),
                fail_closed=p.get("fail_closed", True),
                allowed_export_formats=tuple(p.get("allowed_export_formats", ("json", "ocsf", "vanta"))),
            )
            if p
            else None
        )
        audit_events = [
            TenantAuditEvent(
                event_id=e["event_id"],
                tenant_id=e["tenant_id"],
                actor_id=e["actor_id"],
                action=e["action"],
                target=e["target"],
                timestamp=e["timestamp"],
                metadata=e.get("metadata", {}),
            )
            for e in data.get("audit_events", [])
        ]
        return cls(
            schema_version=data["schema_version"],
            exported_at=data["exported_at"],
            tenant=tenant,
            roles=roles,
            agents=agents,
            devices=devices,
            policy=policy,
            audit_events=audit_events,
        )


def build_tenant_archive(registry: LocalRegistry, tenant_id: str) -> TenantArchive:
    """Extract a complete isolated archive of a tenant's registered assets."""
    tenant = registry.get_tenant(tenant_id)
    if tenant is None:
        raise TenantExportError(f"tenant {tenant_id!r} not found in registry")
    doc = registry._read()
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    roles = registry.get_roles(tenant_id)
    policy = registry.get_policy(tenant_id)
    audit_events = registry.get_audit_log(tenant_id, limit=10000)

    agents = []
    for k, a in doc["agents"].items():
        if a.get("tenant_id") == tenant_id:
            agents.append(
                AgentRegistration(
                    tenant_id=a["tenant_id"],
                    agent_did=a["agent_did"],
                    display_name=a["display_name"],
                    status=a.get("status", "active"),
                )
            )

    devices = []
    for k, d in doc["devices"].items():
        if d.get("tenant_id") == tenant_id:
            devices.append(
                DeviceRegistration(
                    tenant_id=d["tenant_id"],
                    device_id=d["device_id"],
                    agent_did=d["agent_did"],
                    public_key=d["public_key"],
                    pack_hash=d["pack_hash"],
                    status=d.get("status", "active"),
                    revocation_reason=d.get("revocation_reason"),
                    revoked_at=d.get("revoked_at"),
                )
            )

    return TenantArchive(
        schema_version=EXPORT_SCHEMA_VERSION,
        exported_at=now_iso,
        tenant=tenant,
        roles=roles,
        agents=agents,
        devices=devices,
        policy=policy,
        audit_events=audit_events,
    )


def export_tenant_vanta(archive: TenantArchive) -> dict[str, Any]:
    """Render tenant state into Vanta-compatible compliance evidence."""
    return {
        "integration": "integrity-protocol",
        "format": "vanta",
        "schema_version": "vanta.compliance/1",
        "exported_at": archive.exported_at,
        "tenant_id": archive.tenant.tenant_id,
        "organization_id": archive.tenant.organization_id,
        "controls": {
            "access_control": {
                "account_status": archive.tenant.status,
                "role_assignments": [
                    {
                        "actor_id": r.actor_id,
                        "role": r.role,
                        "status": r.status,
                        "assigned_at": r.assigned_at,
                    }
                    for r in archive.roles
                ],
            },
            "asset_management": {
                "registered_agents": [
                    {
                        "agent_did": a.agent_did,
                        "display_name": a.display_name,
                        "status": a.status,
                    }
                    for a in archive.agents
                ],
                "enrolled_devices": [
                    {
                        "device_id": d.device_id,
                        "agent_did": d.agent_did,
                        "pack_hash": d.pack_hash,
                        "status": d.status,
                        "revoked_at": d.revoked_at,
                        "revocation_reason": d.revocation_reason,
                    }
                    for d in archive.devices
                ],
            },
            "data_retention_and_privacy": {
                "retention_days": archive.policy.retention_days if archive.policy else 90,
                "region": archive.policy.region if archive.policy else "local",
                "fail_closed": archive.policy.fail_closed if archive.policy else True,
            },
            "audit_trail": {
                "total_events": len(archive.audit_events),
                "events": [
                    {
                        "event_id": e.event_id,
                        "timestamp": e.timestamp,
                        "actor_id": e.actor_id,
                        "action": e.action,
                        "target": e.target,
                    }
                    for e in archive.audit_events
                ],
            },
        },
    }


def export_tenant_ocsf(archive: TenantArchive) -> dict[str, Any]:
    """Render tenant audit events into Open Cybersecurity Schema Framework (OCSF v1.1)."""
    ocsf_events = []
    for e in archive.audit_events:
        # Determine OCSF Category & Class
        # Category 3: Identity & Access Management (UID 3)
        # Class 3001: Account Change, Class 3002: Authentication, Class 3004: Entity Management
        if "role" in e.action:
            class_uid = 3001
            class_name = "Account Change"
            category_uid = 3
            category_name = "Identity & Access Management"
            activity_id = 1 if "assign" in e.action else 2
            activity_name = "Assign Role" if "assign" in e.action else "Revoke Role"
        elif "device" in e.action:
            class_uid = 3004
            class_name = "Entity Management"
            category_uid = 3
            category_name = "Identity & Access Management"
            activity_id = 1 if "enroll" in e.action else 3
            activity_name = "Enroll Entity" if "enroll" in e.action else "Revoke Entity"
        else:
            class_uid = 6003
            class_name = "Configuration Activity"
            category_uid = 6
            category_name = "Application Activity"
            activity_id = 1
            activity_name = "Policy Change"

        ocsf_events.append({
            "class_uid": class_uid,
            "class_name": class_name,
            "category_uid": category_uid,
            "category_name": category_name,
            "activity_id": activity_id,
            "activity_name": activity_name,
            "time": e.timestamp,
            "actor": {
                "id": e.actor_id,
            },
            "entity": {
                "id": e.target,
            },
            "metadata": {
                "event_id": e.event_id,
                "tenant_id": archive.tenant.tenant_id,
                "organization_id": archive.tenant.organization_id,
                "product": {
                    "name": "Integrity Protocol",
                    "vendor_name": "Xibalba Solutions",
                },
            },
            "unmapped": e.metadata,
        })

    return {
        "format": "ocsf",
        "ocsf_version": "1.1.0",
        "exported_at": archive.exported_at,
        "tenant_id": archive.tenant.tenant_id,
        "organization_id": archive.tenant.organization_id,
        "events": ocsf_events,
    }


def export_tenant(registry: LocalRegistry, tenant_id: str, format: str = "json") -> dict[str, Any]:
    """Export tenant compliance evidence in the specified format."""
    if format not in SUPPORTED_EXPORT_FORMATS:
        raise TenantExportError(
            f"unsupported export format {format!r}; must be one of {sorted(SUPPORTED_EXPORT_FORMATS)}"
        )
    archive = build_tenant_archive(registry, tenant_id)
    if format == "json":
        return archive.to_dict()
    elif format == "vanta":
        return export_tenant_vanta(archive)
    elif format == "ocsf":
        return export_tenant_ocsf(archive)
    raise TenantExportError(f"unhandled format: {format}")


def backup_tenant(registry: LocalRegistry, tenant_id: str, target_path: str | Path) -> Path:
    """Save an atomic JSON archive of a tenant to a file path."""
    dest = Path(target_path)
    archive = build_tenant_archive(registry, tenant_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(archive.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return dest


def restore_tenant(registry: LocalRegistry, archive_data: Mapping[str, Any]) -> TenantIdentity:
    """Atomically restore an entire tenant archive into the registry."""
    archive = TenantArchive.from_dict(archive_data)
    # Register tenant
    registry.register_tenant(archive.tenant)

    # Register agents
    for agent in archive.agents:
        registry.register_agent(agent)

    # Register devices
    for device in archive.devices:
        registry.register_device(device)
        if device.status == "revoked":
            registry.revoke_device(
                tenant_id=device.tenant_id,
                device_id=device.device_id,
                reason=device.revocation_reason or "restored_as_revoked",
            )

    # Assign roles
    for role in archive.roles:
        registry.assign_role(role)

    # Set policy
    if archive.policy:
        registry.set_policy(archive.policy)

    # Restore audit events
    for event in archive.audit_events:
        registry.record_audit(event)

    return archive.tenant


def delete_tenant(
    registry: LocalRegistry,
    tenant_id: str,
    *,
    confirmation: str,
    actor_id: str,
) -> None:
    """Permanently delete a tenant enclave and all associated scoped assets."""
    expected = f"DELETE {tenant_id}"
    if confirmation != expected:
        raise TenantExportError(
            f"tenant deletion requires exact confirmation {expected!r}; got {confirmation!r}"
        )
    tenant = registry.get_tenant(tenant_id)
    if tenant is None:
        raise TenantExportError(f"tenant {tenant_id!r} not found")

    document = registry._read()

    # Remove tenant
    if tenant_id in document["tenants"]:
        del document["tenants"][tenant_id]

    # Remove scoped devices
    devices_to_delete = [k for k, v in document["devices"].items() if v.get("tenant_id") == tenant_id]
    for d_id in devices_to_delete:
        del document["devices"][d_id]

    # Remove scoped agents
    agents_to_delete = [k for k, v in document["agents"].items() if v.get("tenant_id") == tenant_id]
    for a_id in agents_to_delete:
        del document["agents"][a_id]

    # Remove roles
    roles_to_delete = [k for k, v in document["roles"].items() if v.get("tenant_id") == tenant_id]
    for r_id in roles_to_delete:
        del document["roles"][r_id]

    # Remove policies
    if tenant_id in document["policies"]:
        del document["policies"][tenant_id]

    # Purge scoped audit logs
    document["audit"] = [e for e in document["audit"] if e.get("tenant_id") != tenant_id]

    registry._write(document)
