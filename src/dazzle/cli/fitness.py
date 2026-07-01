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

from dazzle.core.model_defaults import DEFAULT_JUDGMENT_MODEL
from dazzle.fitness.backlog import read_backlog
from dazzle.fitness.clones import build_clone_baseline, compute_clone_index
from dazzle.fitness.triage import (
    cluster_findings,
    read_queue_file,
    write_queue_file,
)
from dazzle.fitness.vitality import analyze_connectedness, render_report_md

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
    for line in queue_file.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"**{field}:**"):
            try:
                return int(line.split(":**", 1)[1].strip())
            except (IndexError, ValueError):
                return 0
    return 0


@fitness_app.command("investigate")
def investigate_command(
    top: int = typer.Option(1, "--top", help="Investigate the top N clusters from the queue."),
    cluster: str | None = typer.Option(
        None, "--cluster", help="Investigate a specific cluster ID."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Build + print case file; no LLM."),
    force: bool = typer.Option(
        False, "--force", help="Re-investigate clusters that already have a proposal."
    ),
    project: Path | None = typer.Option(None, "--project", help="Project root (default: cwd)."),
    model: str | None = typer.Option(None, "--model", help="LLM model override."),
) -> None:
    """Run the investigator on one or more clusters from the fitness queue."""
    import asyncio

    from dazzle.fitness.investigator.runner import run_investigation, walk_queue
    from dazzle.fitness.triage import read_queue_file

    project_root = project or Path.cwd()
    queue_path = project_root / "dev_docs" / "fitness-queue.md"

    # Validate --cluster if provided
    selected_cluster = None
    if cluster is not None:
        if not queue_path.exists():
            typer.echo("error: fitness-queue.md not found", err=True)
            raise typer.Exit(code=2)
        try:
            clusters = read_queue_file(queue_path)
        except Exception as e:
            typer.echo(f"error: failed to read queue: {e}", err=True)
            raise typer.Exit(code=2) from e
        matching = [c for c in clusters if c.cluster_id == cluster]
        if not matching:
            typer.echo(f"error: cluster {cluster!r} not in queue", err=True)
            raise typer.Exit(code=2)
        selected_cluster = matching[0]

    # Reject invalid --top values (when no --cluster is set)
    if cluster is None and top <= 0:
        typer.echo("error: --top must be >= 1", err=True)
        raise typer.Exit(code=2)

    # Build LLM client
    llm_client = _build_llm_client(model=model, dry_run=dry_run)

    async def _run() -> int:
        if selected_cluster is not None:
            result = await run_investigation(
                cluster=selected_cluster,
                dazzle_root=project_root,
                llm_client=llm_client,
                force=force,
                dry_run=dry_run,
            )
            if dry_run:
                return 0  # dry_run always succeeds
            return 0 if result is not None else 1
        else:
            if not queue_path.exists():
                typer.echo("nothing to do: queue empty")
                return 1
            results = await walk_queue(
                dazzle_root=project_root,
                llm_client=llm_client,
                top=top,
                force=force,
                dry_run=dry_run,
            )
            if not results:
                typer.echo("nothing to do: queue empty")
                return 1
            if dry_run:
                return 0
            produced = sum(1 for r in results if r is not None)
            if produced == 0:
                return 1
            return 0

    exit_code = asyncio.run(_run())
    raise typer.Exit(code=exit_code)


def _build_llm_client(model: str | None, dry_run: bool) -> object:
    """Build the LLM client for the investigator.

    In --dry-run mode, returns a placeholder that will never be called.
    In real mode, returns an LLMAPIClient from dazzle.llm.api_client.
    """
    resolved_model = model or DEFAULT_JUDGMENT_MODEL

    class _DryRunClient:
        run_id = "dry-run"
        model = resolved_model

    if dry_run:
        return _DryRunClient()

    from dazzle.llm.api_client import LLMAPIClient

    return LLMAPIClient(model=resolved_model, temperature=0.2)


_COMPLEXITY_BASELINE = Path("tests/unit/fixtures/complexity_baseline.json")
_CLONE_BASELINE = Path("tests/unit/fixtures/clone_baseline.json")


@fitness_app.command("code")
def code_command(
    project: Path | None = typer.Option(None, "--project", help="Repo root (default: cwd)"),
    since_days: int = typer.Option(180, "--since-days", help="Churn window in days"),
    write: bool = typer.Option(
        False, "--write", help="Regenerate dev_docs/framework-hotspots.md (the debt queue)"
    ),
    write_baseline: bool = typer.Option(
        False, "--write-baseline", help="Regenerate the complexity ratchet baseline"
    ),
) -> None:
    """Framework structural fitness: churn×complexity hotspot ranking for src/dazzle.

    Report-only by default. `--write` refreshes the hotspot queue; `--write-baseline`
    re-tightens the complexity ratchet (run after a refactor improves a file).
    """
    from dazzle.fitness.code import (
        build_complexity_baseline,
        change_frequency,
        compute_complexity,
        rank_hotspots,
        render_hotspots_md,
    )

    repo = project or Path.cwd()
    root = repo / "src" / "dazzle"

    if write_baseline:
        baseline = build_complexity_baseline(root)
        out = repo / _COMPLEXITY_BASELINE
        out.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n")
        typer.echo(f"Wrote {out} ({len(baseline)} files)")
        return

    ranked = rank_hotspots(compute_complexity(root), change_frequency(root, since_days))
    md = render_hotspots_md(ranked)
    if write:
        out = repo / "dev_docs" / "framework-hotspots.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text(md)
        typer.echo(f"Wrote {out}")
    else:
        typer.echo(md)


@fitness_app.command("clones")
def clones_command(
    project: Path | None = typer.Option(None, "--project", help="Repo root (default: cwd)"),
    write_baseline: bool = typer.Option(
        False, "--write-baseline", help="Regenerate the clone (reuse) ratchet baseline"
    ),
) -> None:
    """Type-2 function-clone detection — the reinvented-capability layer-3 filter.

    Reports clusters of functions sharing a structural signature (re-implemented
    capability). Report-only by default; `--write-baseline` re-tightens the clone
    ratchet (`tests/unit/test_clone_ratchet.py`) after a dedup. A cluster that is
    parallel-by-design (a family of CLI commands / route handlers) is accepted
    residue — it lives in the baseline; the gate only forbids *new* duplication.
    """
    repo = project or Path.cwd()
    root = repo / "src" / "dazzle"

    if write_baseline:
        baseline = build_clone_baseline(root)
        out = repo / _CLONE_BASELINE
        out.write_text(json.dumps(baseline, indent=2) + "\n")
        members = sum(int(e["count"]) for e in baseline)
        typer.echo(f"Wrote {out} ({len(baseline)} clusters, {members} functions)")
        return

    index = compute_clone_index(root)
    members = sum(len(m) for m in index.values())
    typer.echo(f"# Re-implemented capability — {len(index)} clone clusters, {members} functions\n")
    for cluster in sorted(index.values(), key=len, reverse=True):
        typer.echo(f"x{len(cluster)}:")
        for member in cluster:
            typer.echo(f"    {member}")
    if not index:
        typer.echo("No clone clusters found.")


@fitness_app.command("vitality")
def vitality(
    project: Path | None = typer.Option(None, "--project", help="Repo root (default: cwd)"),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write the report markdown to this file"
    ),
    top: int = typer.Option(40, "--top", help="Max islet candidates to list"),
) -> None:
    """Static connectedness report — Vitality Phase 1 (#1521).

    Builds an AST call graph over ``src/``, augments it with registry/decorator
    dispatch recovered from the code, and reports: reachability, the augmentation
    delta (functions rescued by the dispatch recovery — the acceptance signal), and
    the islet candidates (functions with no caller that are neither reached nor
    dispatch-referenced). Report-only; AST-only over-reports, so candidates are
    review prompts, not dead code (Phase 2 coverage/runtime would clear false
    positives). See ``dev_docs/dazzle-vitality-thesis.md``.
    """
    src_root = (project or Path.cwd()) / "src"
    report = analyze_connectedness(src_root)
    md = render_report_md(report, top=top)
    if output is not None:
        output.write_text(md, encoding="utf-8")
        typer.echo(f"Wrote {output}")
    else:
        typer.echo(md)
