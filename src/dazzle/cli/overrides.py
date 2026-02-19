"""CLI commands for the template override system (v0.29.0).

``dazzle overrides scan``   — Scan project templates and build the registry.
``dazzle overrides check``  — Check registered overrides against current framework.
``dazzle overrides list``   — List all registered overrides.
"""

from __future__ import annotations

from pathlib import Path

import typer

overrides_app = typer.Typer(help="Template override management (v0.29.0)")


def _resolve_paths(
    project_root: Path,
) -> tuple[Path, Path, Path]:
    """Resolve project templates, framework templates, and registry paths."""
    from dazzle.core.paths import project_overrides_file
    from dazzle_ui.runtime.template_renderer import TEMPLATES_DIR

    project_templates = project_root / "templates"
    return project_templates, TEMPLATES_DIR, project_overrides_file(project_root)


@overrides_app.command(name="scan")
def scan_command(
    project_root: Path = typer.Option(
        ".",
        "--project",
        "-p",
        help="Project root directory",
    ),
) -> None:
    """Scan project templates for override declarations and build the registry."""
    from dazzle import __version__
    from dazzle_ui.runtime.override_registry import build_registry, save_registry

    project_root = project_root.resolve()
    project_templates, framework_templates, registry_path = _resolve_paths(project_root)

    if not project_templates.is_dir():
        typer.echo(f"No templates/ directory found at {project_root}")
        raise typer.Exit(code=0)

    registry = build_registry(project_templates, framework_templates, __version__)
    entries = registry.get("template_overrides", [])

    if not entries:
        typer.echo("No override declarations found in project templates.")
        raise typer.Exit(code=0)

    save_registry(registry, registry_path)
    typer.echo(f"Found {len(entries)} override(s), registry saved to {registry_path}")

    for entry in entries:
        blocks = ", ".join(entry["blocks"]) if entry["blocks"] else "(no blocks declared)"
        typer.echo(f"  {entry['source']} -> {entry['target']} [{blocks}]")


@overrides_app.command(name="check")
def check_command(
    project_root: Path = typer.Option(
        ".",
        "--project",
        "-p",
        help="Project root directory",
    ),
) -> None:
    """Check registered overrides against current framework template blocks."""
    from dazzle_ui.runtime.override_registry import check_overrides

    project_root = project_root.resolve()
    project_templates, framework_templates, registry_path = _resolve_paths(project_root)

    if not registry_path.is_file():
        typer.echo("No override registry found. Run 'dazzle overrides scan' first.")
        raise typer.Exit(code=0)

    results = check_overrides(project_templates, framework_templates, registry_path)

    if not results:
        typer.echo("No overrides registered.")
        raise typer.Exit(code=0)

    has_changes = False
    for r in results:
        if r["status"] == "ok":
            typer.echo(f"  [ok]      {r['target']}:{r['block']} — block unchanged, override safe")
        elif r["status"] == "changed":
            typer.echo(
                f"  [CHANGED] {r['target']}:{r['block']} — block changed in framework, review override"
            )
            has_changes = True
        elif r["status"] == "new":
            typer.echo(f"  [new]     {r['target']}:{r['block']} — no previous hash recorded")

    if has_changes:
        typer.echo(
            "\nSome framework blocks have changed. Review your overrides and run 'dazzle overrides scan' to update hashes."
        )
        raise typer.Exit(code=1)

    typer.echo("\nAll overrides are compatible with the current framework.")


@overrides_app.command(name="list")
def list_command(
    project_root: Path = typer.Option(
        ".",
        "--project",
        "-p",
        help="Project root directory",
    ),
) -> None:
    """List all registered template overrides."""
    from dazzle_ui.runtime.override_registry import load_registry

    project_root = project_root.resolve()
    _, _, registry_path = _resolve_paths(project_root)

    registry = load_registry(registry_path)
    entries = registry.get("template_overrides", [])

    if not entries:
        typer.echo("No overrides registered.")
        raise typer.Exit(code=0)

    typer.echo(f"Override registry ({len(entries)} override(s)):\n")
    for entry in entries:
        typer.echo(f"  Source:   {entry['source']}")
        typer.echo(f"  Target:   {entry['target']}")
        typer.echo(f"  Blocks:   {', '.join(entry.get('blocks', [])) or '(none)'}")
        typer.echo(f"  Version:  {entry.get('framework_version', 'unknown')}")
        typer.echo()
