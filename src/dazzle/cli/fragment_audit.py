"""`dazzle fragment-audit` — Fragment-rendering coverage audit.

Walks any AppSpec and reports per-surface whether the typed Fragment
substrate can render it. Aggregates blockers across the appspec so the
user can see which closure unlocks the most surfaces.

Mirrors the shape of `dazzle coverage` (framework-artefact coverage).

Usage
-----
    dazzle fragment-audit <project-path>                # human-readable
    dazzle fragment-audit <project-path> --json         # JSON
    dazzle fragment-audit <project-path> --fail-on-blocked   # CI gate
"""

from __future__ import annotations

from pathlib import Path

import typer

from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules
from dazzle.core.renderer_registry import known_renderer_names
from dazzle.render.fragment.coverage import audit_appspec


def fragment_audit_command(
    project_path: Path = typer.Argument(
        ...,
        help="Path to a Dazzle project (directory containing dazzle.toml).",
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Emit JSON instead of human-readable text."
    ),
    fail_on_blocked: bool = typer.Option(
        False,
        "--fail-on-blocked",
        help="Exit 1 if any surface is blocked (CI-gate mode).",
    ),
) -> None:
    """Audit Fragment-rendering coverage for the given project."""
    if not project_path.exists():
        typer.echo(f"Project path does not exist: {project_path}", err=True)
        raise typer.Exit(code=2)

    # Reuse the canonical project-loading pattern (cf. dazzle deploy).

    manifest_path = (project_path / "dazzle.toml").resolve()
    if not manifest_path.exists():
        typer.echo(
            f"No dazzle.toml found at {manifest_path}; not a Dazzle project.",
            err=True,
        )
        raise typer.Exit(code=2)

    manifest = load_manifest(manifest_path)
    root = manifest_path.parent
    dsl_files = discover_dsl_files(root, manifest)
    if not dsl_files:
        typer.echo(f"No DSL files found in {project_path}", err=True)
        raise typer.Exit(code=2)

    modules = parse_modules(dsl_files)
    appspec = build_appspec(
        modules,
        manifest.project_root,
        known_renderers=known_renderer_names(manifest),
    )
    report = audit_appspec(appspec)

    if json_output:
        typer.echo(report.to_json())
    else:
        typer.echo(report.to_text())

    # Exit 1 if any surface is blocked AND --fail-on-blocked is set.
    # Default: exit 0 even when blocked (informational reports).
    if fail_on_blocked and report.blocked_count > 0:
        raise typer.Exit(code=1)
