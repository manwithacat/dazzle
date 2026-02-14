"""CLI sub-app for Sentinel failure-mode detection."""

from __future__ import annotations

import json
from pathlib import Path

import typer

sentinel_app = typer.Typer(
    help="SaaS Sentinel — failure-mode detection for Dazzle applications.",
    no_args_is_help=True,
)


def _resolve_root(manifest: str) -> Path:
    root = Path(manifest).resolve().parent
    if not (root / "dazzle.toml").exists():
        typer.echo(f"No dazzle.toml found in {root}", err=True)
        raise typer.Exit(code=1)
    return root


@sentinel_app.command("scan")
def sentinel_scan(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    format_: str = typer.Option("table", "--format", "-f"),
    agent: list[str] = typer.Option([], "--agent", "-a"),
    severity: str = typer.Option("info", "--severity", "-s"),
) -> None:
    """Run a sentinel scan against the project DSL."""
    from dazzle.mcp.server.handlers.sentinel import scan_handler

    root = _resolve_root(manifest)
    args: dict[str, object] = {
        "severity_threshold": severity,
        "detail": "full",
    }
    if agent:
        args["agents"] = agent

    try:
        raw = scan_handler(root, args)
        data = json.loads(raw)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    if data.get("error"):
        typer.echo(f"Error: {data['error']}", err=True)
        raise typer.Exit(code=1)

    if format_ == "json":
        typer.echo(json.dumps(data, indent=2))
    else:
        summary = data.get("summary", {})
        total = summary.get("total_findings", 0)
        by_sev = summary.get("by_severity", {})

        typer.secho(f"\nSentinel Scan: {total} findings", bold=True)
        for sev in ("critical", "high", "medium", "low", "info"):
            count = by_sev.get(sev, 0)
            if count == 0:
                continue
            color = {
                "critical": typer.colors.RED,
                "high": typer.colors.RED,
                "medium": typer.colors.YELLOW,
                "low": typer.colors.CYAN,
                "info": typer.colors.WHITE,
            }.get(sev, typer.colors.WHITE)
            typer.secho(f"  {sev}: {count}", fg=color)

        findings = data.get("findings", [])
        for f in findings:
            sev = f.get("severity", "info")
            color = {
                "critical": typer.colors.RED,
                "high": typer.colors.RED,
                "medium": typer.colors.YELLOW,
            }.get(sev, typer.colors.WHITE)
            hid = f.get("heuristic_id", "?")
            title = f.get("title", "")
            entity = f.get("entity_name", "")
            loc = f" [{entity}]" if entity else ""
            typer.secho(f"  {hid} {title}{loc}", fg=color)

        typer.echo()

    # Exit code 1 if any critical findings
    findings = data.get("findings", [])
    if any(f.get("severity") == "critical" for f in findings):
        raise typer.Exit(code=1)


@sentinel_app.command("findings")
def sentinel_findings(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    agent: str = typer.Option(None, "--agent", "-a"),
    format_: str = typer.Option("table", "--format", "-f"),
) -> None:
    """Show findings from the latest scan."""
    from dazzle.mcp.server.handlers.sentinel import findings_handler

    root = _resolve_root(manifest)
    args: dict[str, object] = {}
    if agent:
        args["agent"] = agent

    raw = findings_handler(root, args)
    data = json.loads(raw)

    if format_ == "json":
        typer.echo(json.dumps(data, indent=2))
        return

    findings = data.get("findings", [])
    typer.secho(f"\n{len(findings)} findings", bold=True)
    for f in findings:
        hid = f.get("heuristic_id", "?")
        title = f.get("title", "")
        sev = f.get("severity", "info")
        typer.echo(f"  [{sev.upper():8s}] {hid} {title}")
    typer.echo()


@sentinel_app.command("suppress")
def sentinel_suppress(
    finding_id: str = typer.Argument(..., help="Finding ID to suppress"),
    reason: str = typer.Option(..., "--reason", "-r", help="Reason for suppression"),
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
) -> None:
    """Suppress a finding as a false positive."""
    from dazzle.mcp.server.handlers.sentinel import suppress_handler

    root = _resolve_root(manifest)
    raw = suppress_handler(root, {"finding_id": finding_id, "reason": reason})
    data = json.loads(raw)

    if data.get("error"):
        typer.echo(f"Error: {data['error']}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Suppressed: {finding_id}")


@sentinel_app.command("status")
def sentinel_status(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
) -> None:
    """Show sentinel status: available agents and last scan."""
    from dazzle.mcp.server.handlers.sentinel import status_handler

    root = _resolve_root(manifest)
    raw = status_handler(root, {})
    data = json.loads(raw)

    typer.secho("\nSentinel Status", bold=True)
    for a in data.get("agents", []):
        typer.echo(f"  Agent {a['id']}: {a['heuristics']} heuristics")

    last = data.get("last_scan")
    if last:
        typer.echo(
            f"\n  Last scan: {last.get('timestamp', '?')} ({last.get('total_findings', 0)} findings)"
        )
    else:
        typer.echo("\n  No scans yet")
    typer.echo()
