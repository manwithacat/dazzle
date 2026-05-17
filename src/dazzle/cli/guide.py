"""``dazzle guide`` — onboarding-guide inspection (v0.71.7).

Companion to the MCP ``guide`` tool. Provides the same operations as
human-readable CLI output rather than JSON.

Commands:
- ``dazzle guide list`` — every guide declared in the project.
- ``dazzle guide narrate <name>`` — linear narrative of one guide's
  steps. Useful for human review during DSL authoring + for
  generating documentation.

Concordance is already part of ``dazzle validate`` (the linker pass
shipped in v0.71.0); no separate command is needed here.
"""

from pathlib import Path

import typer

from dazzle.core.appspec_loader import load_project_appspec

guide_app = typer.Typer(
    help="Inspect onboarding guides declared in the project DSL.",
    no_args_is_help=True,
)


@guide_app.command(name="list")
def guide_list(
    project_dir: Path = typer.Option(  # noqa: B008
        Path("."),
        "--project",
        "-p",
        help="Project directory (default: current directory).",
    ),
) -> None:
    """List every guide declared in the project DSL."""
    try:
        appspec = load_project_appspec(project_dir)
    except Exception as exc:
        typer.echo(f"Error loading DSL: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    guides = list(getattr(appspec, "guides", None) or [])
    if not guides:
        typer.echo("No guides declared in this project.")
        return

    typer.echo(f"{len(guides)} guide(s) declared:")
    typer.echo("")
    for g in guides:
        on_complete_marker = " (on_complete set)" if g.on_complete is not None else ""
        typer.echo(f"  {g.name} — {g.title!r}")
        typer.echo(f"    audience: {g.audience}")
        typer.echo(
            f"    {len(g.steps)} step(s); "
            f"order: {', '.join(g.step_order) if g.step_order else '(none)'}"
            f"{on_complete_marker}"
        )
        typer.echo("")


@guide_app.command(name="narrate")
def guide_narrate(
    name: str = typer.Argument(..., help="Guide name (e.g. workspace_setup)."),
    project_dir: Path = typer.Option(  # noqa: B008
        Path("."),
        "--project",
        "-p",
        help="Project directory (default: current directory).",
    ),
) -> None:
    """Materialise the linear narrative of one guide's steps.

    Output format: one section per step in ``step_order``, showing
    title + body + target + completion criterion + CTA. Orphan steps
    (declared but not in ``step_order`` — never fire at runtime) are
    listed at the end with a warning marker.
    """
    try:
        appspec = load_project_appspec(project_dir)
    except Exception as exc:
        typer.echo(f"Error loading DSL: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    guides = list(getattr(appspec, "guides", None) or [])
    spec = next((g for g in guides if g.name == name), None)
    if spec is None:
        typer.echo(
            f"Unknown guide: {name!r}. Known: {[g.name for g in guides] or '(none declared)'}",
            err=True,
        )
        raise typer.Exit(code=1)

    typer.echo(f"# {spec.title}")
    typer.echo("")
    typer.echo(f"**Name:** `{spec.name}`")
    typer.echo(f"**Audience:** `{spec.audience}`")
    typer.echo("")

    by_name = {s.name: s for s in spec.steps}
    typer.echo(f"## Steps ({len(spec.step_order)} in order)")
    typer.echo("")
    for idx, step_name in enumerate(spec.step_order, start=1):
        step = by_name.get(step_name)
        if step is None:
            typer.echo(f"### {idx}. {step_name}  ⚠ UNRESOLVED (linker drift)")
            typer.echo("")
            continue
        _emit_step(idx, step)

    orphans = [s for s in spec.steps if s.name not in set(spec.step_order)]
    if orphans:
        typer.echo("## Orphan steps (declared but not in step_order — never fire)")
        typer.echo("")
        for step in orphans:
            _emit_step(0, step, orphan=True)

    if spec.on_complete is not None:
        typer.echo("## On complete")
        typer.echo("")
        if spec.on_complete.emit:
            typer.echo(f"- Emit event: `{spec.on_complete.emit}`")
        if spec.on_complete.redirect:
            typer.echo(f"- Redirect to: `{spec.on_complete.redirect}`")
        typer.echo("")


def _emit_step(idx: int, step: object, *, orphan: bool = False) -> None:
    """Render one step block as markdown."""
    kind = step.kind.value if hasattr(step.kind, "value") else str(step.kind)  # type: ignore[attr-defined]
    heading_prefix = "⚠ " if orphan else f"{idx}. "
    typer.echo(f"### {heading_prefix}{step.name} *({kind})*")  # type: ignore[attr-defined]
    typer.echo("")
    typer.echo(f"**Title:** {step.title!r}")  # type: ignore[attr-defined]
    typer.echo(f"**Body:** {step.body!r}")  # type: ignore[attr-defined]
    typer.echo(f"**Target:** `{step.target}`")  # type: ignore[attr-defined]
    if step.placement and step.placement != "bottom":  # type: ignore[attr-defined]
        typer.echo(f"**Placement:** `{step.placement}`")  # type: ignore[attr-defined]
    if step.cta_target:  # type: ignore[attr-defined]
        cta_label = step.cta_label or "(default)"  # type: ignore[attr-defined]
        typer.echo(f"**CTA:** {cta_label!r} → `{step.cta_target}`")  # type: ignore[attr-defined]
    if step.audience_when:  # type: ignore[attr-defined]
        typer.echo(f"**Audience override:** `{step.audience_when}`")  # type: ignore[attr-defined]
    co = step.complete_on  # type: ignore[attr-defined]
    co_kind = co.kind.value if hasattr(co.kind, "value") else str(co.kind)
    co_payload = ""
    if co.event_ref:
        co_payload = f" — `{co.event_ref}`"
    elif co.field_filled:
        co_payload = f" — `{co.field_filled}`"
    typer.echo(f"**Completes on:** `{co_kind}`{co_payload}")
    typer.echo("")
