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
) -> None:
    """Watch MCP activity in a live workshop view."""
    from dazzle.mcp.server.workshop import run_workshop

    run_workshop(project_dir)
