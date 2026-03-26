"""Database shell command — drop into psql with app's DATABASE_URL."""

import shutil
import subprocess
from typing import Annotated

import typer
from rich.console import Console

console = Console()


def _resolve_db_url(database_url: str | None = None) -> str:
    """Resolve database URL from explicit arg, manifest, or env."""
    from pathlib import Path

    from dazzle.core.manifest import load_manifest, resolve_database_url

    manifest = None
    manifest_path = Path.cwd() / "dazzle.toml"
    if manifest_path.exists():
        manifest = load_manifest(manifest_path)
    return resolve_database_url(manifest, explicit_url=database_url or "")


def dbshell_command(
    command: Annotated[str | None, typer.Option("-c", help="Run a single SQL command")] = None,
    read_only: Annotated[
        bool, typer.Option("--read-only", help="Connect in read-only mode")
    ] = False,
    database_url: Annotated[
        str | None,
        typer.Option("--database-url", envvar="DATABASE_URL", help="PostgreSQL database URL"),
    ] = None,
) -> None:
    """Open an interactive PostgreSQL shell (psql) with the app's database."""
    psql_path = shutil.which("psql")
    if not psql_path:
        console.print("[red]psql not found.[/red] Install PostgreSQL client tools:")
        console.print("  macOS: brew install libpq && brew link --force libpq")
        console.print("  Ubuntu: sudo apt install postgresql-client")
        raise typer.Exit(1)

    url = _resolve_db_url(database_url)
    if not url:
        console.print(
            "[red]No DATABASE_URL found.[/red] Set it in dazzle.toml, environment, or --database-url."
        )
        raise typer.Exit(1)

    args = ["psql", url]
    if command:
        args.extend(["-c", command])
    if read_only:
        args.extend(["-v", "default_transaction_read_only=on"])

    subprocess.run(args, check=False)
