"""
Process CLI commands.

Named process_cli.py to avoid conflict with Python's process module.

Commands:
- process propose: Propose processes from stories
- process save: Save processes from a JSON file
- process diagram: Generate a process diagram
"""

import json
from pathlib import Path

import typer

process_app = typer.Typer(
    help="Process proposal, storage, and diagramming.",
    no_args_is_help=True,
)


@process_app.command("propose")
def process_propose(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    story_ids: str = typer.Option(
        None, "--story-ids", "-s", help="Comma-separated story IDs to base proposals on"
    ),
    include_crud: bool = typer.Option(False, "--include-crud", help="Include CRUD processes"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Propose processes from stories."""
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.process.proposals import process_propose_impl

    root = resolve_project(manifest)

    ids: list[str] | None = None
    if story_ids:
        ids = [s.strip() for s in story_ids.split(",")]

    try:
        result = process_propose_impl(root, story_ids=ids, include_crud=include_crud)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(format_output(result, as_json=json_output))


@process_app.command("save")
def process_save(
    file: Path = typer.Argument(..., help="JSON file containing processes list"),
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing processes"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Save processes from a JSON file.

    The JSON file should contain a list of process objects.
    """
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.process.storage import process_save_impl

    root = resolve_project(manifest)

    file_path = Path(file).resolve()
    if not file_path.exists():
        typer.echo(f"File not found: {file_path}", err=True)
        raise typer.Exit(code=1)

    try:
        raw_processes = json.loads(file_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        typer.echo(f"Error reading JSON file: {e}", err=True)
        raise typer.Exit(code=1)

    if not isinstance(raw_processes, list):
        typer.echo("JSON file must contain a list of process objects.", err=True)
        raise typer.Exit(code=1)

    try:
        result = process_save_impl(root, raw_processes=raw_processes, overwrite=overwrite)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(format_output(result, as_json=json_output))


@process_app.command("diagram")
def process_diagram(
    process_name: str = typer.Argument(..., help="Name of the process to diagram"),
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    include_compensations: bool = typer.Option(
        False, "--include-compensations", help="Include compensation flows"
    ),
    diagram_type: str = typer.Option(
        "flowchart", "--type", "-t", help="Diagram type (e.g. flowchart)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Generate a process diagram."""
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.process.diagrams import process_diagram_impl

    root = resolve_project(manifest)

    try:
        result = process_diagram_impl(
            root,
            process_name=process_name,
            include_compensations=include_compensations,
            diagram_type=diagram_type,
        )
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(format_output(result, as_json=json_output))
