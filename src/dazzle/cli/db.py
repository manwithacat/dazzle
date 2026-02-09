"""
DAZZLE Database Migration CLI Commands.

Wraps Alembic's programmatic API for managing PostgreSQL schema migrations:
- revision: Generate a new migration from EntitySpec diff
- upgrade:  Apply pending migrations
- downgrade: Rollback migrations
- current:  Show current revision
- history:  Show migration history
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

db_app = typer.Typer(
    help="Database migration commands (Alembic)",
    no_args_is_help=True,
)

console = Console()


def _get_alembic_cfg() -> Any:
    """Build an Alembic Config pointing to dazzle_back's alembic directory."""
    from alembic.config import Config as AlembicConfig

    alembic_dir = (Path(__file__).resolve().parents[2] / "dazzle_back" / "alembic").resolve()
    ini_path = alembic_dir / "alembic.ini"

    cfg = AlembicConfig(str(ini_path))
    cfg.set_main_option("script_location", str(alembic_dir))

    # Override sqlalchemy.url from environment if available
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url:
        cfg.set_main_option("sqlalchemy.url", db_url)

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
    """Generate a new migration revision."""
    from alembic import command

    cfg = _get_alembic_cfg()

    try:
        command.revision(cfg, message=message, autogenerate=autogenerate)
        console.print(f"[green]Migration revision created: {message}[/green]")
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
