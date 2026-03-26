"""Pulse health-check and analytics CLI commands."""

import typer

pulse_app = typer.Typer(help="Project health pulse checks.", no_args_is_help=True)


@pulse_app.command("run")
def pulse_run(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    business_context: str = typer.Option(None, "--context", "-c", help="Business context"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Run full project pulse check."""
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.pulse import pulse_run_impl

    root = resolve_project(manifest)
    result = pulse_run_impl(root, business_context=business_context)
    typer.echo(format_output(result, as_json=json_output))


@pulse_app.command("radar")
def pulse_radar(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    business_context: str = typer.Option(None, "--context", "-c", help="Business context"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Generate radar chart of project health dimensions."""
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.pulse import pulse_radar_impl

    root = resolve_project(manifest)
    result = pulse_radar_impl(root, business_context=business_context)
    typer.echo(format_output(result, as_json=json_output))


@pulse_app.command("persona")
def pulse_persona(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    persona_name: str = typer.Option(..., "--persona", "-p", help="Persona name to analyze"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Analyze project health from a specific persona's perspective."""
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.pulse import pulse_persona_impl

    root = resolve_project(manifest)
    result = pulse_persona_impl(root, persona_name=persona_name)
    typer.echo(format_output(result, as_json=json_output))


@pulse_app.command("timeline")
def pulse_timeline(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    business_context: str = typer.Option(None, "--context", "-c", help="Business context"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show project health timeline."""
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.pulse import pulse_timeline_impl

    root = resolve_project(manifest)
    result = pulse_timeline_impl(root, business_context=business_context)
    typer.echo(format_output(result, as_json=json_output))


@pulse_app.command("decisions")
def pulse_decisions(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    business_context: str = typer.Option(None, "--context", "-c", help="Business context"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List pending decisions affecting project health."""
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.pulse import pulse_decisions_impl

    root = resolve_project(manifest)
    result = pulse_decisions_impl(root, business_context=business_context)
    typer.echo(format_output(result, as_json=json_output))


@pulse_app.command("wfs")
def pulse_wfs(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    persona_filter: str = typer.Option(None, "--persona", "-p", help="Filter by persona"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show workflow fitness scores."""
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.pulse import pulse_wfs_impl

    root = resolve_project(manifest)
    result = pulse_wfs_impl(root, persona_filter=persona_filter)
    typer.echo(format_output(result, as_json=json_output))
