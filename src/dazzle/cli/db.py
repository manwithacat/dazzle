"""
DAZZLE Database Migration CLI Commands.

Wraps Alembic's programmatic API for managing PostgreSQL schema migrations:
- revision: Generate a new migration from EntitySpec diff
- upgrade:  Apply pending migrations
- downgrade: Rollback migrations
- current:  Show current revision
- history:  Show migration history
"""

import asyncio
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from dazzle.cli.utils import load_project_appspec

db_app = typer.Typer(
    help="Database migration commands (Alembic)",
    no_args_is_help=True,
)

console = Console()


def _get_framework_alembic_dir() -> Path:
    """Locate the framework's alembic directory (env.py, templates, INI)."""
    # Works both in editable installs and pip-installed packages
    try:
        import dazzle_back

        return (Path(dazzle_back.__file__).resolve().parent / "alembic").resolve()
    except (ImportError, AttributeError):
        # Fallback for dev layout
        return (Path(__file__).resolve().parents[2] / "dazzle_back" / "alembic").resolve()


def _get_project_versions_dir() -> Path:
    """Return the project-local migrations directory, creating it if needed."""
    project_root = Path.cwd().resolve()
    versions_dir = project_root / ".dazzle" / "migrations" / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)
    return versions_dir


def _get_alembic_cfg() -> Any:
    """Build an Alembic Config with framework env.py + project-local versions.

    The framework's alembic directory provides env.py, migration template,
    and alembic.ini. The version_locations option chains the framework's
    built-in migrations with the project's local migrations directory.
    New revisions are written to the project directory via --version-path.
    """
    from alembic.config import Config as AlembicConfig

    framework_dir = _get_framework_alembic_dir()
    ini_path = framework_dir / "alembic.ini"

    cfg = AlembicConfig(str(ini_path))
    cfg.set_main_option("script_location", str(framework_dir))

    # Chain framework + project version directories so upgrade/downgrade
    # discovers migrations from both locations
    framework_versions = str(framework_dir / "versions")
    project_versions = str(_get_project_versions_dir())
    cfg.set_main_option("version_locations", f"{framework_versions} {project_versions}")

    # Override sqlalchemy.url from resolved database URL
    url = _resolve_url("")
    if url:
        cfg.set_main_option("sqlalchemy.url", url)

    return cfg


@db_app.command(name="revision")
def revision_command(
    message: str = typer.Option(
        ...,
        "--message",
        "-m",
        help="Short description of the migration",
    ),
    autogenerate: bool = typer.Option(
        True,
        "--autogenerate/--no-autogenerate",
        help="Auto-detect schema changes from DSL entities",
    ),
) -> None:
    """Generate a new migration revision into the project directory."""
    from alembic import command

    cfg = _get_alembic_cfg()
    project_versions = str(_get_project_versions_dir())

    try:
        command.revision(
            cfg,
            message=message,
            autogenerate=autogenerate,
            version_path=project_versions,
        )
        console.print(f"[green]Migration revision created: {message}[/green]")
        console.print(f"[dim]  → {project_versions}/[/dim]")
    except Exception as e:
        console.print(f"[red]Failed to create revision: {e}[/red]")
        raise typer.Exit(1)


@db_app.command(name="upgrade")
def upgrade_command(
    revision: str = typer.Argument(
        "head",
        help="Target revision (default: head)",
    ),
) -> None:
    """Apply pending migrations (upgrade to target revision)."""
    from alembic import command

    cfg = _get_alembic_cfg()

    try:
        command.upgrade(cfg, revision)
        console.print(f"[green]Upgraded to: {revision}[/green]")
    except Exception as e:
        console.print(f"[red]Upgrade failed: {e}[/red]")
        raise typer.Exit(1)


@db_app.command(name="downgrade")
def downgrade_command(
    revision: str = typer.Argument(
        "-1",
        help="Target revision (default: -1 for one step back)",
    ),
) -> None:
    """Rollback migrations (downgrade to target revision)."""
    from alembic import command

    cfg = _get_alembic_cfg()

    try:
        command.downgrade(cfg, revision)
        console.print(f"[green]Downgraded to: {revision}[/green]")
    except Exception as e:
        console.print(f"[red]Downgrade failed: {e}[/red]")
        raise typer.Exit(1)


