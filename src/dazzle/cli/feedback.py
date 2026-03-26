"""CLI commands for feedback widget management."""

import asyncio
import json as json_mod

import typer
from rich.console import Console
from rich.table import Table

feedback_app = typer.Typer(help="Feedback reports — list, triage, resolve.", no_args_is_help=True)
console = Console()


@feedback_app.command("list")
def list_command(
    status: str = typer.Option("", "--status", "-s", help="Filter by status"),
    category: str = typer.Option("", "--category", "-c", help="Filter by category"),
    severity: str = typer.Option("", "--severity", help="Filter by severity"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List feedback reports."""
    from dazzle.cli.feedback_impl import feedback_list

    result = asyncio.run(
        feedback_list(
            status=status or None,
            category=category or None,
            severity=severity or None,
            limit=limit,
        )
    )

    if as_json:
        console.print(json_mod.dumps(result, indent=2))
        return

    items = result.get("items", [])
    if not items:
        console.print("[dim]No feedback reports found.[/dim]")
        return

    table = Table(title=f"Feedback Reports ({result.get('total', len(items))} total)")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Status")
    table.add_column("Category")
    table.add_column("Severity")
    table.add_column("Description", max_width=40)
    table.add_column("Reported By")

    for item in items:
        table.add_row(
            item["id"][:8],
            item.get("status", ""),
            item.get("category", ""),
            item.get("severity", ""),
            (item.get("description", "") or "")[:40],
            item.get("reported_by", ""),
        )
    console.print(table)


@feedback_app.command("get")
def get_command(
    report_id: str = typer.Argument(..., help="Feedback report ID"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Get a single feedback report."""
    from dazzle.cli.feedback_impl import feedback_get

    result = asyncio.run(feedback_get(report_id))

    if as_json:
        console.print(json_mod.dumps(result, indent=2))
        return

    for key, value in result.items():
        if value is not None:
            console.print(f"[bold]{key}:[/bold] {value}")


@feedback_app.command("triage")
def triage_command(
    report_id: str = typer.Argument(..., help="Feedback report ID"),
    notes: str = typer.Option("", "--notes", "-n", help="Agent notes"),
    assign: str = typer.Option("", "--assign", "-a", help="Assign to"),
    classify: str = typer.Option("", "--classify", help="Classification"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Triage a feedback report (new -> triaged)."""
    from dazzle.cli.feedback_impl import feedback_triage

    result = asyncio.run(
        feedback_triage(
            report_id,
            agent_notes=notes or None,
            assigned_to=assign or None,
            agent_classification=classify or None,
        )
    )

    if as_json:
        console.print(json_mod.dumps(result, indent=2))
        return

    console.print(f"[green]✓[/green] Report {report_id[:8]} triaged → status={result['status']}")


@feedback_app.command("resolve")
def resolve_command(
    report_id: str = typer.Argument(..., help="Feedback report ID"),
    notes: str = typer.Option("", "--notes", "-n", help="Resolution notes"),
    resolved_by: str = typer.Option("", "--resolved-by", help="Who resolved it"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Resolve a feedback report (triaged/in_progress -> resolved)."""
    from dazzle.cli.feedback_impl import feedback_resolve

    result = asyncio.run(
        feedback_resolve(
            report_id,
            agent_notes=notes or None,
            resolved_by=resolved_by or None,
        )
    )

    if as_json:
        console.print(json_mod.dumps(result, indent=2))
        return

    console.print(f"[green]✓[/green] Report {report_id[:8]} resolved → status={result['status']}")


@feedback_app.command("delete")
def delete_command(
    report_id: str = typer.Argument(..., help="Feedback report ID"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Delete a feedback report."""
    from dazzle.cli.feedback_impl import feedback_delete

    asyncio.run(feedback_delete(report_id))

    if as_json:
        console.print(json_mod.dumps({"deleted": report_id}))
        return

    console.print(f"[green]✓[/green] Report {report_id[:8]} deleted")


@feedback_app.command("stats")
def stats_command(
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show feedback statistics."""
    from dazzle.cli.feedback_impl import feedback_stats

    result = asyncio.run(feedback_stats())

    if as_json:
        console.print(json_mod.dumps(result, indent=2))
        return

    console.print(f"[bold]Total:[/bold] {result['total']}")
    console.print("\n[bold]By Status:[/bold]")
    for k, v in result.get("by_status", {}).items():
        console.print(f"  {k}: {v}")
    console.print("\n[bold]By Category:[/bold]")
    for k, v in result.get("by_category", {}).items():
        console.print(f"  {k}: {v}")
    console.print("\n[bold]By Severity:[/bold]")
    for k, v in result.get("by_severity", {}).items():
        console.print(f"  {k}: {v}")
