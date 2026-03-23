"""Dazzle compliance documentation CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

compliance_app = typer.Typer(
    help="Compliance documentation tools",
    no_args_is_help=True,
)

console = Console()


@compliance_app.command(name="compile")
def compile_cmd(
    framework: str = typer.Option("iso27001", "--framework", "-f", help="Framework ID"),
    output: str = typer.Option("", "--output", "-o", help="Output path for auditspec JSON"),
) -> None:
    """Compile compliance audit spec from DSL evidence."""
    from dazzle.compliance.coordinator import compile_full_pipeline

    project_root = Path.cwd().resolve()
    auditspec = compile_full_pipeline(project_root, framework=framework)
    s = auditspec.summary

    # Write outputs
    out_dir = project_root / ".dazzle" / "compliance" / "output" / framework
    out_dir.mkdir(parents=True, exist_ok=True)
    auditspec_path = out_dir / "auditspec.json"
    auditspec_path.write_text(json.dumps(auditspec.model_dump(), indent=2))

    if output:
        Path(output).write_text(json.dumps(auditspec.model_dump(), indent=2))

    # Display summary
    console.print(f"\n[bold]Compliance: {auditspec.framework_name}[/bold]")
    console.print(f"  Controls: {s.total_controls}")
    console.print(f"  Evidenced: {s.evidenced}")
    console.print(f"  Partial: {s.partial}")
    console.print(f"  Gaps: {s.gaps}")
    console.print(f"  Excluded: {s.excluded}")
    if s.total_controls > 0:
        coverage = (s.evidenced + s.partial) / s.total_controls * 100
        console.print(f"  Coverage: {coverage:.1f}%")
    console.print(f"\n  Output: {auditspec_path}")


@compliance_app.command(name="evidence")
def evidence_cmd() -> None:
    """Show DSL evidence extracted from the current project."""
    from dazzle.compliance.evidence import extract_evidence_from_project

    project_root = Path.cwd().resolve()
    evidence = extract_evidence_from_project(project_root)

    console.print("\n[bold]DSL Evidence[/bold]")
    for construct, items in sorted(evidence.items.items()):
        if items:
            console.print(f"  [green]{construct}[/green]: {len(items)} items")
        else:
            console.print(f"  [dim]{construct}[/dim]: 0 items")


@compliance_app.command(name="gaps")
def gaps_cmd(
    framework: str = typer.Option("iso27001", "--framework", "-f", help="Framework ID"),
    tier: str = typer.Option("2,3", "--tier", help="Tiers to show (comma-separated)"),
) -> None:
    """Show compliance gaps and partial controls."""
    from dazzle.compliance.coordinator import compile_full_pipeline

    project_root = Path.cwd().resolve()
    auditspec = compile_full_pipeline(project_root, framework=framework)

    tiers = {int(t.strip()) for t in tier.split(",")}
    gaps = [c for c in auditspec.controls if c.tier in tiers]

    if not gaps:
        console.print("[green]No gaps found for selected tiers.[/green]")
        return

    console.print(f"\n[bold]Compliance Gaps ({len(gaps)} controls)[/bold]")
    for g in gaps:
        status_color = "yellow" if g.status == "partial" else "red"
        console.print(
            f"  [{status_color}]{g.control_id}[/{status_color}] {g.control_name} (tier {g.tier})"
        )
        if g.gap_description:
            console.print(f"    {g.gap_description}")
