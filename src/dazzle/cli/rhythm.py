"""
Rhythm CLI commands.

Commands:
- rhythm propose: Propose rhythms for a persona
- rhythm evaluate: Evaluate a rhythm by name
- rhythm gaps: Find rhythm gaps in the project
- rhythm fidelity: Check fidelity of a named rhythm
- rhythm lifecycle: Show rhythm lifecycle overview
"""

from __future__ import annotations

import typer

rhythm_app = typer.Typer(
    help="Rhythm analysis and lifecycle management.",
    no_args_is_help=True,
)


@rhythm_app.command("propose")
def rhythm_propose(
    persona_id: str = typer.Argument(..., help="Persona ID to propose rhythms for"),
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Propose rhythms for a persona."""
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.rhythm import rhythm_propose_impl

    root = resolve_project(manifest)

    try:
        result = rhythm_propose_impl(root, persona_id=persona_id)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(format_output(result, as_json=json_output))


@rhythm_app.command("evaluate")
def rhythm_evaluate(
    name: str = typer.Argument(..., help="Rhythm name to evaluate"),
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    action: str = typer.Option("evaluate", "--action", "-a", help="Action: evaluate or score"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Evaluate a rhythm by name."""
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.rhythm import rhythm_evaluate_impl

    root = resolve_project(manifest)

    try:
        result = rhythm_evaluate_impl(root, name=name, action=action)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(format_output(result, as_json=json_output))


@rhythm_app.command("gaps")
def rhythm_gaps(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Find rhythm gaps in the project."""
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.rhythm import rhythm_gaps_impl

    root = resolve_project(manifest)

    try:
        result = rhythm_gaps_impl(root)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(format_output(result, as_json=json_output))


@rhythm_app.command("fidelity")
def rhythm_fidelity(
    name: str = typer.Argument(..., help="Rhythm name to check fidelity for"),
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Check fidelity of a named rhythm."""
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.rhythm import rhythm_fidelity_impl

    root = resolve_project(manifest)

    try:
        result = rhythm_fidelity_impl(root, name=name)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(format_output(result, as_json=json_output))


@rhythm_app.command("lifecycle")
def rhythm_lifecycle(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show rhythm lifecycle overview."""
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.rhythm import rhythm_lifecycle_impl

    root = resolve_project(manifest)

    try:
        result = rhythm_lifecycle_impl(root)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(format_output(result, as_json=json_output))
