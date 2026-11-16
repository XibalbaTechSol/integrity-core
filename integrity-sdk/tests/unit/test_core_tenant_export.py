from __future__ import annotations

import json
import pytest

from integrity_sdk.core import (
    AgentRegistration,
    DeviceRegistration,
    LocalRegistry,
    TenantAuditEvent,
    TenantIdentity,
    TenantPolicy,
    TenantRoleAssignment,
    backup_tenant,
    delete_tenant,
    export_tenant,
    restore_tenant,
    TenantExportError,
)

TENANT_1 = TenantIdentity("org-acme", "tenant-alpha", "Acme Alpha")
TENANT_2 = TenantIdentity("org-acme", "tenant-beta", "Acme Beta")

AGENT_1 = AgentRegistration(TENANT_1.tenant_id, "did:integrity:agent-alpha-1", "Alpha Agent 1")
DEVICE_1 = DeviceRegistration(
    TENANT_1.tenant_id, "device-alpha-1", AGENT_1.agent_did, "zpublic-key-1", "sha256:" + "1" * 64
)

ROLE_ADMIN = TenantRoleAssignment(TENANT_1.tenant_id, "user-admin", "admin")
ROLE_OP = TenantRoleAssignment(TENANT_1.tenant_id, "user-op", "operator")

POLICY_1 = TenantPolicy(
    tenant_id=TENANT_1.tenant_id,
    retention_days=60,
    region="us-east-1",
    fail_closed=True,
    allowed_export_formats=("json", "vanta", "ocsf"),
)

AUDIT_1 = TenantAuditEvent(
    event_id="evt-001",
    tenant_id=TENANT_1.tenant_id,
    actor_id="user-admin",
    action="role.assign",
    target="user-op",
    timestamp="2026-11-16T08:00:00Z",
    metadata={"role": "operator"},
)

AUDIT_2 = TenantAuditEvent(
    event_id="evt-002",
    tenant_id=TENANT_1.tenant_id,
    actor_id="user-admin",
    action="device.enroll",
    target=DEVICE_1.device_id,
    timestamp="2026-11-16T08:05:00Z",
    metadata={"public_key": DEVICE_1.public_key},
)


@pytest.fixture
def populated_registry(tmp_path):
    reg = LocalRegistry(tmp_path / "registry.json")
    reg.register_tenant(TENANT_1)
    reg.register_agent(AGENT_1)
    reg.register_device(DEVICE_1)
    reg.assign_role(ROLE_ADMIN)
    reg.assign_role(ROLE_OP)
    reg.set_policy(POLICY_1)
    reg.record_audit(AUDIT_1)
    reg.record_audit(AUDIT_2)

    # Register tenant 2 to verify isolation
    reg.register_tenant(TENANT_2)
    return reg


def test_export_tenant_json(populated_registry):
    exported = export_tenant(populated_registry, TENANT_1.tenant_id, format="json")
    assert exported["schema_version"] == "integrity.tenant_export/1"
    assert exported["tenant"]["tenant_id"] == TENANT_1.tenant_id
    assert len(exported["roles"]) == 2
    assert len(exported["agents"]) == 1
    assert len(exported["devices"]) == 1
    assert exported["policy"]["region"] == "us-east-1"
    assert len(exported["audit_events"]) == 2


def test_export_tenant_vanta(populated_registry):
    vanta_export = export_tenant(populated_registry, TENANT_1.tenant_id, format="vanta")
    assert vanta_export["format"] == "vanta"
    assert vanta_export["schema_version"] == "vanta.compliance/1"
    assert vanta_export["tenant_id"] == TENANT_1.tenant_id

    controls = vanta_export["controls"]
    assert len(controls["access_control"]["role_assignments"]) == 2
    assert len(controls["asset_management"]["enrolled_devices"]) == 1
    assert controls["data_retention_and_privacy"]["retention_days"] == 60
    assert controls["audit_trail"]["total_events"] == 2


def test_export_tenant_ocsf(populated_registry):
    ocsf_export = export_tenant(populated_registry, TENANT_1.tenant_id, format="ocsf")
    assert ocsf_export["format"] == "ocsf"
    assert ocsf_export["ocsf_version"] == "1.1.0"
    events = ocsf_export["events"]
    assert len(events) == 2

    # Check first event (role assign)
    role_evt = next(e for e in events if e["metadata"]["event_id"] == "evt-001")
    assert role_evt["class_uid"] == 3001
    assert role_evt["class_name"] == "Account Change"
    assert role_evt["activity_name"] == "Assign Role"
    assert role_evt["actor"]["id"] == "user-admin"

    # Check second event (device enroll)
    dev_evt = next(e for e in events if e["metadata"]["event_id"] == "evt-002")
    assert dev_evt["class_uid"] == 3004
    assert dev_evt["class_name"] == "Entity Management"
    assert dev_evt["activity_name"] == "Enroll Entity"


def test_backup_and_restore_tenant(populated_registry, tmp_path):
    backup_file = tmp_path / "backup_alpha.json"
    backup_tenant(populated_registry, TENANT_1.tenant_id, backup_file)
    assert backup_file.exists()

    # Create fresh empty registry and restore
    new_reg = LocalRegistry(tmp_path / "new_registry.json")
    archive_data = json.loads(backup_file.read_text(encoding="utf-8"))
    restored = restore_tenant(new_reg, archive_data)

    assert restored.tenant_id == TENANT_1.tenant_id
    assert new_reg.get_tenant(TENANT_1.tenant_id) == TENANT_1
    assert new_reg.get_agent(AGENT_1.agent_did, tenant_id=TENANT_1.tenant_id) == AGENT_1
    assert new_reg.get_device(DEVICE_1.device_id, tenant_id=TENANT_1.tenant_id) == DEVICE_1
    assert new_reg.check_role(TENANT_1.tenant_id, "user-op", "operator") is True
    assert new_reg.get_policy(TENANT_1.tenant_id) == POLICY_1
    assert len(new_reg.get_audit_log(TENANT_1.tenant_id)) == 2


def test_delete_tenant_lifecycle(populated_registry):
    # Deletion fails without exact confirmation token
    with pytest.raises(TenantExportError, match="exact confirmation"):
        delete_tenant(populated_registry, TENANT_1.tenant_id, confirmation="delete", actor_id="admin-01")

    # Perform confirmed deletion
    delete_tenant(
        populated_registry,
        TENANT_1.tenant_id,
        confirmation=f"DELETE {TENANT_1.tenant_id}",
        actor_id="admin-01",
    )

    # Scoped resources for tenant 1 are purged
    assert populated_registry.get_tenant(TENANT_1.tenant_id) is None
    assert populated_registry.get_agent(AGENT_1.agent_did) is None
    assert populated_registry.get_device(DEVICE_1.device_id) is None
    assert populated_registry.get_roles(TENANT_1.tenant_id) == []
    assert populated_registry.get_policy(TENANT_1.tenant_id) is None
    assert populated_registry.get_audit_log(TENANT_1.tenant_id) == []

    # Tenant 2 is completely unaffected
    assert populated_registry.get_tenant(TENANT_2.tenant_id) == TENANT_2


def test_export_invalid_format_and_missing_tenant(populated_registry):
    with pytest.raises(TenantExportError, match="unsupported export format"):
        export_tenant(populated_registry, TENANT_1.tenant_id, format="unsupported_format")

    with pytest.raises(TenantExportError, match="not found"):
        export_tenant(populated_registry, "nonexistent-tenant", format="json")
