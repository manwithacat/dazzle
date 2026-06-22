"""Tenant management CLI commands."""

from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from dazzle.core.manifest import load_manifest, resolve_database_url

tenant_app = typer.Typer(
    help="Multi-tenant schema management",
    no_args_is_help=True,
)

console = Console()


def _check_tenant_enabled() -> None:
    """Raise if tenant isolation is not enabled."""

    toml_path = Path("dazzle.toml").resolve()
    if not toml_path.exists():
        console.print("[red]No dazzle.toml found.[/red]")
        raise typer.Exit(1)

    manifest = load_manifest(toml_path)
    if manifest.tenant.isolation != "schema":
        console.print(
            '[red]Multi-tenancy not enabled. Add [tenant] isolation = "schema" to dazzle.toml[/red]'
        )
        raise typer.Exit(1)


def _get_registry() -> Any:
    from dazzle.cli.env import get_active_env
    from dazzle.tenant.registry import TenantRegistry

    manifest = load_manifest(Path("dazzle.toml").resolve())
    db_url = resolve_database_url(manifest, env_name=get_active_env())
    return TenantRegistry(db_url)


def _get_provisioner() -> Any:
    from dazzle.cli.env import get_active_env
    from dazzle.cli.utils import load_project_appspec
    from dazzle.tenant.provisioner import TenantProvisioner

    project_root = Path.cwd().resolve()
    manifest = load_manifest(project_root / "dazzle.toml")
    db_url = resolve_database_url(manifest, env_name=get_active_env())
    appspec = load_project_appspec(project_root)
    return TenantProvisioner(db_url, appspec)


@tenant_app.command(name="create")
def create_command(
    slug: str = typer.Argument(help="Tenant slug (lowercase, alphanumeric + underscores)"),
    display_name: str = typer.Option(
        ..., "--display-name", "-d", help="Human-readable tenant name"
    ),
) -> None:
    """Create a new tenant with its own database schema."""
    _check_tenant_enabled()
    registry = _get_registry()
    provisioner = _get_provisioner()

    registry.ensure_table()

    try:
        record = registry.create(slug, display_name)
    except Exception as e:
        console.print(f"[red]Failed to create tenant: {e}[/red]")
        raise typer.Exit(1)

    try:
        provisioner.provision(record.schema_name)
    except Exception as e:
        console.print(f"[red]Schema provisioning failed: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]Tenant created:[/green] {record.slug}")
    console.print(f"  Schema: {record.schema_name}")
    console.print(f"  Display: {record.display_name}")


@tenant_app.command(name="list")
def list_command() -> None:
    """List all tenants."""
    _check_tenant_enabled()
    registry = _get_registry()
    registry.ensure_table()

    tenants = registry.list()
    if not tenants:
        console.print("No tenants found.")
        return

    table = Table(title="Tenants")
    table.add_column("Slug")
    table.add_column("Display Name")
    table.add_column("Schema")
    table.add_column("Status")

    for t in tenants:
        table.add_row(t.slug, t.display_name, t.schema_name, t.status)

    console.print(table)


@tenant_app.command(name="status")
def status_command(
    slug: str = typer.Argument(help="Tenant slug"),
) -> None:
    """Show details for a tenant."""
    _check_tenant_enabled()
    registry = _get_registry()

    record = registry.get(slug)
    if not record:
        console.print(f"[red]Tenant '{slug}' not found.[/red]")
        raise typer.Exit(1)

    console.print(f"Slug:         {record.slug}")
    console.print(f"Display Name: {record.display_name}")
    console.print(f"Schema:       {record.schema_name}")
    console.print(f"Status:       {record.status}")
    console.print(f"Test tenant:  {getattr(record, 'is_test', False)}")
    console.print(f"Created:      {record.created_at}")
    console.print(f"Updated:      {record.updated_at}")


@tenant_app.command(name="suspend")
def suspend_command(
    slug: str = typer.Argument(help="Tenant slug to suspend"),
) -> None:
    """Suspend a tenant (returns 503 at middleware)."""
    _check_tenant_enabled()
    registry = _get_registry()

    try:
        record = registry.update_status(slug, "suspended")
        console.print(f"[yellow]Tenant '{record.slug}' suspended.[/yellow]")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


@tenant_app.command(name="activate")
def activate_command(
    slug: str = typer.Argument(help="Tenant slug to activate"),
) -> None:
    """Activate a suspended tenant."""
    _check_tenant_enabled()
    registry = _get_registry()

    try:
        record = registry.update_status(slug, "active")
        console.print(f"[green]Tenant '{record.slug}' activated.[/green]")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


def _excise_context() -> tuple[Any, str]:
    """``(appspec, db_url)`` for excision — shared-schema RLS, NOT gated on the
    schema-isolation ``_check_tenant_enabled`` (excision applies to the
    shared-schema model)."""
    from dazzle.cli.env import get_active_env
    from dazzle.cli.utils import load_project_appspec

    project_root = Path.cwd().resolve()
    manifest = load_manifest(project_root / "dazzle.toml")
    db_url = resolve_database_url(manifest, env_name=get_active_env())
    appspec = load_project_appspec(project_root)
    return appspec, db_url


@tenant_app.command(name="excise")
def excise_command(
    tenant_id: str = typer.Argument(help="The tenant/org id (dazzle.tenant_id) to excise."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Report what would be deleted; delete nothing."
    ),
    force: bool = typer.Option(
        False, "--force", help="Allow exciseing a non-test org / missing org (DANGER)."
    ),
    database_url: str = typer.Option(
        "",
        "--database-url",
        help="Override DB URL. MUST be a BYPASSRLS role (dazzle_bypass) in production.",
    ),
) -> None:
    """Permanently delete a tenant: domain rows, memberships, org, orphaned identities.

    Irreversible. Refuses a non-`is_test` org unless --force. Runs in one
    transaction; connect as `dazzle_bypass` (BYPASSRLS) so the deletes aren't
    fenced (the dev superuser bypasses RLS already).
    """
    import psycopg

    from dazzle.db.excision import ExcisionError, excise_tenant

    appspec, default_url = _excise_context()
    url = database_url or default_url
    try:
        with psycopg.connect(url) as conn:  # non-autocommit → one transaction
            # Safety guard: refuse a non-test org unless --force.
            row = conn.execute(
                "SELECT is_test, slug FROM organizations WHERE id = %s", (tenant_id,)
            ).fetchone()
            if row is not None and not bool(row[0]) and not force:
                console.print(
                    f"[red]Refusing to excise non-test org {tenant_id!r} "
                    f"(slug={row[1]!r}). Re-run with --force if you mean it.[/red]"
                )
                raise typer.Exit(2)
            result = excise_tenant(
                appspec, tenant_id, conn=conn, dry_run=dry_run, allow_missing=force
            )
    except ExcisionError as exc:
        console.print(f"[red]Excision aborted: {exc}[/red]")
        raise typer.Exit(1) from exc

    verb = "Would delete" if dry_run else "Deleted"
    console.print(f"[green]{verb} for tenant {tenant_id}[/green] (root={result.root}):")
    for table, n in sorted(result.deleted.items()):
        console.print(f"  {table}: {n}")
