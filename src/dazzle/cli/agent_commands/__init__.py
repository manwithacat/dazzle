"""Agent-first development commands for Dazzle projects."""

from pathlib import Path

import typer

agent_app = typer.Typer(
    name="agent",
    help="Agent-first development commands.",
    no_args_is_help=True,
)


@agent_app.command("sync")
def sync_command(
    project: Path = typer.Option(
        Path("."),
        "--project",
        "-p",
        help="Project root directory.",
    ),
) -> None:
    """Sync agent commands from the Dazzle framework to the project.

    Writes .claude/commands/*.md, AGENTS.md, and seeds agent/ backlog files.
    Idempotent — safe to run repeatedly.
    """
    project = project.resolve()
    if not (project / "dazzle.toml").exists():
        typer.echo(f"Error: {project} does not contain a dazzle.toml", err=True)
        raise typer.Exit(code=1)

    from .renderer import sync_to_project

    manifest = sync_to_project(project)

    available = sum(1 for cs in manifest.commands.values() if cs.available)
    total = len(manifest.commands)
    typer.echo(f"Synced {available}/{total} agent commands to {project}")
    for name, cs in sorted(manifest.commands.items()):
        status = "available" if cs.available else f"unavailable ({cs.reason})"
        typer.echo(f"  /{name}: {status}")
