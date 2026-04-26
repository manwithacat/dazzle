"""``dazzle theme`` — list, preview, and scaffold app-shell themes.

Phase B Patch 3 of the design-system formalisation work
(see ``dev_docs/2026-04-26-design-system-phase-b.md``). v0.61.39 ships
the ``list`` subcommand only; ``preview`` and ``init`` arrive in
Patches 4 and 5.
"""

from __future__ import annotations

from pathlib import Path

import typer

theme_app = typer.Typer(
    help="Inspect and manage app-shell themes (linear-dark / paper / stripe / project-local).",
    no_args_is_help=True,
)


@theme_app.command(name="list")
def list_command(
    tag: str | None = typer.Option(
        None,
        "--tag",
        help="Filter to themes whose `tags` list includes this value.",
    ),
    scheme: str | None = typer.Option(
        None,
        "--scheme",
        help="Filter to themes with this default_color_scheme (light/dark/auto).",
    ),
    project_root: Path = typer.Option(
        Path.cwd(),
        "--project-root",
        help="Project directory to discover local themes in. Defaults to cwd.",
    ),
) -> None:
    """List shipped + project-local themes with metadata."""
    from dazzle_ui.themes.app_theme_registry import discover_themes

    themes = discover_themes(project_root=project_root)
    rows = sorted(themes.values(), key=lambda m: m.name)

    if tag is not None:
        rows = [m for m in rows if tag in m.tags]
    if scheme is not None:
        if scheme not in {"light", "dark", "auto"}:
            typer.echo(f"Invalid --scheme {scheme!r}; expected light/dark/auto.", err=True)
            raise typer.Exit(2)
        rows = [m for m in rows if m.default_color_scheme == scheme]

    if not rows:
        typer.echo("No themes match the filter.")
        raise typer.Exit(0)

    # Compute column widths from the actual rows so the table stays
    # tight when nothing is super-wide.
    name_w = max(len(m.name) for m in rows)
    src_w = max(len(m.source) for m in rows)
    scheme_w = max(len(m.default_color_scheme) for m in rows)
    inspired_w = max((len(m.inspired_by) for m in rows), default=0)

    header = (
        f"{'Name':<{name_w}}  "
        f"{'Scheme':<{scheme_w}}  "
        f"{'Src':<{src_w}}  "
        f"{'Tags':<24}  "
        f"{'Inspired by':<{inspired_w}}"
    )
    typer.echo(header)
    typer.echo("─" * len(header))

    for m in rows:
        tags_str = ",".join(m.tags) if m.tags else "—"
        if len(tags_str) > 24:
            tags_str = tags_str[:21] + "..."
        inspired = m.inspired_by or "—"
        typer.echo(
            f"{m.name:<{name_w}}  "
            f"{m.default_color_scheme:<{scheme_w}}  "
            f"{m.source:<{src_w}}  "
            f"{tags_str:<24}  "
            f"{inspired:<{inspired_w}}"
        )

    typer.echo()
    typer.echo(f"{len(rows)} theme(s).")
