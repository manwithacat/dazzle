"""Workshop CLI command — live TUI for MCP activity."""

import logging
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
    explore: bool = typer.Option(
        False,
        "--explore",
        help="Open the Activity Explorer web UI instead of the TUI.",
    ),
    port: int = typer.Option(
        8877,
        "--port",
        help="Port for the Activity Explorer HTTP server (used with --explore).",
    ),
) -> None:
    """Watch MCP activity in a live workshop view."""
    # Suppress logging before importing MCP modules — the server __init__
    # calls logging.basicConfig(level=DEBUG) which floods stderr with handler
    # registration noise.  The workshop only reads log files / SQLite; it
    # doesn't need server-level logging.
    logging.disable(logging.CRITICAL)

    if explore:
        from dazzle.mcp.server.explorer import run_explorer

        logging.disable(logging.NOTSET)
        run_explorer(Path(project_dir).resolve(), port=port)
    else:
        from dazzle.mcp.server.workshop import run_workshop

        logging.disable(logging.NOTSET)
        run_workshop(project_dir, info=info, tail=tail, bell=bell)
