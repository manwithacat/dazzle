"""`dazzle fitness triage` and `dazzle fitness queue` commands.

Thin wrappers over ``dazzle.fitness.triage``. ``triage`` regenerates
``<project>/dev_docs/fitness-queue.md`` from the current
``fitness-backlog.md``; ``queue`` is read-only and prints the existing
queue for humans or agents.

Design: docs/superpowers/specs/2026-04-14-fitness-triage-design.md
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from dazzle.fitness.backlog import read_backlog
from dazzle.fitness.triage import (
    cluster_findings,
    read_queue_file,
    write_queue_file,
)

fitness_app = typer.Typer(
    name="fitness",
    help="Agent-Led Fitness Methodology queries and triage.",
    no_args_is_help=True,
)


def _backlog_path(project: Path) -> Path:
    return project / "dev_docs" / "fitness-backlog.md"


def _queue_path(project: Path) -> Path:
    return project / "dev_docs" / "fitness-queue.md"


def _find_examples(root: Path) -> list[Path]:
    examples_dir = root / "examples"
    if not examples_dir.exists():
        return []
    return [
        p for p in sorted(examples_dir.iterdir()) if p.is_dir() and (p / "dazzle.toml").exists()
    ]


@fitness_app.command("triage")
def triage_command(
    project: Path | None = typer.Option(None, "--project", help="Project root (default: cwd)"),
    all_examples: bool = typer.Option(
        False, "--all", help="Run triage for every examples/<name> under cwd"
    ),
    top: int = typer.Option(
        0,
        "--top",
        help="After regenerating, print the top N clusters to stdout (0 = silent)",
    ),
) -> None:
    """Dedupe + rank fitness findings into a fitness-queue.md file."""

    if all_examples:
        projects = _find_examples(Path.cwd())
        if not projects:
            typer.echo("[triage] no examples/ directory found", err=True)
            raise typer.Exit(code=1)
    else:
        projects = [project or Path.cwd()]

    for proj in projects:
        backlog = _backlog_path(proj)
        if not backlog.exists():
            typer.echo(
                f"[triage] {proj.name}: no fitness-backlog.md at {backlog}",
                err=True,
            )
            if all_examples:
                continue
            raise typer.Exit(code=1)

        rows = read_backlog(backlog)
        clusters = cluster_findings(rows)
        write_queue_file(
            _queue_path(proj),
            clusters,
            project_name=proj.name,
            raw_findings_count=len(rows),
        )
        ratio = (len(rows) / len(clusters)) if clusters else 0.0
        typer.echo(
            f"[triage] {proj.name}: {len(rows)} findings → {len(clusters)} clusters ({ratio:.1f}×)"
        )
        typer.echo(f"[triage] wrote {_queue_path(proj)}")

        if top and clusters:
            typer.echo("")
            typer.echo(f"Top {top}:")
            for rank, c in enumerate(clusters[:top], start=1):
                typer.echo(
                    f"  {rank}. {c.cluster_id} {c.severity:8s} "
                    f"{c.locus:12s} {c.persona:16s} "
                    f'size={c.cluster_size:<3d} "{c.canonical_summary}"'
                )


@fitness_app.command("queue")
def queue_command(
    project: Path | None = typer.Option(None, "--project", help="Project root (default: cwd)"),
    top: int = typer.Option(10, "--top", help="Number of clusters to show"),
    as_json: bool = typer.Option(
        False, "--json", help="Emit JSON instead of the human-readable table"
    ),
) -> None:
    """Print the current fitness-queue.md for a project."""
    proj = project or Path.cwd()
    queue_file = _queue_path(proj)
    if not queue_file.exists():
        typer.echo(
            f"[queue] no fitness-queue.md at {queue_file} — run `dazzle fitness triage` first",
            err=True,
        )
        raise typer.Exit(code=1)

    clusters = read_queue_file(queue_file)
    shown = clusters[:top]

    if as_json:
        payload = {
            "project": proj.name,
            "queue_file": str(queue_file),
            "raw_findings": _header_int(queue_file, "Raw findings"),
            "clusters_total": len(clusters),
            "clusters": [
                {
                    "rank": i + 1,
                    "cluster_id": c.cluster_id,
                    "severity": c.severity,
                    "locus": c.locus,
                    "axis": c.axis,
                    "persona": c.persona,
                    "cluster_size": c.cluster_size,
                    "summary": c.canonical_summary,
                    "first_seen": c.first_seen.isoformat(),
                    "last_seen": c.last_seen.isoformat(),
                    "sample_id": c.sample_id,
                }
                for i, c in enumerate(shown)
            ],
        }
        typer.echo(json.dumps(payload, indent=2))
        return

    typer.echo(f"Fitness queue for {proj.name} (top {top} of {len(clusters)})")
    for rank, c in enumerate(shown, start=1):
        typer.echo(
            f"  {rank}. {c.cluster_id} {c.severity:8s} "
            f"{c.locus:12s} {c.persona:16s} "
            f'size={c.cluster_size:<3d} "{c.canonical_summary}"'
        )


def _header_int(queue_file: Path, field: str) -> int:
    """Extract an integer field from the queue file header."""
    for line in queue_file.read_text().splitlines():
        if line.startswith(f"**{field}:**"):
            try:
                return int(line.split(":**", 1)[1].strip())
            except (IndexError, ValueError):
                return 0
    return 0
