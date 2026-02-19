"""
Composition CLI commands.

Commands:
- composition audit: Run deterministic composition audit
- composition report: Combined audit + visual evaluation
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

composition_app = typer.Typer(
    help="Visual composition analysis for Dazzle apps.",
    no_args_is_help=True,
)


@composition_app.command("audit")
def composition_audit(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    pages: str = typer.Option(
        None,
        "--pages",
        help="Comma-separated page routes to audit (default: all)",
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format: table (default) or json",
    ),
) -> None:
    """Run deterministic composition audit from sitespec structure.

    Derives section elements from SiteSpec, computes attention weights,
    and evaluates composition rules.

    Examples:
        dazzle composition audit                       # Table output
        dazzle composition audit --format json         # JSON for CI
        dazzle composition audit --pages /,/tasks      # Specific pages
    """
    from dazzle.cli.common import resolve_project, run_mcp_handler
    from dazzle.mcp.server.handlers.composition import audit_composition_handler

    root = resolve_project(manifest)
    args: dict[str, object] = {}
    if pages:
        args["pages"] = [p.strip() for p in pages.split(",")]

    data = run_mcp_handler(
        root,
        "composition",
        "audit",
        audit_composition_handler,
        args,
        error_label="Composition audit",
    )

    if "error" in data:
        typer.echo(f"Error: {data['error']}", err=True)
        raise typer.Exit(code=1)

    if format == "json":
        typer.echo(json.dumps(data, indent=2))
    else:
        _print_audit_table(data)

    # Exit 1 if score < 70
    if data.get("overall_score", 100) < 70:
        raise typer.Exit(code=1)


@composition_app.command("report")
def composition_report(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    base_url: str = typer.Option(
        None,
        "--base-url",
        help="Base URL of running server (enables visual evaluation)",
    ),
    pages: str = typer.Option(
        None,
        "--pages",
        help="Comma-separated page routes to audit (default: all)",
    ),
    viewports: str = typer.Option(
        None,
        "--viewports",
        help="Comma-separated viewports (e.g. 1280x720,375x812)",
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format: table (default) or json",
    ),
) -> None:
    """Run combined composition report: audit + optional visual evaluation.

    Always runs the deterministic DOM audit. When --base-url is provided,
    also runs Playwright capture and LLM visual evaluation.

    Examples:
        dazzle composition report                             # DOM-only
        dazzle composition report --base-url http://localhost:8000  # Full
        dazzle composition report --format json               # JSON for CI
    """
    import asyncio

    from dazzle.mcp.server.handlers.composition import report_composition_handler

    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    if not (root / "dazzle.toml").exists():
        typer.echo(f"No dazzle.toml found in {root}", err=True)
        raise typer.Exit(code=1)

    args: dict[str, object] = {}
    if base_url:
        args["base_url"] = base_url
    if pages:
        args["pages"] = [p.strip() for p in pages.split(",")]
    if viewports:
        args["viewports"] = [v.strip() for v in viewports.split(",")]

    try:
        from dazzle.cli.activity import cli_activity

        with cli_activity(root, "composition", "report") as progress:
            args["_progress"] = progress
            raw = asyncio.run(report_composition_handler(root, args))
        data = json.loads(raw)
    except Exception as e:
        typer.echo(f"Composition report error: {e}", err=True)
        raise typer.Exit(code=1)

    if "error" in data:
        typer.echo(f"Error: {data['error']}", err=True)
        raise typer.Exit(code=1)

    if format == "json":
        typer.echo(json.dumps(data, indent=2))
    else:
        _print_report_table(data)

    # Exit 1 if score < 70
    score = data.get("combined_score", data.get("dom_score", 100))
    if score < 70:
        raise typer.Exit(code=1)


def _print_audit_table(data: dict[str, Any]) -> None:
    """Render human-readable composition audit summary."""
    score = data.get("overall_score", 100)
    pages = data.get("pages", [])

    color = typer.colors.GREEN if score >= 70 else typer.colors.RED
    typer.secho(f"Composition Audit  (score: {score}/100)", bold=True, fg=color)
    typer.echo("=" * 40)

    if not pages:
        typer.echo("No pages to audit.")
        return

    for page in pages:
        route = page.get("route", page.get("page", "?"))
        page_score = page.get("score", page.get("page_score", "?"))
        violations = page.get("violations_count", {})
        total_v = sum(violations.values()) if isinstance(violations, dict) else 0

        sc = (
            typer.colors.GREEN
            if (isinstance(page_score, int) and page_score >= 70)
            else typer.colors.RED
        )
        line = f"  {route:<30} score: {page_score}"
        if total_v:
            line += f"  ({total_v} violations)"
        typer.secho(line, fg=sc)

    typer.echo()
    typer.secho(f"Overall: {score}/100", bold=True, fg=color)


def _print_report_table(data: dict[str, Any]) -> None:
    """Render human-readable composition report summary."""
    dom_score = data.get("dom_score", "?")
    visual_score = data.get("visual_score")
    combined = data.get("combined_score", dom_score)

    color = (
        typer.colors.GREEN if (isinstance(combined, int) and combined >= 70) else typer.colors.RED
    )
    typer.secho(f"Composition Report  (combined: {combined}/100)", bold=True, fg=color)
    typer.echo("=" * 40)
    typer.echo(f"  DOM score:    {dom_score}")
    if visual_score is not None:
        typer.echo(f"  Visual score: {visual_score}")
    typer.echo(f"  Combined:     {combined}")

    summary = data.get("summary", data.get("markdown", ""))
    if isinstance(summary, str) and summary and not summary.startswith("#"):
        typer.echo()
        typer.echo(f"  {summary}")
