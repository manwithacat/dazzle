"""
Test design CLI commands.

Commands:
- test-design propose-persona: Propose test personas
- test-design save: Save test designs from a JSON file
- test-design coverage-actions: Show coverage action suggestions
- test-design runtime-gaps: Identify runtime coverage gaps
- test-design save-runtime: Save runtime coverage data from a JSON file
- test-design improve-coverage: Suggest coverage improvements
"""

import json
from pathlib import Path

import typer

test_design_app = typer.Typer(
    help="Test design proposal, persistence, and coverage analysis.",
    no_args_is_help=True,
)


@test_design_app.command("propose-persona")
def propose_persona(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    persona_filter: str = typer.Option(None, "--persona", "-p", help="Filter by persona ID"),
    max_tests: int = typer.Option(10, "--max", help="Maximum number of tests to propose"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Propose test personas."""
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.test_design.proposals import (
        test_design_propose_persona_impl,
    )

    root = resolve_project(manifest)

    try:
        result = test_design_propose_persona_impl(
            root, persona_filter=persona_filter, max_tests=max_tests
        )
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(format_output(result, as_json=json_output))


@test_design_app.command("save")
def save_designs(
    file: Path = typer.Argument(..., help="JSON file containing test designs list"),
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing designs"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Save test designs from a JSON file.

    The JSON file should contain a list of test design objects.
    """
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.test_design.persistence import test_design_save_impl

    root = resolve_project(manifest)

    file_path = Path(file).resolve()
    if not file_path.exists():
        typer.echo(f"File not found: {file_path}", err=True)
        raise typer.Exit(code=1)

    try:
        designs_data = json.loads(file_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        typer.echo(f"Error reading JSON file: {e}", err=True)
        raise typer.Exit(code=1)

    if not isinstance(designs_data, list):
        typer.echo("JSON file must contain a list of test design objects.", err=True)
        raise typer.Exit(code=1)

    try:
        result = test_design_save_impl(root, designs_data=designs_data, overwrite=overwrite)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(format_output(result, as_json=json_output))


@test_design_app.command("coverage-actions")
def coverage_actions(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    max_actions: int = typer.Option(5, "--max", help="Maximum number of actions"),
    focus: str = typer.Option("all", "--focus", "-f", help="Focus area: all, entity, surface"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show coverage action suggestions."""
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.test_design.coverage import (
        test_design_coverage_actions_impl,
    )

    root = resolve_project(manifest)

    try:
        result = test_design_coverage_actions_impl(root, max_actions=max_actions, focus=focus)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(format_output(result, as_json=json_output))


@test_design_app.command("runtime-gaps")
def runtime_gaps(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    max_actions: int = typer.Option(5, "--max", help="Maximum number of actions"),
    coverage_path: str = typer.Option(
        None, "--coverage-path", help="Path to runtime coverage file"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Identify runtime coverage gaps."""
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.test_design.coverage import (
        test_design_runtime_gaps_impl,
    )

    root = resolve_project(manifest)

    try:
        result = test_design_runtime_gaps_impl(
            root, max_actions=max_actions, coverage_path=coverage_path
        )
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(format_output(result, as_json=json_output))


@test_design_app.command("save-runtime")
def save_runtime(
    file: Path = typer.Argument(..., help="JSON file containing runtime coverage data"),
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Save runtime coverage data from a JSON file."""
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.test_design.coverage import (
        test_design_save_runtime_impl,
    )

    root = resolve_project(manifest)

    file_path = Path(file).resolve()
    if not file_path.exists():
        typer.echo(f"File not found: {file_path}", err=True)
        raise typer.Exit(code=1)

    try:
        coverage_data = json.loads(file_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        typer.echo(f"Error reading JSON file: {e}", err=True)
        raise typer.Exit(code=1)

    if not isinstance(coverage_data, dict):
        typer.echo("JSON file must contain a coverage data object.", err=True)
        raise typer.Exit(code=1)

    try:
        result = test_design_save_runtime_impl(root, coverage_data=coverage_data)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(format_output(result, as_json=json_output))


@test_design_app.command("improve-coverage")
def improve_coverage(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    max_actions: int = typer.Option(5, "--max", help="Maximum number of actions"),
    focus: str = typer.Option("all", "--focus", "-f", help="Focus area: all, entity, surface"),
    coverage_path: str = typer.Option(
        None, "--coverage-path", help="Path to runtime coverage file"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Suggest coverage improvements."""
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.test_design.coverage import (
        test_design_improve_coverage_impl,
    )

    root = resolve_project(manifest)

    try:
        result = test_design_improve_coverage_impl(
            root, max_actions=max_actions, focus=focus, coverage_path=coverage_path
        )
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(format_output(result, as_json=json_output))
