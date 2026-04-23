"""
DAZZLE Database Migration CLI Commands.

Wraps Alembic's programmatic API for managing PostgreSQL schema migrations:
- revision: Generate a new migration from EntitySpec diff
- upgrade:  Apply pending migrations
- downgrade: Rollback migrations
- current:  Show current revision
- history:  Show migration history
- stamp:    Mark a revision as applied without running it
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


@db_app.command(name="stamp")
def stamp_command(
    revision: str = typer.Argument(
        ...,
        help="Revision to stamp (e.g. 'head' or a specific revision hash)",
    ),
) -> None:
    """Mark a revision as applied without running its migration.

    Use when the database already has schema changes applied manually
    and you need to update the Alembic version table to match.
    """
    from alembic import command

    cfg = _get_alembic_cfg()

    try:
        command.stamp(cfg, revision)
        console.print(f"[green]Stamped at: {revision}[/green]")
    except Exception as e:
        console.print(f"[red]Stamp failed: {e}[/red]")
        raise typer.Exit(1)


@db_app.command(name="baseline")
def baseline_command(
    database_url: str = typer.Option("", "--database-url", help="Database URL override"),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Immediately upgrade after generating the baseline revision",
    ),
) -> None:
    """Generate a baseline migration that creates all DSL-declared tables.

    Use this for first-time deployment to a fresh database. The command
    diffs the DSL entities against the target database and generates a
    migration with all CREATE TABLE statements.

    Workflow for fresh deployment:
        dazzle db baseline --apply          # Generate + apply in one step
        # or:
        dazzle db baseline                  # Generate only
        dazzle db upgrade                   # Apply separately

    Do NOT use 'stamp' + empty baseline for fresh databases — that marks
    the schema as current without creating tables.
    """
    from alembic import command

    cfg = _get_alembic_cfg()
    url = _resolve_url(database_url)
    if url:
        cfg.set_main_option("sqlalchemy.url", url)

    # Validate that DSL metadata is loadable and non-empty
    try:
        from dazzle_back.alembic.env import _load_target_metadata

        metadata = _load_target_metadata()
        table_count = len(metadata.tables)
        if table_count == 0:
            console.print(
                "[red]No tables found in DSL metadata.[/red]\n"
                "  Ensure you're running from a project directory with dazzle.toml\n"
                "  and DSL files that declare entities."
            )
            raise typer.Exit(1)
        console.print(f"[dim]DSL declares {table_count} tables[/dim]")
    except ImportError:
        console.print("[yellow]Could not validate DSL metadata — proceeding anyway[/yellow]")

    project_versions = str(_get_project_versions_dir())

    try:
        rev = command.revision(
            cfg,
            message="baseline: create all tables",
            autogenerate=True,
            version_path=project_versions,
        )
        if rev is None:
            console.print(
                "[yellow]No schema changes detected.[/yellow]\n"
                "  If the target database already has tables, use 'dazzle db stamp head'\n"
                "  instead to mark the existing schema as current."
            )
            return

        # command.revision() can return Script | list[Script | None]; take the first element if list
        if isinstance(rev, list):
            rev = rev[0]
        if rev is None:
            console.print("[yellow]No revision was created.[/yellow]")
            return

        console.print(f"[green]Baseline revision created: {rev.revision}[/green]")
        console.print(f"[dim]  → {project_versions}/[/dim]")

        if apply:
            command.upgrade(cfg, "head")
            console.print("[green]Baseline applied — all tables created.[/green]")
        else:
            console.print("[dim]Run 'dazzle db upgrade' to apply.[/dim]")

    except Exception as e:
        console.print(f"[red]Baseline failed: {e}[/red]")
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
    """Resolve database URL from flag, env, or manifest.

    Loads ``<cwd>/.env`` before resolution so per-project DATABASE_URL
    values take effect without the user having to export them in their
    shell (#814). Shell exports still win because ``load_project_dotenv``
    only sets variables that aren't already set.
    """
    from dazzle.cli.dotenv import load_project_dotenv
    from dazzle.cli.env import get_active_env
    from dazzle.db.connection import resolve_db_url

    project_root = Path.cwd().resolve()
    load_project_dotenv(project_root)

    return resolve_db_url(
        explicit_url=database_url,
        project_root=project_root,
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
    fix_money: bool = typer.Option(
        False,
        "--fix-money",
        help="Auto-apply legacy money-column migration (#840). Destructive — back up the DB first.",
    ),
) -> None:
    """Check FK integrity + legacy money-column shape across entities (#840)."""
    import json as json_mod

    project_root = Path.cwd().resolve()
    appspec = load_project_appspec(project_root)
    entities = appspec.domain.entities
    url = _resolve_url(database_url)
    schema = _resolve_tenant_schema(tenant) if tenant else ""

    from dazzle.db.money_migration import repair_money_drifts
    from dazzle.db.verify import db_verify_impl

    async def _run(conn: Any) -> Any:
        fk_result = await db_verify_impl(entities=entities, conn=conn)
        money_result = await repair_money_drifts(conn, list(entities), apply=fix_money)
        return {"fk": fk_result, "money": money_result}

    result = asyncio.run(_run_with_connection(project_root, url, _run, schema=schema))

    if as_json:
        console.print(json_mod.dumps(result, indent=2))
        return

    console.print("\n[bold]FK Integrity:[/bold]")
    fk_result = result["fk"]
    for check in fk_result["checks"]:
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

    if fk_result["total_issues"] == 0:
        console.print("\n[green]All FK references valid.[/green]")
    else:
        console.print(f"\n[red]{fk_result['total_issues']} FK issues found.[/red]")

    money_result = result["money"]
    if money_result["drift_count"] or money_result["partial_count"]:
        console.print("\n[bold]Legacy money-column drift (#840):[/bold]")
        for drift in money_result["drifts"]:
            label = "[red]drift[/red]" if drift["status"] == "drift" else "[yellow]partial[/yellow]"
            console.print(
                f"  {label} {drift['entity']}.{drift['field']} "
                f"(legacy {drift['legacy_type']}, ccy {drift['currency']})"
            )
            if drift["status"] == "drift" and not fix_money:
                for line in drift["repair_sql"].splitlines():
                    console.print(f"    [dim]{line}[/dim]")
        if fix_money:
            console.print(f"\n[green]Applied {money_result['applied_count']} statement(s).[/green]")
            if money_result["errors"]:
                console.print(f"[red]{len(money_result['errors'])} error(s) during repair:[/red]")
                for err in money_result["errors"]:
                    console.print(f"  {err['entity']}.{err['field']}: {err['error']}")
        else:
            console.print(
                "\n[yellow]Re-run with --fix-money to auto-apply "
                "(back up the DB first — destructive).[/yellow]"
            )
    else:
        console.print("\n[green]No legacy money-column drift.[/green]")


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


@db_app.command(name="snapshot")
def db_snapshot_command(
    name: str = typer.Argument("baseline", help="Snapshot label (default: baseline)"),
    database_url: str = typer.Option("", "--database-url", help="Database URL override"),
    project: Path | None = typer.Option(None, "--project", help="Project root (default: cwd)"),
) -> None:
    """Capture a pg_dump of the project database to a .sql.gz file.

    Writes `<project>/.dazzle/baselines/<name>.sql.gz`. For named snapshots
    other than 'baseline', the file is used verbatim. For 'baseline', the
    filename is hash-tagged with the Alembic revision and fixture SHA.
    """
    import os

    from dazzle.e2e.baseline import BaselineManager
    from dazzle.e2e.snapshot import Snapshotter

    if project is None:
        project = Path.cwd()

    url = database_url or os.environ.get("DATABASE_URL", "")
    if not url:
        typer.echo("DATABASE_URL not set. Export it or pass --database-url.", err=True)
        raise typer.Exit(code=2)

    if name == "baseline":
        mgr = BaselineManager(project, url)
        path = mgr.ensure(fresh=True)
        typer.echo(f"[db snapshot] wrote baseline → {path}")
    else:
        snap = Snapshotter()
        dest = project / ".dazzle" / "baselines" / f"{name}.sql.gz"
        snap.capture(url, dest)
        typer.echo(f"[db snapshot] wrote {name} → {dest}")


@db_app.command(name="restore")
def db_restore_command(
    name: str = typer.Argument("baseline", help="Snapshot label to restore"),
    database_url: str = typer.Option("", "--database-url", help="Database URL override"),
    project: Path | None = typer.Option(None, "--project", help="Project root (default: cwd)"),
) -> None:
    """Restore a snapshot into the project database via pg_restore --clean."""
    import os

    from dazzle.e2e.baseline import BaselineManager
    from dazzle.e2e.snapshot import Snapshotter

    if project is None:
        project = Path.cwd()

    url = database_url or os.environ.get("DATABASE_URL", "")
    if not url:
        typer.echo("DATABASE_URL not set. Export it or pass --database-url.", err=True)
        raise typer.Exit(code=2)

    if name == "baseline":
        mgr = BaselineManager(project, url)
        path = mgr.restore()
        typer.echo(f"[db restore] restored baseline from {path}")
    else:
        snap = Snapshotter()
        src = project / ".dazzle" / "baselines" / f"{name}.sql.gz"
        if not src.exists():
            typer.echo(f"Snapshot not found: {src}", err=True)
            raise typer.Exit(code=2)
        snap.restore(src, url)
        typer.echo(f"[db restore] restored {name} from {src}")


@db_app.command(name="snapshot-gc")
def db_snapshot_gc_command(
    keep: int = typer.Option(3, "--keep", help="Number of newest snapshots to retain"),
    project: Path | None = typer.Option(None, "--project", help="Project root (default: cwd)"),
) -> None:
    """Delete old baseline snapshot files, keeping the newest `keep`."""
    import os

    from dazzle.e2e.baseline import BaselineManager

    if project is None:
        project = Path.cwd()

    # BaselineManager requires a db_url at construction time, but gc() is a
    # file-only operation that never connects. Use a dummy if DATABASE_URL
    # is absent so the command still works without infrastructure.
    url = os.environ.get("DATABASE_URL", "postgresql://localhost/unused")
    mgr = BaselineManager(project, url)
    deleted = mgr.gc(keep=keep)
    if not deleted:
        typer.echo(f"[db snapshot-gc] nothing to delete (kept newest {keep})")
        return
    for p in deleted:
        typer.echo(f"[db snapshot-gc] deleted {p.name}")


@db_app.command(name="explain-aggregate")
def explain_aggregate_command(
    entity: str = typer.Argument(..., help="Source entity name (e.g. Alert)"),
    group_by: str = typer.Option(
        "",
        "--group-by",
        "-g",
        help="Dimension field(s) — comma-separated for multi-dim. "
        "FK fields auto-LEFT JOIN the target. e.g. 'system,severity'.",
    ),
    measures: str = typer.Option(
        "count=count",
        "--measures",
        "-m",
        help="Comma-separated metric=expr pairs. "
        "Supported exprs: count, sum:<col>, avg:<col>, min:<col>, max:<col>. "
        "Example: 'n=count,avg_score=avg:score'.",
    ),
    limit: int = typer.Option(200, "--limit", "-l", help="Bucket limit (default 200)"),
) -> None:
    """Print the SQL that ``Repository.aggregate`` would execute — no DB hit.

    Debug-velocity tool for authors. When a bar_chart or pivot_table region
    renders wrong values (or no buckets), run this against the same source
    entity + group_by + measures to see the exact query the framework
    emits. Pair with ``psql`` / ``sqlite3 .read`` to run the SQL manually
    and compare row counts to the rendered bars.

    Scope filters are NOT included — explain shows the base query before
    row-level security is applied at request time. Add ``--scope`` later
    if we need to simulate a persona's predicate.
    """
    from dazzle.core.ir.fields import FieldTypeKind
    from dazzle_back.runtime.aggregate import (
        Dimension,
        build_aggregate_sql,
        resolve_fk_display_field,
    )

    project_root = Path.cwd().resolve()
    appspec = load_project_appspec(project_root)

    src_entity = next(
        (e for e in appspec.domain.entities if e.name == entity),
        None,
    )
    if src_entity is None:
        console.print(f"[red]Unknown entity:[/red] {entity}")
        raise typer.Exit(code=1)

    dim_names = [d.strip() for d in group_by.split(",") if d.strip()]
    if not dim_names:
        console.print("[red]--group-by is required[/red] (e.g. '--group-by system,severity')")
        raise typer.Exit(code=1)

    # Resolve each dim — scalar vs FK + target display field.
    dimensions: list[Dimension] = []
    for dim_name in dim_names:
        field = next((f for f in src_entity.fields if f.name == dim_name), None)
        if field is None:
            console.print(f"[red]Unknown field {entity}.{dim_name}[/red]")
            raise typer.Exit(code=1)
        is_fk = field.type.kind == FieldTypeKind.REF
        fk_table = None
        fk_display_field = None
        if is_fk:
            fk_table = field.type.ref_entity
            target = next(
                (e for e in appspec.domain.entities if e.name == fk_table),
                None,
            )
            fk_display_field = resolve_fk_display_field(target)
        dimensions.append(
            Dimension(name=dim_name, fk_table=fk_table, fk_display_field=fk_display_field)
        )

    # Parse measures: 'n=count,avg_score=avg:score' → {'n': 'count', 'avg_score': 'avg:score'}
    measure_dict: dict[str, str] = {}
    for pair in measures.split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        name, _, expr = pair.partition("=")
        measure_dict[name.strip()] = expr.strip()

    sql, params = build_aggregate_sql(
        table_name=src_entity.name,
        placeholder_style="%s",
        dimensions=dimensions,
        measures=measure_dict,
        filters=None,
        limit=limit,
    )

    if not sql:
        console.print(
            "[yellow]No SQL generated[/yellow] — no supported measures "
            "(recognised: count, sum:<col>, avg:<col>, min:<col>, max:<col>)."
        )
        return

    console.print("\n[bold]Aggregate SQL[/bold] ([dim]no scope filter — base query[/dim])")
    for part in sql.split(" FROM "):
        console.print(part)
    console.print("")
    console.print(f"[bold]Params:[/bold] {params}")
