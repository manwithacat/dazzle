"""CLI commands for runtime parameter management."""

from __future__ import annotations

import json
from pathlib import Path

import typer

param_app = typer.Typer(help="Runtime parameter management.", no_args_is_help=True)


@param_app.command(name="list")
def list_command(
    project_root: Path = typer.Option(Path("."), "--project", help="Project root"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all declared runtime parameters."""
    from dazzle.cli._output import format_output
    from dazzle.mcp.server.handlers.param import param_list_handler

    result = json.loads(param_list_handler(project_root.resolve(), {}))
    typer.echo(format_output(result, as_json=json_output))


@param_app.command(name="get")
def get_command(
    key: str = typer.Argument(help="Parameter key (e.g., heatmap.rag.thresholds)"),
    project_root: Path = typer.Option(Path("."), "--project", help="Project root"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Get a specific parameter's declaration and default value."""
    from dazzle.cli._output import format_output
    from dazzle.mcp.server.handlers.param import param_get_handler

    result = json.loads(param_get_handler(project_root.resolve(), {"key": key}))
    typer.echo(format_output(result, as_json=json_output))


@param_app.command(name="validate")
def validate_command(
    project_root: Path = typer.Option(Path("."), "--project", help="Project root"),
) -> None:
    """Validate all parameter declarations against their defaults."""
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle_back.runtime.param_store import validate_param_value

    appspec = load_project_appspec(project_root.resolve())
    params = getattr(appspec, "params", [])
    if not params:
        typer.echo("No parameters declared.")
        return
    errors_found = False
    for p in params:
        errs = validate_param_value(p, p.default)
        if errs:
            errors_found = True
            typer.secho(f"  {p.key}: {'; '.join(errs)}", fg=typer.colors.RED)
        else:
            typer.secho(f"  {p.key}: OK", fg=typer.colors.GREEN)
    if errors_found:
        raise typer.Exit(code=1)
