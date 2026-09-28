from __future__ import annotations

import pytest

from integrity_sdk.core import (
    AgentRegistration,
    DeviceRegistration,
    LocalRegistry,
    RegistryError,
    TenantIdentity,
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
