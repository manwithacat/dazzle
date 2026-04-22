"""Dazzle compliance documentation CLI commands."""

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
    framework: str = typer.Option(
        "iso27001", "--framework", "-f", help="Framework ID (iso27001 or soc2)"
    ),
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
    framework: str = typer.Option(
        "iso27001", "--framework", "-f", help="Framework ID (iso27001 or soc2)"
    ),
    tier: str = typer.Option("2,3", "--tier", help="Tiers to show (comma-separated)"),
    status: str = typer.Option(
        "gap,partial", "--status", help="Comma-separated statuses to include"
    ),
) -> None:
    """Show compliance gaps and partial controls."""
    from dazzle.compliance.coordinator import compile_full_pipeline
    from dazzle.compliance.slicer import slice_auditspec

    project_root = Path.cwd().resolve()
    auditspec = compile_full_pipeline(project_root, framework=framework)

    tiers = [int(t.strip()) for t in tier.split(",")]
    statuses = [s.strip() for s in status.split(",") if s.strip()]

    sliced = slice_auditspec(
        auditspec.model_dump(),
        status_filter=statuses,
        tier_filter=tiers,
    )
    sliced_controls = sliced["controls"]

    if not sliced_controls:
        console.print("[green]No gaps found for selected tiers/statuses.[/green]")
        return

    console.print(f"\n[bold]Compliance Gaps ({len(sliced_controls)} controls)[/bold]")
    for g in sliced_controls:
        gap_status = g["status"]
        status_color = "yellow" if gap_status == "partial" else "red"
        console.print(
            f"  [{status_color}]{g['control_id']}[/{status_color}] "
            f"{g['control_name']} (tier {g['tier']})"
        )
        if g.get("gap_description"):
            console.print(f"    {g['gap_description']}")


@compliance_app.command(name="render")
def render_cmd(
    markdown_path: Path = typer.Argument(..., help="Source markdown file"),
    output: Path = typer.Option(..., "--output", "-o", help="Output PDF path"),
    title: str = typer.Option("Compliance Document", "--title", help="Document title"),
    document_id: str = typer.Option("DOC-001", "--id", help="Document ID"),
    version: str = typer.Option("1.0", "--version", "-v", help="Document version"),
    brandspec_path: Path | None = typer.Option(
        None, "--brandspec", help="Path to brandspec.yaml (otherwise auto-detected)"
    ),
) -> None:
    """Render a markdown compliance document to branded PDF."""
    from dazzle.compliance.renderer import HAS_RENDERER_DEPS, load_brandspec, render_document

    if not HAS_RENDERER_DEPS:
        console.print(
            "[red]PDF rendering requires optional dependencies.[/red]\n"
            "Install with: [cyan]pip install 'dazzle-dsl[compliance]'[/cyan] "
            "(or: pip install weasyprint jinja2 markdown)"
        )
        raise typer.Exit(code=1)

    project_root = Path.cwd().resolve()
    brandspec = load_brandspec(path=brandspec_path, project_path=project_root)

    written = render_document(
        markdown_path=markdown_path.resolve(),
        output_path=output.resolve(),
        brandspec=brandspec,
        document_title=title,
        document_id=document_id,
        version=version,
    )
    console.print(f"[green]Rendered:[/green] {written}")


@compliance_app.command(name="validate-citations")
def validate_citations_cmd(
    markdown_path: Path = typer.Argument(..., help="Markdown document to validate"),
    framework: str = typer.Option(
        "iso27001", "--framework", "-f", help="Framework ID (iso27001 or soc2)"
    ),
) -> None:
    """Check ``DSL ref: Entity.construct`` citations in a markdown document."""
    from dazzle.compliance.citation import validate_citations
    from dazzle.compliance.coordinator import compile_full_pipeline

    project_root = Path.cwd().resolve()
    auditspec = compile_full_pipeline(project_root, framework=framework)

    text = markdown_path.read_text()
    issues = validate_citations(text, auditspec.model_dump())

    if not issues:
        console.print(f"[green]All citations in {markdown_path.name} resolve cleanly.[/green]")
        return

    console.print(f"[red]{len(issues)} unresolved citation(s):[/red]")
    for issue in issues:
        console.print(f"  {issue}")
    raise typer.Exit(code=1)
