"""``dazzle perf report`` — render findings from a trace SQLite file."""

from __future__ import annotations

from pathlib import Path

import typer

from dazzle.perf.findings import build_findings, render_json, render_markdown
from dazzle.perf.run_id import latest_run_id


def report_command(
    run: str | None = typer.Option(None, "--run", help="Run id (default: latest)"),
    fmt: str = typer.Option("md", "--format", help="md|json"),
    top: int = typer.Option(10, "--top", help="Per-section row cap"),  # noqa: ARG001
    baseline: str | None = typer.Option(
        None,
        "--baseline",
        help="Diff mode — compare against a prior run id (not yet implemented).",
    ),  # noqa: ARG001
) -> None:
    perf_dir = Path.cwd() / ".dazzle" / "perf"
    run_id = run or latest_run_id(perf_dir)
    if run_id is None:
        typer.echo("No perf runs found. Run `dazzle perf trace` first.")
        raise typer.Exit(1)
    db_path = perf_dir / f"{run_id}.db"
    if not db_path.exists():
        typer.echo(f"No trace file for run {run_id}")
        raise typer.Exit(1)

    report = build_findings(db_path, run_id)
    if fmt == "json":
        typer.echo(render_json(report))
    else:
        typer.echo(render_markdown(report))
