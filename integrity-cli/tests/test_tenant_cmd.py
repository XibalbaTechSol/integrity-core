from __future__ import annotations

import json
from pathlib import Path
from typer.testing import CliRunner

from integrity_cli.main import app
from integrity_sdk.core import AgentRegistration, DeviceRegistration, LocalRegistry

runner = CliRunner()


def test_tenant_cli_full_lifecycle(tmp_path: Path):
    reg_path = tmp_path / "test_reg.json"
    reg_arg = ["--registry", str(reg_path)]

    # 1. Register tenant
    res = runner.invoke(app, [
        "tenant", "register", "tenant-test", "--org", "org-test", "--name", "Test Enclave", *reg_arg
    ])
    assert res.exit_code == 0
    assert "Registered tenant" in res.stdout

    # 2. Show tenant
    res = runner.invoke(app, ["tenant", "show", "tenant-test", *reg_arg])
    assert res.exit_code == 0
    assert "tenant-test" in res.stdout
    assert "Test Enclave" in res.stdout

    # Show JSON output
    res = runner.invoke(app, ["tenant", "show", "tenant-test", *reg_arg, "--json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["ok"] is True
    assert data["tenant"]["tenant_id"] == "tenant-test"

    # 3. Configure Policy
    res = runner.invoke(app, [
        "tenant", "policy", "set", "tenant-test", "--retention-days", "45", "--region", "us-east-1", *reg_arg
    ])
    assert res.exit_code == 0

    res = runner.invoke(app, ["tenant", "policy", "show", "tenant-test", *reg_arg, "--json"])
    assert res.exit_code == 0
    p_data = json.loads(res.stdout)
    assert p_data["policy"]["retention_days"] == 45
    assert p_data["policy"]["region"] == "us-east-1"

    # 4. Assign and check Role
    res = runner.invoke(app, [
        "tenant", "role", "assign", "tenant-test", "--actor", "user-lead", "--role", "admin", *reg_arg
    ])
    assert res.exit_code == 0

    res = runner.invoke(app, ["tenant", "role", "list", "tenant-test", *reg_arg, "--json"])
    assert res.exit_code == 0
    r_data = json.loads(res.stdout)
    assert len(r_data["roles"]) == 1
    assert r_data["roles"][0]["actor_id"] == "user-lead"
    assert r_data["roles"][0]["role"] == "admin"

    # 5. Device Revocation
    # Register an agent and device directly into registry for testing revocation
    reg = LocalRegistry(reg_path)
    reg.register_agent(AgentRegistration("tenant-test", "did:integrity:agent-x", "Agent X"))
    reg.register_device(DeviceRegistration("tenant-test", "dev-101", "did:integrity:agent-x", "zpubkey", "sha256:" + "0" * 64))

    res = runner.invoke(app, [
        "tenant", "device", "revoke", "tenant-test", "--device", "dev-101", "--reason", "security_rotation", *reg_arg
    ])
    assert res.exit_code == 0
    assert "Revoked device" in res.stdout

    # 6. Compliance Evidence Export (Vanta and OCSF)
    vanta_out = tmp_path / "vanta.json"
    res = runner.invoke(app, [
        "tenant", "export", "tenant-test", "--format", "vanta", "--out", str(vanta_out), *reg_arg
    ])
    assert res.exit_code == 0
    vanta_content = json.loads(vanta_out.read_text(encoding="utf-8"))
    assert vanta_content["format"] == "vanta"
    assert vanta_content["tenant_id"] == "tenant-test"

    ocsf_res = runner.invoke(app, [
        "tenant", "export", "tenant-test", "--format", "ocsf", *reg_arg, "--json"
    ])
    assert ocsf_res.exit_code == 0
    ocsf_payload = json.loads(ocsf_res.stdout)
    assert ocsf_payload["data"]["format"] == "ocsf"

    # 7. Backup and Restore
    backup_file = tmp_path / "tenant_backup.json"
    res = runner.invoke(app, [
        "tenant", "backup", "tenant-test", "--out", str(backup_file), *reg_arg
    ])
    assert res.exit_code == 0

    fresh_reg_path = tmp_path / "fresh_reg.json"
    res = runner.invoke(app, [
        "tenant", "restore", str(backup_file), "--registry", str(fresh_reg_path)
    ])
    assert res.exit_code == 0
    assert "Restored tenant" in res.stdout

    fresh_reg = LocalRegistry(fresh_reg_path)
    assert fresh_reg.get_tenant("tenant-test") is not None
    assert fresh_reg.check_role("tenant-test", "user-lead", "admin") is True

    # 8. Delete Tenant
    res = runner.invoke(app, [
        "tenant", "delete", "tenant-test", "--confirmation", "DELETE tenant-test", *reg_arg
    ])
    assert res.exit_code == 0
    assert "Permanently deleted tenant enclave" in res.stdout
    assert reg.get_tenant("tenant-test") is None
