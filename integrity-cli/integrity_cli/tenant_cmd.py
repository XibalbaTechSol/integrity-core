"""Tenant management and compliance evidence export commands (B0 / B7)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from integrity_sdk.core import (
    LocalRegistry,
    RegistryError,
    ROLES,
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

from . import output
from .output import EXIT_NO, EXIT_OK, EXIT_USAGE, JSON_OPTION_HELP, Reporter

DEFAULT_REGISTRY_PATH = Path.home() / ".integrity" / "tenants.json"

tenant_app = typer.Typer(help="Tenant lifecycle, RBAC, devices, policies, and compliance exports (B0)")
device_app = typer.Typer(help="Manage tenant-scoped device lifecycle and revocation")
role_app = typer.Typer(help="Manage tenant role-based access control (RBAC)")
policy_app = typer.Typer(help="Manage tenant retention and regional policies")

tenant_app.add_typer(device_app, name="device")
tenant_app.add_typer(role_app, name="role")
tenant_app.add_typer(policy_app, name="policy")


def _get_registry(custom_path: Optional[Path]) -> LocalRegistry:
    return LocalRegistry(custom_path or DEFAULT_REGISTRY_PATH)


@tenant_app.command("register")
def tenant_register(
    tenant_id: str = typer.Argument(..., help="Unique identifier for the tenant enclave"),
    organization_id: str = typer.Option(..., "--org", "-o", help="Parent organization identifier"),
    display_name: str = typer.Option(..., "--name", "-n", help="Human-readable display name"),
    registry_path: Optional[Path] = typer.Option(None, "--registry", help="Custom registry path"),
    json_mode: bool = typer.Option(False, "--json", help=JSON_OPTION_HELP),
) -> None:
    """Register a new tenant enclave."""
    rep = Reporter("tenant", "register", json_mode=json_mode)
    reg = _get_registry(registry_path)
    try:
        tenant = TenantIdentity(
            organization_id=organization_id,
            tenant_id=tenant_id,
            display_name=display_name,
        )
        reg.register_tenant(tenant)
        rep.result({"ok": True, "tenant": tenant.__dict__})
        rep.info(f"[bold green]Registered tenant:[/bold green] {tenant.tenant_id} ({tenant.display_name}) [org: {tenant.organization_id}]")
    except RegistryError as exc:
        rep.fail(EXIT_NO, str(exc), code="REGISTRATION_FAILED")


@tenant_app.command("show")
def tenant_show(
    tenant_id: str = typer.Argument(..., help="Tenant identifier to inspect"),
    registry_path: Optional[Path] = typer.Option(None, "--registry", help="Custom registry path"),
    json_mode: bool = typer.Option(False, "--json", help=JSON_OPTION_HELP),
) -> None:
    """Show details of a registered tenant enclave."""
    rep = Reporter("tenant", "show", json_mode=json_mode)
    reg = _get_registry(registry_path)
    tenant = reg.get_tenant(tenant_id)
    if not tenant:
        rep.fail(EXIT_NO, f"tenant {tenant_id!r} not found", code="NOT_FOUND")
    roles = reg.get_roles(tenant_id)
    policy = reg.get_policy(tenant_id)

    data = {
        "ok": True,
        "tenant": tenant.__dict__,
        "roles_count": len(roles),
        "policy": policy.__dict__ if policy else None,
    }
    rep.result(data)
    rep.info(f"[bold cyan]Tenant ID:[/bold cyan] {tenant.tenant_id}")
    rep.info(f"[bold]Organization:[/bold] {tenant.organization_id}")
    rep.info(f"[bold]Display Name:[/bold] {tenant.display_name}")
    rep.info(f"[bold]Status:[/bold] {tenant.status}")
    if policy:
        rep.info(f"[bold]Retention Policy:[/bold] {policy.retention_days} days (region: {policy.region})")


@tenant_app.command("export")
def tenant_export(
    tenant_id: str = typer.Argument(..., help="Tenant identifier to export"),
    format: str = typer.Option("json", "--format", "-f", help="Export format: json, vanta, ocsf"),
    out: Optional[Path] = typer.Option(None, "--out", help="Output file path"),
    registry_path: Optional[Path] = typer.Option(None, "--registry", help="Custom registry path"),
    json_mode: bool = typer.Option(False, "--json", help=JSON_OPTION_HELP),
) -> None:
    """Export compliance evidence or backup for a tenant enclave."""
    rep = Reporter("tenant", "export", json_mode=json_mode)
    reg = _get_registry(registry_path)
    try:
        exported = export_tenant(reg, tenant_id, format=format)
        if out:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(exported, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            rep.info(f"[bold green]Exported {format} evidence to:[/bold green] {out}")
        else:
            if not json_mode:
                rep.info(json.dumps(exported, indent=2, sort_keys=True))
        rep.result({"ok": True, "format": format, "data": exported})
    except (RegistryError, TenantExportError) as exc:
        rep.fail(EXIT_NO, str(exc), code="EXPORT_FAILED")


@tenant_app.command("backup")
def tenant_backup(
    tenant_id: str = typer.Argument(..., help="Tenant identifier to backup"),
    out: Path = typer.Option(..., "--out", help="Output JSON backup archive path"),
    registry_path: Optional[Path] = typer.Option(None, "--registry", help="Custom registry path"),
    json_mode: bool = typer.Option(False, "--json", help=JSON_OPTION_HELP),
) -> None:
    """Create an atomic JSON backup archive of a tenant enclave."""
    rep = Reporter("tenant", "backup", json_mode=json_mode)
    reg = _get_registry(registry_path)
    try:
        saved = backup_tenant(reg, tenant_id, out)
        rep.result({"ok": True, "path": str(saved)})
        rep.info(f"[bold green]Backup archive saved to:[/bold green] {saved}")
    except (RegistryError, TenantExportError) as exc:
        rep.fail(EXIT_NO, str(exc), code="BACKUP_FAILED")


@tenant_app.command("restore")
def tenant_restore(
    archive_file: Path = typer.Argument(..., help="Path to JSON backup archive file"),
    registry_path: Optional[Path] = typer.Option(None, "--registry", help="Custom registry path"),
    json_mode: bool = typer.Option(False, "--json", help=JSON_OPTION_HELP),
) -> None:
    """Restore a tenant enclave from a backup archive."""
    rep = Reporter("tenant", "restore", json_mode=json_mode)
    reg = _get_registry(registry_path)
    try:
        data = json.loads(archive_file.read_text(encoding="utf-8"))
        restored = restore_tenant(reg, data)
        rep.result({"ok": True, "tenant": restored.__dict__})
        rep.info(f"[bold green]Restored tenant:[/bold green] {restored.tenant_id} ({restored.display_name})")
    except Exception as exc:
        rep.fail(EXIT_NO, f"restore failed: {exc}", code="RESTORE_FAILED")


@tenant_app.command("delete")
def tenant_delete(
    tenant_id: str = typer.Argument(..., help="Tenant identifier to permanently delete"),
    confirmation: str = typer.Option(..., "--confirmation", help="Confirmation string: DELETE <tenant_id>"),
    actor_id: str = typer.Option("operator", "--actor", help="Operator or admin initiating deletion"),
    registry_path: Optional[Path] = typer.Option(None, "--registry", help="Custom registry path"),
    json_mode: bool = typer.Option(False, "--json", help=JSON_OPTION_HELP),
) -> None:
    """Permanently delete a tenant enclave and all associated scoped assets."""
    rep = Reporter("tenant", "delete", json_mode=json_mode)
    reg = _get_registry(registry_path)
    try:
        delete_tenant(reg, tenant_id, confirmation=confirmation, actor_id=actor_id)
        rep.result({"ok": True, "deleted": tenant_id})
        rep.info(f"[bold yellow]Permanently deleted tenant enclave:[/bold yellow] {tenant_id}")
    except (RegistryError, TenantExportError) as exc:
        rep.fail(EXIT_NO, str(exc), code="DELETION_FAILED")


# --- RBAC Role Commands ---

@role_app.command("assign")
def role_assign(
    tenant_id: str = typer.Argument(..., help="Tenant identifier"),
    actor_id: str = typer.Option(..., "--actor", help="User identifier or agent DID"),
    role: str = typer.Option(..., "--role", help=f"Role: {', '.join(sorted(ROLES))}"),
    registry_path: Optional[Path] = typer.Option(None, "--registry", help="Custom registry path"),
    json_mode: bool = typer.Option(False, "--json", help=JSON_OPTION_HELP),
) -> None:
    """Assign an RBAC role to an actor in a tenant enclave."""
    rep = Reporter("tenant", "role-assign", json_mode=json_mode)
    reg = _get_registry(registry_path)
    try:
        assignment = TenantRoleAssignment(tenant_id=tenant_id, actor_id=actor_id, role=role)
        reg.assign_role(assignment)
        reg.record_audit(
            TenantAuditEvent(
                event_id=f"audit-{tenant_id}-role-assign",
                tenant_id=tenant_id,
                actor_id=actor_id,
                action="role.assign",
                target=actor_id,
                timestamp=assignment.assigned_at or "",
                metadata={"role": role},
            )
        )
        rep.result({"ok": True, "assignment": assignment.__dict__})
        rep.info(f"[bold green]Assigned role:[/bold green] {role} to {actor_id} in {tenant_id}")
    except RegistryError as exc:
        rep.fail(EXIT_NO, str(exc), code="ROLE_ASSIGN_FAILED")


@role_app.command("list")
def role_list(
    tenant_id: str = typer.Argument(..., help="Tenant identifier"),
    actor_id: Optional[str] = typer.Option(None, "--actor", help="Filter by actor identifier"),
    registry_path: Optional[Path] = typer.Option(None, "--registry", help="Custom registry path"),
    json_mode: bool = typer.Option(False, "--json", help=JSON_OPTION_HELP),
) -> None:
    """List role assignments in a tenant enclave."""
    rep = Reporter("tenant", "role-list", json_mode=json_mode)
    reg = _get_registry(registry_path)
    roles = reg.get_roles(tenant_id, actor_id=actor_id)
    rep.result({"ok": True, "roles": [r.__dict__ for r in roles]})
    if not json_mode:
        table = Table(title=f"Role Assignments for {tenant_id}")
        table.add_column("Actor ID", style="cyan")
        table.add_column("Role", style="bold green")
        table.add_column("Assigned At", style="dim")
        table.add_column("Status")
        for r in roles:
            table.add_row(r.actor_id, r.role, r.assigned_at or "-", r.status)
        rep.console.print(table)


@role_app.command("revoke")
def role_revoke(
    tenant_id: str = typer.Argument(..., help="Tenant identifier"),
    actor_id: str = typer.Option(..., "--actor", help="Actor identifier"),
    role: str = typer.Option(..., "--role", help="Role to revoke"),
    registry_path: Optional[Path] = typer.Option(None, "--registry", help="Custom registry path"),
    json_mode: bool = typer.Option(False, "--json", help=JSON_OPTION_HELP),
) -> None:
    """Revoke a role assignment from an actor."""
    rep = Reporter("tenant", "role-revoke", json_mode=json_mode)
    reg = _get_registry(registry_path)
    reg.revoke_role(tenant_id, actor_id, role)
    rep.result({"ok": True, "revoked": {"tenant_id": tenant_id, "actor_id": actor_id, "role": role}})
    rep.info(f"[bold yellow]Revoked role:[/bold yellow] {role} from {actor_id} in {tenant_id}")


# --- Device Commands ---

@device_app.command("revoke")
def device_revoke(
    tenant_id: str = typer.Argument(..., help="Tenant identifier"),
    device_id: str = typer.Option(..., "--device", help="Device identifier to revoke"),
    reason: str = typer.Option("operator_revoked", "--reason", help="Revocation reason code"),
    registry_path: Optional[Path] = typer.Option(None, "--registry", help="Custom registry path"),
    json_mode: bool = typer.Option(False, "--json", help=JSON_OPTION_HELP),
) -> None:
    """Revoke an enrolled device, preventing any further authorization."""
    rep = Reporter("tenant", "device-revoke", json_mode=json_mode)
    reg = _get_registry(registry_path)
    try:
        revoked = reg.revoke_device(tenant_id, device_id, reason=reason)
        reg.record_audit(
            TenantAuditEvent(
                event_id=f"audit-{tenant_id}-device-revoke",
                tenant_id=tenant_id,
                actor_id="operator",
                action="device.revoke",
                target=device_id,
                timestamp=revoked.revoked_at or "",
                metadata={"reason": reason},
            )
        )
        rep.result({"ok": True, "device": revoked.__dict__})
        rep.info(f"[bold yellow]Revoked device:[/bold yellow] {device_id} in {tenant_id} (reason: {reason})")
    except RegistryError as exc:
        rep.fail(EXIT_NO, str(exc), code="DEVICE_REVOKE_FAILED")


# --- Policy Commands ---

@policy_app.command("set")
def policy_set(
    tenant_id: str = typer.Argument(..., help="Tenant identifier"),
    retention_days: int = typer.Option(90, "--retention-days", help="Data retention period in days"),
    region: str = typer.Option("local", "--region", help="Regional boundary (e.g. us-east-1, local)"),
    fail_closed: bool = typer.Option(True, "--fail-closed/--fail-open", help="Fail-closed enforcement"),
    registry_path: Optional[Path] = typer.Option(None, "--registry", help="Custom registry path"),
    json_mode: bool = typer.Option(False, "--json", help=JSON_OPTION_HELP),
) -> None:
    """Configure tenant retention and regional compliance policies."""
    rep = Reporter("tenant", "policy-set", json_mode=json_mode)
    reg = _get_registry(registry_path)
    try:
        policy = TenantPolicy(
            tenant_id=tenant_id,
            retention_days=retention_days,
            region=region,
            fail_closed=fail_closed,
        )
        reg.set_policy(policy)
        rep.result({"ok": True, "policy": policy.__dict__})
        rep.info(f"[bold green]Configured tenant policy for {tenant_id}:[/bold green] {retention_days} days retention (region: {region})")
    except RegistryError as exc:
        rep.fail(EXIT_NO, str(exc), code="POLICY_SET_FAILED")


@policy_app.command("show")
def policy_show(
    tenant_id: str = typer.Argument(..., help="Tenant identifier"),
    registry_path: Optional[Path] = typer.Option(None, "--registry", help="Custom registry path"),
    json_mode: bool = typer.Option(False, "--json", help=JSON_OPTION_HELP),
) -> None:
    """Show tenant retention and regional policy configuration."""
    rep = Reporter("tenant", "policy-show", json_mode=json_mode)
    reg = _get_registry(registry_path)
    policy = reg.get_policy(tenant_id)
    if not policy:
        rep.fail(EXIT_NO, f"no policy configured for tenant {tenant_id!r}", code="NOT_FOUND")
    rep.result({"ok": True, "policy": policy.__dict__})
    rep.info(f"[bold cyan]Tenant Policy for {tenant_id}:[/bold cyan]")
    rep.info(f"  Retention Days: {policy.retention_days}")
    rep.info(f"  Region:         {policy.region}")
    rep.info(f"  Fail Closed:    {policy.fail_closed}")
    rep.info(f"  Export Formats: {', '.join(policy.allowed_export_formats)}")
