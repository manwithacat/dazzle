"""
Discovery CLI commands.

Commands:
- discovery run: Run headless discovery analysis
- discovery report: Generate discovery report
- discovery compile: Compile discovery observations into proposals
- discovery emit: Emit DSL patches from proposals
- discovery status: Show discovery session status
- discovery verify-all-stories: Verify all stories against running app
- discovery coherence: Run persona-by-persona UX coherence checks
"""

from __future__ import annotations

import json
from typing import Any

import typer

discovery_app = typer.Typer(
    help="App discovery and coherence analysis.",
    no_args_is_help=True,
)


@discovery_app.command("run")
def discovery_run(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    persona: str = typer.Option(None, "--persona", help="Persona IDs (comma-separated)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Run headless discovery analysis.

    Examples:
        dazzle discovery run
        dazzle discovery run --persona admin,user
        dazzle discovery run --json
    """
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.discovery.missions import discovery_run_headless_impl

    root = resolve_project(manifest)
    persona_ids = [p.strip() for p in persona.split(",")] if persona else None
    result = discovery_run_headless_impl(root, persona_ids=persona_ids)
    typer.echo(format_output(result, as_json=json_output))


@discovery_app.command("report")
def discovery_report(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    session_id: str = typer.Option(None, "--session-id", "-s", help="Session ID to report on"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Generate discovery report.

    Examples:
        dazzle discovery report
        dazzle discovery report --session-id abc123
        dazzle discovery report --json
    """
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.discovery.compiler import discovery_report_impl

    root = resolve_project(manifest)
    result = discovery_report_impl(root, session_id=session_id)
    typer.echo(format_output(result, as_json=json_output))


@discovery_app.command("compile")
def discovery_compile(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    session_id: str = typer.Option(None, "--session-id", "-s", help="Session ID to compile"),
    persona: str = typer.Option("user", "--persona", help="Persona to compile for"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Compile discovery observations into proposals.

    Examples:
        dazzle discovery compile
        dazzle discovery compile --persona admin
        dazzle discovery compile --session-id abc123
    """
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.discovery.compiler import discovery_compile_impl

    root = resolve_project(manifest)
    result = discovery_compile_impl(root, session_id=session_id, persona=persona)
    typer.echo(format_output(result, as_json=json_output))


@discovery_app.command("emit")
def discovery_emit(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    session_id: str = typer.Option(None, "--session-id", "-s", help="Session ID to emit from"),
    persona: str = typer.Option("user", "--persona", help="Persona to emit for"),
    proposal_ids: str = typer.Option(None, "--proposal-ids", help="Proposal IDs (comma-separated)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Emit DSL patches from compiled proposals.

    Examples:
        dazzle discovery emit
        dazzle discovery emit --persona admin
        dazzle discovery emit --proposal-ids p1,p2
    """
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.discovery.emitter import discovery_emit_impl

    root = resolve_project(manifest)
    ids = [p.strip() for p in proposal_ids.split(",")] if proposal_ids else None
    result = discovery_emit_impl(root, session_id=session_id, persona=persona, proposal_ids=ids)
    typer.echo(format_output(result, as_json=json_output))


@discovery_app.command("status")
def discovery_status(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show discovery session status.

    Examples:
        dazzle discovery status
        dazzle discovery status --json
    """
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.discovery.status import discovery_status_impl

    root = resolve_project(manifest)
    result = discovery_status_impl(root)
    typer.echo(format_output(result, as_json=json_output))


@discovery_app.command("verify-all-stories")
def discovery_verify_all_stories(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    base_url: str = typer.Option(None, "--base-url", help="Base URL of running app"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Verify all stories against a running app.

    Examples:
        dazzle discovery verify-all-stories
        dazzle discovery verify-all-stories --base-url http://localhost:3000
        dazzle discovery verify-all-stories --json
    """
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.discovery.status import discovery_verify_all_stories_impl

    root = resolve_project(manifest)
    result = discovery_verify_all_stories_impl(root, base_url=base_url)
    typer.echo(format_output(result, as_json=json_output))


@discovery_app.command("coherence")
def discovery_coherence(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    persona: str = typer.Option(
        None,
        "--persona",
        help="Persona ID to check (default: all personas)",
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format: table (default) or json",
    ),
) -> None:
    """Run persona-by-persona UX coherence checks.

    Synthesizes headless discovery gaps into named checks with a coherence
    score per persona.

    Examples:
        dazzle discovery coherence                       # Table output
        dazzle discovery coherence --format json         # JSON for CI
        dazzle discovery coherence --persona admin       # Single persona
    """
    from dazzle.cli.common import resolve_project, run_mcp_handler
    from dazzle.mcp.server.handlers.discovery import app_coherence_handler

    root = resolve_project(manifest)
    args: dict[str, object] = {}
    if persona:
        args["persona"] = persona

    data = run_mcp_handler(
        root,
        "discovery",
        "coherence",
        app_coherence_handler,
        args,
        error_label="Coherence analysis",
    )

    if "error" in data:
        typer.echo(f"Error: {data['error']}", err=True)
        raise typer.Exit(code=1)

    if format == "json":
        typer.echo(json.dumps(data, indent=2))
    else:
        _print_coherence_table(data)

    # Exit 1 if overall score < 70
    if data.get("overall_score", 100) < 70:
        raise typer.Exit(code=1)


def _print_coherence_table(data: dict[str, Any]) -> None:
    """Render human-readable coherence summary."""
    overall = data.get("overall_score", 100)
    personas = data.get("personas", [])

    color = typer.colors.GREEN if overall >= 70 else typer.colors.RED
    typer.secho(f"App Coherence  (score: {overall}/100)", bold=True, fg=color)
    typer.echo("=" * 40)

    if not personas:
        typer.echo("No personas to evaluate.")
        return

    for p in personas:
        pid = p.get("persona", "?")
        score = p.get("coherence_score", "?")
        gap_count = p.get("gap_count", 0)
        checks = p.get("checks", [])

        sc = typer.colors.GREEN if (isinstance(score, int) and score >= 70) else typer.colors.RED
        typer.secho(f"\n  {pid} (score: {score}/100, {gap_count} gaps)", fg=sc, bold=True)

        for check in checks:
            name = check.get("check", "?")
            status = check.get("status", "?")
            if status == "pass":
                mark = typer.style("\u2713", fg=typer.colors.GREEN)
            elif status == "fail":
                mark = typer.style("\u2717", fg=typer.colors.RED)
            elif status == "warn":
                mark = typer.style("!", fg=typer.colors.YELLOW)
            else:
                mark = typer.style("~", fg=typer.colors.CYAN)

            line = f"    {mark} {name}"
            detail = check.get("detail")
            if detail and status != "pass":
                line += f"  \u2192 {detail}"
            typer.echo(line)

    typer.echo()
    typer.secho(f"Overall: {overall}/100", bold=True, fg=color)
    skipped = data.get("skipped_personas", [])
    if skipped:
        typer.echo(f"  Skipped: {', '.join(skipped)}")
