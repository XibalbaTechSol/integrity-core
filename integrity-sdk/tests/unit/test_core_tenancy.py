from __future__ import annotations

import pytest

from integrity_sdk.core import (
    AgentRegistration,
    DeviceRegistration,
    LocalRegistry,
    RegistryError,
    ROLES,
    TenantAuditEvent,
    TenantIdentity,
    TenantPolicy,
    TenantRoleAssignment,
)


TENANT = TenantIdentity("org-acme", "tenant-lab", "Acme Lab")
AGENT = AgentRegistration(TENANT.tenant_id, "did:integrity:agent-1", "Lab agent")
DEVICE = DeviceRegistration(TENANT.tenant_id, "device-1", AGENT.agent_did, "zpublic-key", "sha256:" + "a" * 64)


def test_local_registry_registers_and_scopes_public_identity(tmp_path):
    registry = LocalRegistry(tmp_path / "registry.json")
    registry.register_tenant(TENANT)
    registry.register_agent(AGENT)
    registry.register_device(DEVICE)

    assert registry.get_tenant(TENANT.tenant_id) == TENANT
    assert registry.get_agent(AGENT.agent_did, tenant_id=TENANT.tenant_id) == AGENT
    assert registry.get_device(DEVICE.device_id, tenant_id=TENANT.tenant_id) == DEVICE
    assert registry.authorize_device(
        tenant_id=TENANT.tenant_id, agent_did=AGENT.agent_did, device_id=DEVICE.device_id
    ) == DEVICE


def test_registration_is_idempotent_but_conflicts_are_refused(tmp_path):
    registry = LocalRegistry(tmp_path / "registry.json")
    registry.register_tenant(TENANT)
    registry.register_tenant(TENANT)
    with pytest.raises(RegistryError, match="different metadata"):
        registry.register_tenant(TenantIdentity(TENANT.organization_id, TENANT.tenant_id, "Other"))


def test_agent_and_device_require_same_registered_tenant(tmp_path):
    registry = LocalRegistry(tmp_path / "registry.json")
    registry.register_tenant(TENANT)
    with pytest.raises(RegistryError, match="not registered"):
        registry.register_agent(AgentRegistration("tenant-other", AGENT.agent_did, AGENT.display_name))
    registry.register_agent(AGENT)
    registry.register_tenant(TenantIdentity("org-other", "tenant-other", "Other"))
    with pytest.raises(RegistryError, match="same tenant"):
        registry.register_device(DeviceRegistration("tenant-other", DEVICE.device_id, AGENT.agent_did, DEVICE.public_key, DEVICE.pack_hash))


def test_cross_tenant_lookup_and_inactive_device_fail_closed(tmp_path):
    registry = LocalRegistry(tmp_path / "registry.json")
    registry.register_tenant(TENANT)
    registry.register_agent(AGENT)
    registry.register_device(DeviceRegistration(**{**DEVICE.__dict__, "status": "revoked"}))
    assert registry.get_device(DEVICE.device_id, tenant_id="tenant-other") is None
    with pytest.raises(RegistryError, match="not active"):
        registry.authorize_device(tenant_id=TENANT.tenant_id, agent_did=AGENT.agent_did, device_id=DEVICE.device_id)


def test_device_revocation_lifecycle(tmp_path):
    registry = LocalRegistry(tmp_path / "registry.json")
    registry.register_tenant(TENANT)
    registry.register_agent(AGENT)
    registry.register_device(DEVICE)

    # Revoke device
    revoked = registry.revoke_device(TENANT.tenant_id, DEVICE.device_id, reason="compromised_key")
    assert revoked.status == "revoked"
    assert revoked.revocation_reason == "compromised_key"
    assert revoked.revoked_at is not None

    # Fetch and check status
    fetched = registry.get_device(DEVICE.device_id, tenant_id=TENANT.tenant_id)
    assert fetched.status == "revoked"
    assert fetched.revocation_reason == "compromised_key"

    # Authorization must fail closed
    with pytest.raises(RegistryError, match="not active"):
        registry.authorize_device(tenant_id=TENANT.tenant_id, agent_did=AGENT.agent_did, device_id=DEVICE.device_id)


def test_rbac_role_assignments_and_checks(tmp_path):
    registry = LocalRegistry(tmp_path / "registry.json")
    registry.register_tenant(TENANT)

    # Assign operator and auditor roles
    op_role = TenantRoleAssignment(TENANT.tenant_id, "user-alice", "operator")
    registry.assign_role(op_role)

    aud_role = TenantRoleAssignment(TENANT.tenant_id, "user-bob", "auditor")
    registry.assign_role(aud_role)

    assert registry.check_role(TENANT.tenant_id, "user-alice", "operator") is True
    assert registry.check_role(TENANT.tenant_id, "user-alice", "admin") is False
    assert registry.check_role(TENANT.tenant_id, "user-bob", "auditor") is True

    # Admin role subsumes operational checks
    admin_role = TenantRoleAssignment(TENANT.tenant_id, "user-super", "admin")
    registry.assign_role(admin_role)
    assert registry.check_role(TENANT.tenant_id, "user-super", "operator") is True
    assert registry.check_role(TENANT.tenant_id, "user-super", "auditor") is True

    # Revoke role
    registry.revoke_role(TENANT.tenant_id, "user-alice", "operator")
    assert registry.check_role(TENANT.tenant_id, "user-alice", "operator") is False


def test_tenant_policy_configuration(tmp_path):
    registry = LocalRegistry(tmp_path / "registry.json")
    registry.register_tenant(TENANT)

    policy = TenantPolicy(
        tenant_id=TENANT.tenant_id,
        retention_days=30,
        region="us-central1",
        fail_closed=True,
        allowed_export_formats=("json", "vanta"),
    )
    registry.set_policy(policy)

    retrieved = registry.get_policy(TENANT.tenant_id)
    assert retrieved == policy
    assert retrieved.retention_days == 30
    assert retrieved.region == "us-central1"
    assert retrieved.allowed_export_formats == ("json", "vanta")


def test_tenant_audit_logging(tmp_path):
    registry = LocalRegistry(tmp_path / "registry.json")
    registry.register_tenant(TENANT)

    event1 = TenantAuditEvent(
        event_id="evt-001",
        tenant_id=TENANT.tenant_id,
        actor_id="admin-01",
        action="device.enroll",
        target=DEVICE.device_id,
        timestamp="2026-11-16T07:00:00Z",
        metadata={"public_key": DEVICE.public_key},
    )
    registry.record_audit(event1)

    event2 = TenantAuditEvent(
        event_id="evt-002",
        tenant_id=TENANT.tenant_id,
        actor_id="admin-01",
        action="device.revoke",
        target=DEVICE.device_id,
        timestamp="2026-11-16T07:15:00Z",
        metadata={"reason": "key_rotation"},
    )
    registry.record_audit(event2)

    log = registry.get_audit_log(TENANT.tenant_id)
    assert len(log) == 2
    assert log[0].event_id == "evt-002"  # Reverse chronological order
    assert log[1].event_id == "evt-001"

