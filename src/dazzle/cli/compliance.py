"""CLI commands for compliance compiler."""

from __future__ import annotations

import json
from pathlib import Path

import typer

compliance_app = typer.Typer(help="Compliance documentation compiler")


@compliance_app.command("compile")
def compile_cmd(
    framework: str = typer.Option("iso27001", help="Compliance framework ID"),
    project_path: str | None = typer.Option(None, help="Project path (default: current dir)"),
    output: str | None = typer.Option(None, "-o", help="Output file for AuditSpec JSON"),
):
    """Compile AuditSpec from DSL evidence against a compliance framework."""
    from dazzle.compliance.coordinator import compile_full_pipeline, write_outputs

    pp = Path(project_path) if project_path else Path.cwd()
    typer.echo(f"Compiling {framework} AuditSpec from {pp}...")

    auditspec = compile_full_pipeline(pp, framework=framework)
    output_dir = write_outputs(pp, auditspec, framework=framework)

    s = auditspec["summary"]
    typer.echo(
        f"  {s['total_controls']} controls: {s['evidenced']} evidenced, {s['partial']} partial, {s['gaps']} gaps"
    )
    typer.echo(f"  Coverage: {(s['evidenced'] + s['partial']) / s['total_controls'] * 100:.1f}%")
    typer.echo(f"  Output: {output_dir}")

    if output:
        Path(output).write_text(json.dumps(auditspec, indent=2))
        typer.echo(f"  AuditSpec written to {output}")


@compliance_app.command("evidence")
def evidence_cmd(
    project_path: str | None = typer.Option(None, help="Project path"),
):
    """Show DSL evidence summary for compliance assessment."""
    from dazzle.compliance.evidence import extract_all_evidence

    pp = Path(project_path) if project_path else Path.cwd()
    evidence = extract_all_evidence(pp)

    typer.echo("DSL Evidence Summary:")
    for construct, data in sorted(evidence.items()):
        count = len(data) if isinstance(data, (list, dict)) else 0
        typer.echo(f"  {construct:<15} {count:>5} items")


@compliance_app.command("gaps")
def gaps_cmd(
    framework: str = typer.Option("iso27001", help="Compliance framework ID"),
    project_path: str | None = typer.Option(None, help="Project path"),
):
    """List compliance control gaps."""
    from dazzle.compliance.coordinator import compile_full_pipeline

    pp = Path(project_path) if project_path else Path.cwd()
    auditspec = compile_full_pipeline(pp, framework=framework)

    for control in auditspec["controls"]:
        if control["status"] in ("gap", "partial"):
            status_icon = "●" if control["status"] == "gap" else "◐"
            typer.echo(f"  {status_icon} {control['id']} {control['name']}")
            for gap in control["gaps"]:
                typer.echo(f"      tier {gap['tier']}: {gap['description']}")
