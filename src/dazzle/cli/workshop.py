"""Workshop CLI command — live TUI for MCP activity."""

from pathlib import Path

import typer


def workshop_command(
    project_dir: Path = typer.Option(  # noqa: B008
        ".",
        "--project-dir",
        "-p",
        help="Project root directory (default: current directory)",
    ),
    info: bool = typer.Option(
        False,
        "--info",
        help="Print the resolved activity log path and exit.",
    ),
    tail: int = typer.Option(
        20,
        "--tail",
        "-n",
        help="Number of completed entries to keep visible (default: 20).",
    ),
    bell: bool = typer.Option(
        False,
        "--bell",
        help="Ring terminal bell on errors.",
    ),
) -> None:
    """Watch MCP activity in a live workshop view."""
    from dazzle.mcp.server.workshop import run_workshop

    run_workshop(project_dir, info=info, tail=tail, bell=bell)
