"""
DAZZLE Process Migration CLI Commands.

Commands for managing DSL version migrations:
- status: Show current version and migration status
- drain: Drain running processes before deploying new version
- deploy: Deploy current DSL as new version
- rollback: Rollback a migration
- list: List deployed versions
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.table import Table

if TYPE_CHECKING:
    from dazzle.core.process import VersionManager

migrate_app = typer.Typer(
    help="Process migration commands for safe DSL version deployments",
    no_args_is_help=True,
)

console = Console()


def _get_version_manager() -> VersionManager:
    """Get VersionManager for current project."""
    from dazzle.core.process import VersionManager

    # Get project root from cwd or find dazzle.toml
    project_root = Path.cwd()
    manifest_path = project_root / "dazzle.toml"

    if not manifest_path.exists():
        console.print("[red]Error: No dazzle.toml found in current directory[/red]")
        raise typer.Exit(1)

    db_path = project_root / ".dazzle" / "processes.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    return VersionManager(db_path=db_path)


def _get_dsl_files() -> list[Path]:
    """Discover DSL files in current project."""
    from dazzle.core.fileset import discover_dsl_files
    from dazzle.core.manifest import load_manifest

    project_root = Path.cwd()
    manifest = load_manifest(project_root / "dazzle.toml")
    return discover_dsl_files(project_root, manifest)


@migrate_app.command(name="status")
def status_command() -> None:
    """Show current version and migration status."""
    vm = _get_version_manager()

    async def _status() -> None:
        await vm.initialize()

        current = await vm.get_current_version()
        if current:
            console.print(f"Current version: [green]{current}[/green]")
        else:
            console.print("[yellow]No active version deployed[/yellow]")

        # Show any in-progress migrations
        migrations = await vm.get_active_migrations()
        if migrations:
            console.print()
            table = Table(title="Active Migrations")
            table.add_column("ID", style="cyan")
            table.add_column("From")
            table.add_column("To")
            table.add_column("Remaining", justify="right")
            table.add_column("Status")

            for m in migrations:
                status_info = await vm.check_migration_status(m.id)
                table.add_row(
                    str(m.id),
                    m.from_version or "-",
                    m.to_version,
                    str(status_info.runs_remaining),
                    m.status,
                )
            console.print(table)

        # Show recent versions
        versions = await vm.list_versions(limit=5)
        if versions:
            console.print()
            table = Table(title="Recent Versions")
            table.add_column("Version ID", style="cyan")
            table.add_column("Deployed")
            table.add_column("Status")
            table.add_column("Hash")

            for v in versions:
                status_style = {
                    "active": "green",
                    "draining": "yellow",
                    "archived": "dim",
                }.get(v.status, "")

                table.add_row(
                    v.version_id,
                    v.deployed_at.strftime("%Y-%m-%d %H:%M"),
                    f"[{status_style}]{v.status}[/{status_style}]",
                    v.dsl_hash[:8],
                )
            console.print(table)

    asyncio.run(_status())


@migrate_app.command(name="drain")
def drain_command(
    timeout: int = typer.Option(
        300,
        "--timeout",
        "-t",
        help="Timeout in seconds to wait for drain",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force drain even if processes are stuck (suspends them)",
    ),
) -> None:
    """Drain running processes before deploying new version."""
    vm = _get_version_manager()

    async def _drain() -> None:
        await vm.initialize()

        current = await vm.get_current_version()
        if not current:
            console.print("[yellow]No active version to drain[/yellow]")
            return

        # Start drain - create migration to placeholder
        runs_remaining = await vm.start_migration(current, "pending_deploy")

        if runs_remaining == 0:
            console.print("[green]No running processes, ready for deploy[/green]")
            return

        console.print(f"Draining {runs_remaining} processes...")

        # Get migration ID
        migrations = await vm.get_active_migrations()
        if not migrations:
            console.print("[red]Failed to start migration[/red]")
            raise typer.Exit(1)

        migration_id = migrations[0].id

        # Wait for drain with progress
        start = time.time()
        with console.status("[bold blue]Waiting for processes to complete...") as status:
            while time.time() - start < timeout:
                check = await vm.check_migration_status(migration_id)

                if check.runs_remaining == 0:
                    console.print("[green]Drain complete[/green]")
                    return

                status.update(f"[bold blue]Waiting... {check.runs_remaining} processes remaining")
                await asyncio.sleep(5)

        # Timeout reached
        final_check = await vm.check_migration_status(migration_id)
        if force:
            console.print("[yellow]Timeout reached, forcing completion[/yellow]")
            suspended = await vm.suspend_remaining_processes(current)
            console.print(f"Suspended {suspended} processes")
            await vm.complete_migration(migration_id)
        else:
            console.print(
                f"[red]Timeout reached. {final_check.runs_remaining} processes still running.[/red]"
            )
            console.print("Use --force to suspend remaining processes")
            raise typer.Exit(1)

    asyncio.run(_drain())


@migrate_app.command(name="deploy")
def deploy_command(
    skip_drain: bool = typer.Option(
        False,
        "--skip-drain",
        help="Skip automatic drain before deploy",
    ),
    timeout: int = typer.Option(
        300,
        "--timeout",
        "-t",
        help="Timeout for drain phase",
    ),
) -> None:
    """Deploy current DSL as new version."""
    from dazzle.core.dsl_parser import parse_modules
    from dazzle.core.linker import build_appspec
    from dazzle.core.manifest import load_manifest
    from dazzle.core.process import VersionManager, generate_version_id

    project_root = Path.cwd()
    manifest_path = project_root / "dazzle.toml"

    if not manifest_path.exists():
        console.print("[red]Error: No dazzle.toml found in current directory[/red]")
        raise typer.Exit(1)

    # Load manifest and compute hash
    manifest = load_manifest(manifest_path)
    dsl_files = _get_dsl_files()

    if not dsl_files:
        console.print("[red]Error: No DSL files found[/red]")
        raise typer.Exit(1)

    # Compute version hash
    version_hash = VersionManager.compute_version_hash(dsl_files)
    version_id = generate_version_id(version_hash)

    # Validate DSL
    console.print("Validating DSL...")
    try:
        modules = parse_modules(dsl_files)
        build_appspec(modules, str(project_root))
    except Exception as e:
        console.print(f"[red]DSL validation failed: {e}[/red]")
        raise typer.Exit(1)

    console.print("[green]DSL validation passed[/green]")

    vm = _get_version_manager()

    async def _deploy() -> None:
        await vm.initialize()

        current = await vm.get_current_version()

        # Drain if there's an existing version
        if current and not skip_drain:
            runs_remaining = await vm.start_migration(current, version_id)

            if runs_remaining > 0:
                console.print(f"Draining {runs_remaining} processes...")

                migrations = await vm.get_active_migrations()
                if migrations:
                    migration_id = migrations[0].id
                    start = time.time()

                    while time.time() - start < timeout:
                        check = await vm.check_migration_status(migration_id)
                        if check.runs_remaining == 0:
                            break
                        await asyncio.sleep(5)
                        console.print(f"  Waiting... {check.runs_remaining} processes remaining")

                    final_check = await vm.check_migration_status(migration_id)
                    if final_check.runs_remaining > 0:
                        console.print(
                            f"[yellow]Warning: {final_check.runs_remaining} processes "
                            "still running[/yellow]"
                        )
                    else:
                        await vm.complete_migration(migration_id)

        # Deploy new version
        await vm.deploy_version(
            version_id,
            version_hash,
            manifest.model_dump() if hasattr(manifest, "model_dump") else {},
        )

        console.print(f"[green]Deployed version: {version_id}[/green]")

    asyncio.run(_deploy())


@migrate_app.command(name="rollback")
def rollback_command(
    migration_id: int = typer.Argument(
        ...,
        help="Migration ID to rollback",
    ),
) -> None:
    """Rollback a migration."""
    vm = _get_version_manager()

    async def _rollback() -> None:
        await vm.initialize()

        status = await vm.check_migration_status(migration_id)
        if status.status == "not_found":
            console.print(f"[red]Migration {migration_id} not found[/red]")
            raise typer.Exit(1)

        if status.status == "rolled_back":
            console.print(f"[yellow]Migration {migration_id} already rolled back[/yellow]")
            return

        await vm.rollback_migration(migration_id)
        console.print(f"[green]Rolled back migration {migration_id}[/green]")
        console.print(f"  From: {status.to_version}")
        console.print(f"  To: {status.from_version}")

    asyncio.run(_rollback())


@migrate_app.command(name="list")
def list_command(
    limit: int = typer.Option(
        10,
        "--limit",
        "-n",
        help="Number of versions to show",
    ),
    status_filter: str = typer.Option(
        None,
        "--status",
        "-s",
        help="Filter by status (active, draining, archived)",
    ),
) -> None:
    """List deployed versions."""
    vm = _get_version_manager()

    async def _list() -> None:
        await vm.initialize()

        versions = await vm.list_versions(status=status_filter, limit=limit)

        if not versions:
            console.print("[yellow]No versions found[/yellow]")
            return

        table = Table(title="DSL Versions")
        table.add_column("Version ID", style="cyan")
        table.add_column("Deployed At")
        table.add_column("Status")
        table.add_column("Hash")

        for v in versions:
            status_style = {
                "active": "green",
                "draining": "yellow",
                "archived": "dim",
            }.get(v.status, "")

            table.add_row(
                v.version_id,
                v.deployed_at.strftime("%Y-%m-%d %H:%M:%S"),
                f"[{status_style}]{v.status}[/{status_style}]",
                v.dsl_hash[:8],
            )

        console.print(table)

    asyncio.run(_list())


@migrate_app.command(name="history")
def history_command(
    limit: int = typer.Option(
        20,
        "--limit",
        "-n",
        help="Number of migrations to show",
    ),
) -> None:
    """Show migration history."""
    from dazzle.core.process import VersionManager

    project_root = Path.cwd()
    db_path = project_root / ".dazzle" / "processes.db"

    if not db_path.exists():
        console.print("[yellow]No migration history found[/yellow]")
        return

    vm = VersionManager(db_path=db_path)

    async def _history() -> None:
        await vm.initialize()

        # Query migrations
        import aiosqlite

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM version_migrations
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            console.print("[yellow]No migration history[/yellow]")
            return

        table = Table(title="Migration History")
        table.add_column("ID", style="cyan")
        table.add_column("From")
        table.add_column("To")
        table.add_column("Started")
        table.add_column("Completed")
        table.add_column("Status")
        table.add_column("Drained", justify="right")

        for row in rows:
            status_style = {
                "completed": "green",
                "in_progress": "yellow",
                "failed": "red",
                "rolled_back": "magenta",
            }.get(row["status"], "")

            table.add_row(
                str(row["id"]),
                row["from_version"] or "-",
                row["to_version"],
                row["started_at"][:16] if row["started_at"] else "-",
                row["completed_at"][:16] if row["completed_at"] else "-",
                f"[{status_style}]{row['status']}[/{status_style}]",
                str(row["runs_drained"]),
            )

        console.print(table)

    asyncio.run(_history())