@db_app.command(name="current")
def current_command() -> None:
    """Show the current migration revision."""
    from alembic import command

    cfg = _get_alembic_cfg()

    try:
        command.current(cfg, verbose=True)
    except Exception as e:
        console.print(f"[red]Failed to get current revision: {e}[/red]")
        raise typer.Exit(1)


@db_app.command(name="history")
def history_command(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed history",
    ),
) -> None:
    """Show migration history."""
    from alembic import command

    cfg = _get_alembic_cfg()

    try:
        command.history(cfg, verbose=verbose)
    except Exception as e:
        console.print(f"[red]Failed to get history: {e}[/red]")
        raise typer.Exit(1)


@db_app.command(name="migrate")
def migrate_command(
    database_url: str = typer.Option("", "--database-url", help="Database URL override"),
    tenant: str = typer.Option("", "--tenant", help="Tenant slug (when isolation=schema)"),
    check: bool = typer.Option(
        False,
        "--check",
        help="Dry-run: show what would change without applying",
    ),
    sql: bool = typer.Option(
        False,
        "--sql",
        help="Print SQL without applying",
    ),
) -> None:
    """Generate and apply pending migrations.

    Diffs the DSL-derived schema against the live database and applies
    safe changes automatically. Use --check for a dry-run preview.

    Examples:
        dazzle db migrate              # Generate + apply
        dazzle db migrate --check      # Preview changes
        dazzle db migrate --tenant X   # Apply to tenant schema
    """
    from alembic import command
    from alembic.util.exc import CommandError

    cfg = _get_alembic_cfg()
    url = _resolve_url(database_url)
    if url:
        cfg.set_main_option("sqlalchemy.url", url)

    schema = _resolve_tenant_schema(tenant) if tenant else ""
    if schema:
        cfg.attributes["tenant_schema"] = schema

    if check:
        console.print("[bold]Migration check (dry-run):[/bold]\n")
        try:
            command.check(cfg)
            console.print("[green]No pending changes.[/green]")
        except CommandError as e:
            console.print(f"[yellow]Pending changes detected:[/yellow] {e}")
        return

    if sql:
        command.upgrade(cfg, "head", sql=True)
        return

    try:
        # Generate revision from current DSL diff.
        # process_revision_directives in env.py suppresses empty revisions,
        # so revision() returns None when there are no changes.
        rev = command.revision(cfg, message="auto", autogenerate=True)
        if rev is None:
            console.print("[green]No schema changes detected.[/green]")
            return

        # Apply the new revision (and any other pending)
        command.upgrade(cfg, "head")
        console.print("[green]Migration applied successfully.[/green]")
    except Exception as e:
        console.print(f"[red]Migration failed: {e}[/red]")
        raise typer.Exit(1)


@db_app.command(name="rollback")
def rollback_command_wrapper(
    revision: str = typer.Argument(
        "-1",
        help="Target revision or steps back (default: -1)",
    ),
    database_url: str = typer.Option("", "--database-url", help="Database URL override"),
) -> None:
    """Revert the last migration (or to a specific revision).

    Examples:
        dazzle db rollback             # Undo last migration
        dazzle db rollback -2          # Undo last 2 migrations
        dazzle db rollback abc123      # Downgrade to specific revision
    """
    from alembic import command

    cfg = _get_alembic_cfg()
    url = _resolve_url(database_url)
    if url:
        cfg.set_main_option("sqlalchemy.url", url)

    try:
        command.downgrade(cfg, revision)
        console.print(f"[green]Rolled back to: {revision}[/green]")
    except Exception as e:
        console.print(f"[red]Rollback failed: {e}[/red]")
        raise typer.Exit(1)


