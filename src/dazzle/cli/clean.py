"""Local regenerable-state cleanup (gitignored trees).

``dazzle clean snapshots`` reclaims exploded ``.dazzle/spec_snapshots/``
trees left by historical ops rollback mirrors (ADR-0051 retired the writer).
"""

from __future__ import annotations

from pathlib import Path

import typer

from dazzle.core.local_snapshots import (
    DEFAULT_KEEP,
    any_nested_snapshots,
    list_snapshot_ids,
    prune_snapshots,
    remove_all_snapshots,
    snapshots_root,
)

clean_app = typer.Typer(
    help="Remove regenerable local state (gitignored). Does not touch git or source.",
    no_args_is_help=True,
)


@clean_app.command("snapshots")
def clean_snapshots_command(
    all: bool = typer.Option(
        False,
        "--all",
        help="Delete the entire .dazzle/spec_snapshots tree (recommended after recursive nests).",
    ),
    keep: int = typer.Option(
        DEFAULT_KEEP,
        "--keep",
        min=0,
        help="When not using --all, keep the N newest top-level snapshot dirs (mtime).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="List what would be removed without deleting.",
    ),
    project: Path = typer.Option(
        Path("."),
        "--project",
        help="Project root (default: cwd).",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
) -> None:
    """Clean local ``.dazzle/spec_snapshots`` (and warn about nested trees).

    Historical ops RollbackManager wrote DSL-only snapshots here; some trees
    later nested full project copies and exploded disk use. The product writer
    is retired (ADR-0051). Prefer ``--all`` for reclaim after nesting.
    """
    root = snapshots_root(project)
    ids = list_snapshot_ids(project)
    nested = any_nested_snapshots(project)

    typer.echo(f"Snapshots root: {root}")
    typer.echo(f"Top-level snapshots: {len(ids)}")
    if nested:
        typer.echo(
            f"[warn] {len(nested)} top-level snapshot(s) contain nested "
            f".dazzle/spec_snapshots (recursive explosion). Prefer --all."
        )
        for name in nested[:10]:
            typer.echo(f"  nested: {name}")
        if len(nested) > 10:
            typer.echo(f"  … and {len(nested) - 10} more")

    if not ids and not root.exists():
        typer.echo("Nothing to clean.")
        raise typer.Exit(0)

    if all:
        report = remove_all_snapshots(project, dry_run=dry_run)
        action = "Would remove" if dry_run else "Removed"
        typer.echo(f"{action} entire tree ({report.removed_count} top-level id(s)).")
    else:
        if nested:
            typer.echo(
                "[warn] Prune only drops whole top-level ids; nested junk inside "
                "kept dirs remains. Use --all for a full reclaim."
            )
        report = prune_snapshots(project, keep=keep, dry_run=dry_run)
        action = "Would remove" if dry_run else "Removed"
        typer.echo(f"{action} {report.removed_count} id(s); keep={len(report.kept)} (keep={keep}).")
        if report.removed and dry_run:
            for name in report.removed[:20]:
                typer.echo(f"  - {name}")
            if len(report.removed) > 20:
                typer.echo(f"  … and {len(report.removed) - 20} more")

    if dry_run:
        typer.echo("Dry run — no files deleted.")
