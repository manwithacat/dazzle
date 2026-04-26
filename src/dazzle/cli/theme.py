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


@theme_app.command(name="init")
def init_command(
    name: str = typer.Argument(
        ...,
        help="New theme name. Lowercase + hyphens (e.g. 'my-brand', 'fintech-pro').",
    ),
    inspired_by: str = typer.Option(
        "linear-dark",
        "--inspired-by",
        "-i",
        help="Existing theme to copy as a starting point. Defaults to linear-dark.",
    ),
    project_root: Path = typer.Option(
        Path.cwd(),
        "--project-root",
        help="Project directory; the new theme lands under <project>/themes/.",
    ),
) -> None:
    """Scaffold a new project-local theme as <project>/themes/<name>.css + .toml.

    Copies an existing theme (default: linear-dark) so you start from a
    working baseline. Edit the resulting CSS to customise; activate via
    [ui] theme = "<name>" in dazzle.toml.
    """
    from dazzle_ui.themes.app_theme_registry import discover_themes

    # Validate name
    if not name or not name.replace("-", "").replace("_", "").isalnum():
        typer.echo(
            f"Invalid theme name {name!r}. Use lowercase letters, digits, "
            f"and hyphens only (e.g. 'my-brand').",
            err=True,
        )
        raise typer.Exit(2)
    if name != name.lower():
        typer.echo(
            f"Theme name {name!r} should be lowercase (e.g. {name.lower()!r}).",
            err=True,
        )
        raise typer.Exit(2)

    # Source theme to copy from
    registry = discover_themes(project_root=project_root)
    source = registry.get(inspired_by)
    if source is None:
        available = sorted(registry.keys())
        typer.echo(
            f"Source theme {inspired_by!r} not found. Available: {available}",
            err=True,
        )
        raise typer.Exit(2)

    target_dir = project_root / "themes"
    target_css = target_dir / f"{name}.css"
    target_toml = target_dir / f"{name}.toml"

    if target_css.exists() or target_toml.exists():
        typer.echo(
            f"Theme {name!r} already exists at {target_dir}. Delete it first to "
            f"re-init from a different source.",
            err=True,
        )
        raise typer.Exit(2)

    target_dir.mkdir(parents=True, exist_ok=True)

    # Copy CSS verbatim — the override layer is identical, just the
    # values differ. User edits to taste.
    target_css.write_text(source.css_path.read_text())

    # Boilerplate TOML — user owns the metadata; we just give them the
    # right keys.
    target_toml.write_text(
        f'name = "{name}"\n'
        f'description = "Project-local theme (scaffolded from {inspired_by})"\n'
        f'inspired_by = "{source.inspired_by or inspired_by}"\n'
        f'default_color_scheme = "{source.default_color_scheme}"\n'
        f"font_preconnect = []\n"
        f'tags = ["project-local"]\n'
    )

    typer.echo(f"Created theme {name!r}:")
    typer.echo(f"  CSS:  {target_css.relative_to(project_root)}")
    typer.echo(f"  TOML: {target_toml.relative_to(project_root)}")
    typer.echo()
    typer.echo(f"Edit {target_css.name} to customise the token values.")
    typer.echo(f'Activate by adding `theme = "{name}"` to the [ui] block in dazzle.toml.')


@theme_app.command(name="preview")
def preview_command(
    name: str = typer.Argument(
        ...,
        help="Theme to preview. Must exist in the registry (use `dazzle theme list`).",
    ),
    project_root: Path = typer.Option(
        Path.cwd(),
        "--project-root",
        help="Project directory. Defaults to cwd.",
    ),
) -> None:
    """Boot the project with a theme override, no commit needed.

    Sets ``DAZZLE_OVERRIDE_THEME=<name>`` in the environment and execs
    ``dazzle serve --local``. The override wins over both DSL
    ``theme:`` and ``[ui] theme`` in dazzle.toml — restoring the
    original theme is just exiting the preview (no toml mutation, no
    DSL edit).
    """
    import os
    import sys

    from dazzle_ui.themes.app_theme_registry import discover_themes

    # Validate theme exists before exec'ing — otherwise the user gets a
    # 404 mid-session and won't know why.
    registry = discover_themes(project_root=project_root)
    if name not in registry:
        available = sorted(registry.keys())
        typer.echo(
            f"Theme {name!r} not found. Available: {available}",
            err=True,
        )
        raise typer.Exit(2)

    typer.echo(f"Previewing theme {name!r} via DAZZLE_OVERRIDE_THEME env var.")
    typer.echo("Press Ctrl-C to exit; no project files will be modified.")
    typer.echo()

    # Hand off to `dazzle serve --local` with the override env var set.
    env = {**os.environ, "DAZZLE_OVERRIDE_THEME": name}
    # Resolve the dazzle entrypoint from sys.executable so we use the
    # same interpreter (don't trust PATH order — venv awareness).
    cmd = [sys.executable, "-m", "dazzle", "serve", "--local"]
    # execvpe replaces this process — we don't need to track the child
    # or proxy signals. Ctrl-C cleans up the server directly.
    os.execvpe(cmd[0], cmd, env)
