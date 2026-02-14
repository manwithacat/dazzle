"""
Discovery CLI commands.

Commands:
- discovery coherence: Run persona-by-persona UX coherence checks
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

discovery_app = typer.Typer(
    help="App discovery and coherence analysis.",
    no_args_is_help=True,
)


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
    from dazzle.mcp.server.handlers.discovery import app_coherence_handler

    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    if not (root / "dazzle.toml").exists():
        typer.echo(f"No dazzle.toml found in {root}", err=True)
        raise typer.Exit(code=1)

    args: dict[str, object] = {}
    if persona:
        args["persona"] = persona

    try:
        raw = app_coherence_handler(root, args)
        data = json.loads(raw)
    except Exception as e:
        typer.echo(f"Coherence analysis error: {e}", err=True)
        raise typer.Exit(code=1)

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
