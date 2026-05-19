"""``dazzle perf list`` — show past runs in the current project."""

from __future__ import annotations

from pathlib import Path

import typer

from dazzle.perf.storage import list_runs


def list_command() -> None:
    """List past perf runs under ``.dazzle/perf/``."""
    perf_dir = Path.cwd() / ".dazzle" / "perf"
    if not perf_dir.exists():
        typer.echo("No perf runs yet — run `dazzle perf trace` first.")
        raise typer.Exit(0)
    found_any = False
    for db_path in sorted(perf_dir.glob("*.db")):
        for run in list_runs(db_path):
            found_any = True
            typer.echo(
                f"{run.run_id}  {run.started_at}  "
                f"{run.ended_at or '(running)'}  "
                f"{run.app_name or '-'}  "
                f"{run.command_line}"
            )
    if not found_any:
        typer.echo("No perf runs yet.")