async def _run_with_connection(
    project_root: Path,
    database_url: str,
    coro_factory: Any,
    schema: str = "",
) -> Any:
    """Connect to DB, run async operation, close connection.

    Args:
        schema: Optional tenant schema name. When provided, sets the
                search_path before running the operation.
    """
    from dazzle.db.connection import get_connection

    conn = await get_connection(explicit_url=database_url, project_root=project_root)
    try:
        if schema:
            # schema is pre-validated via slug_to_schema_name (alphanumeric + underscore only)
            await conn.execute(f"SET search_path TO {schema}, public")  # nosemgrep
        return await coro_factory(conn)
    finally:
        await conn.close()


def _resolve_tenant_schema(tenant: str) -> str:
    """Convert tenant slug to a quoted schema name for SET search_path."""
    from dazzle.tenant.config import slug_to_schema_name, validate_slug

    validate_slug(tenant)
    return slug_to_schema_name(tenant)


def _resolve_url(database_url: str) -> str:
    """Resolve database URL from flag, env, or manifest."""
    from dazzle.cli.env import get_active_env
    from dazzle.db.connection import resolve_db_url

    return resolve_db_url(
        explicit_url=database_url,
        project_root=Path.cwd().resolve(),
        env_name=get_active_env(),
    )


@db_app.command(name="status")
def status_command(
    database_url: str = typer.Option("", "--database-url", help="Database URL override"),
    tenant: str = typer.Option("", "--tenant", help="Tenant slug (when isolation=schema)"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show row counts per entity and database size."""
    import json as json_mod

    project_root = Path.cwd().resolve()
    appspec = load_project_appspec(project_root)
    entities = appspec.domain.entities
    url = _resolve_url(database_url)
    schema = _resolve_tenant_schema(tenant) if tenant else ""

    from dazzle.db.status import db_status_impl

    async def _run(conn: Any) -> Any:
        return await db_status_impl(entities=entities, conn=conn)

    result = asyncio.run(_run_with_connection(project_root, url, _run, schema=schema))

    if as_json:
        console.print(json_mod.dumps(result, indent=2))
        return

    console.print("\n[bold]Entity           Rows[/bold]")
    console.print("─" * 30)
    for entry in result["entities"]:
        status = "[red]error[/red]" if entry.get("error") else str(entry["rows"])
        console.print(f"  {entry['name']:<18} {status}")
    console.print("─" * 30)
    console.print(
        f"Total: {result['total_entities']} entities, "
        f"{result['total_rows']:,} rows, {result['database_size']}"
    )


@db_app.command(name="verify")
def verify_command(
    database_url: str = typer.Option("", "--database-url", help="Database URL override"),
    tenant: str = typer.Option("", "--tenant", help="Tenant slug (when isolation=schema)"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Check FK integrity across all entity relationships."""
    import json as json_mod

    project_root = Path.cwd().resolve()
    appspec = load_project_appspec(project_root)
    entities = appspec.domain.entities
    url = _resolve_url(database_url)
    schema = _resolve_tenant_schema(tenant) if tenant else ""

    from dazzle.db.verify import db_verify_impl

    async def _run(conn: Any) -> Any:
        return await db_verify_impl(entities=entities, conn=conn)

    result = asyncio.run(_run_with_connection(project_root, url, _run, schema=schema))

    if as_json:
        console.print(json_mod.dumps(result, indent=2))
        return

    console.print("\n[bold]FK Integrity:[/bold]")
    for check in result["checks"]:
        if check["status"] == "ok":
            console.print(f"  [green]✓[/green] {check['entity']}.{check['field']} → {check['ref']}")
        elif check["status"] == "orphans":
            console.print(
                f"  [red]✗[/red] {check['entity']}.{check['field']} → {check['ref']}: "
                f"{check['orphan_count']} orphans"
            )
        else:
            console.print(
                f"  [yellow]![/yellow] {check['entity']}.{check['field']} → {check['ref']}: "
                f"{check.get('error', 'unknown error')}"
            )

    if result["total_issues"] == 0:
        console.print("\n[green]All FK references valid.[/green]")
    else:
        console.print(f"\n[red]{result['total_issues']} issues found.[/red]")


@db_app.command(name="reset")
def reset_command(
    database_url: str = typer.Option("", "--database-url", help="Database URL override"),
    tenant: str = typer.Option("", "--tenant", help="Tenant slug (when isolation=schema)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be truncated"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Truncate entity tables in dependency order (preserves auth)."""
    import json as json_mod

    project_root = Path.cwd().resolve()
    appspec = load_project_appspec(project_root)
    entities = appspec.domain.entities
    url = _resolve_url(database_url)
    schema = _resolve_tenant_schema(tenant) if tenant else ""

    from dazzle.db.reset import db_reset_impl

    if dry_run:

        async def _run_dry(conn: Any) -> Any:
            return await db_reset_impl(entities=entities, conn=conn, dry_run=True)

        result = asyncio.run(_run_with_connection(project_root, url, _run_dry, schema=schema))

        if as_json:
            console.print(json_mod.dumps(result, indent=2))
            return

        console.print(
            f"\n[bold]Would truncate {result['would_truncate']} tables ({result['total_rows']:,} rows):[/bold]"
        )
        for t in result["tables"]:
            console.print(f"  {t['name']} ({t['rows']} rows)")
        if result["preserved"]:
            console.print(f"\nPreserved: {', '.join(result['preserved'])}")
        return

    if not yes:
        console.print(f"\nThis will truncate {len(entities)} entity tables.")
        confirm = typer.prompt("Type 'reset' to confirm", default="")
        if confirm != "reset":
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    async def _run(conn: Any) -> Any:
        return await db_reset_impl(entities=entities, conn=conn)

    result = asyncio.run(_run_with_connection(project_root, url, _run, schema=schema))

    if as_json:
        console.print(json_mod.dumps(result, indent=2))
        return

    for t in result["tables"]:
        err = f" [red]error: {t['error']}[/red]" if t.get("error") else " ✓"
        console.print(f"  {t['name']} ({t['rows']} rows){err}")
    console.print(
        f"\n[green]Reset complete: {result['truncated']} tables, {result['total_rows']:,} rows removed.[/green]"
    )


@db_app.command(name="cleanup")
def cleanup_command(
    database_url: str = typer.Option("", "--database-url", help="Database URL override"),
    tenant: str = typer.Option("", "--tenant", help="Tenant slug (when isolation=schema)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be deleted"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Find and remove FK orphan records."""
    import json as json_mod

    project_root = Path.cwd().resolve()
    appspec = load_project_appspec(project_root)
    entities = appspec.domain.entities
    url = _resolve_url(database_url)
    schema = _resolve_tenant_schema(tenant) if tenant else ""

    from dazzle.db.cleanup import db_cleanup_impl

    if dry_run:

        async def _run_dry(conn: Any) -> Any:
            return await db_cleanup_impl(entities=entities, conn=conn, dry_run=True)

        result = asyncio.run(_run_with_connection(project_root, url, _run_dry, schema=schema))

        if as_json:
            console.print(json_mod.dumps(result, indent=2))
            return

        if result["would_delete"] == 0:
            console.print("[green]No orphan records found.[/green]")
            return

        console.print(f"\n[bold]Found {result['would_delete']} orphan records:[/bold]")
        for f in result["findings"]:
            console.print(
                f"  {f['orphan_count']} × {f['entity']} ({f['field']} → {f['ref']}: missing)"
            )
        console.print("\nRun without --dry-run to delete.")
        return

    if not yes:
        confirm = typer.prompt("Type 'cleanup' to confirm", default="")
        if confirm != "cleanup":
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    async def _run(conn: Any) -> Any:
        return await db_cleanup_impl(entities=entities, conn=conn)

    result = asyncio.run(_run_with_connection(project_root, url, _run, schema=schema))

    if as_json:
        console.print(json_mod.dumps(result, indent=2))
        return

    if result["total_deleted"] == 0:
        console.print("[green]No orphan records found.[/green]")
        return

    for d in result["deletions"]:
        console.print(f"  {d['deleted']} × {d['entity']} ✓")
    console.print(
        f"\n[green]Cleanup complete: {result['total_deleted']} orphans removed "
        f"in {result['iterations']} iteration(s).[/green]"
    )
