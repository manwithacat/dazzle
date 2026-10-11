"""`dazzle fitness code` and `dazzle fitness clones` — framework structural ratchets.

Both commands report on ``src/dazzle`` and regenerate the baselines that
``tests/unit/test_complexity_ratchet.py`` and ``tests/unit/test_clone_ratchet.py``
hold (``--write-baseline``).
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from dazzle.fitness.clones import build_clone_baseline, compute_clone_index

fitness_app = typer.Typer(
    name="fitness",
    help="Framework structural-fitness ratchets (complexity, clones).",
    no_args_is_help=True,
)


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
