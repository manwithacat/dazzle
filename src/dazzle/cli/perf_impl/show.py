"""``dazzle perf show`` — dump a span tree for one run."""

from __future__ import annotations

from pathlib import Path

import typer

from dazzle.perf.run_id import latest_run_id
from dazzle.perf.storage import iter_spans


def show_command(
    run: str | None = typer.Option(None, "--run", help="Run id (default: latest)"),
) -> None:
    perf_dir = Path.cwd() / ".dazzle" / "perf"
    run_id = run or latest_run_id(perf_dir)
    if run_id is None:
        typer.echo("No perf runs found.")
        raise typer.Exit(1)
    db_path = perf_dir / f"{run_id}.db"
    if not db_path.exists():
        typer.echo(f"No trace file for run {run_id}")
        raise typer.Exit(1)

    children: dict[str | None, list] = {}
    for span in iter_spans(db_path, run_id):
        children.setdefault(span.parent_span_id, []).append(span)

    def emit(parent: str | None, depth: int) -> None:
        for span in children.get(parent, []):
            duration_ms = span.duration_ns / 1e6
            typer.echo(f"{'  ' * depth}{span.name}  {duration_ms:.2f}ms  [{span.status}]")
            emit(span.span_id, depth + 1)

    emit(None, 0)
