"""
CLI commands for stub generation.

Commands:
- stubs generate: Generate missing stubs for domain services
- stubs sync: Update headers, preserve implementations
- stubs list: Show service → stub mapping
"""

from __future__ import annotations

from pathlib import Path

import typer

from dazzle.stubs import DomainServiceSpec, ServiceField, ServiceKind, StubGenerator

stubs_app = typer.Typer(help="Manage domain service stubs")


@stubs_app.command("generate")
def generate_command(
    output_dir: str = typer.Option("services", "--output", "-o", help="Output directory for stubs"),
    language: str = typer.Option(
        "python", "--language", "-l", help="Target language (python/typescript)"
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing stubs"),
) -> None:
    """
    Generate stub files for domain services.

    Currently generates example stubs. In a future version, this will
    read domain services from DSL files automatically.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    generator = StubGenerator()

    # For now, show a demo of stub generation
    # In full implementation, we would read services from parsed DSL
    demo_service = DomainServiceSpec(
        id="calculate_overdue_penalty",
        title="Calculate penalty for overdue tasks",
        kind=ServiceKind.DOMAIN_LOGIC,
        inputs=[
            ServiceField(name="task_id", type_name="uuid", required=True),
        ],
        outputs=[
            ServiceField(name="penalty_amount", type_name="decimal"),
            ServiceField(name="reason", type_name="str"),
        ],
        guarantees=[
            "Returns 0 if task is not overdue.",
        ],
    )

    ext = ".ts" if language == "typescript" else ".py"
    stub_path = output_path / f"{demo_service.id}{ext}"

    if stub_path.exists() and not force:
        typer.echo(f"Stub exists: {stub_path}")
        typer.echo("Use --force to overwrite, or use 'stubs sync' to update headers only.")
        return

    content = generator.generate_stub(demo_service, language)
    stub_path.write_text(content)
    typer.echo(f"Generated: {stub_path}")

    # Show what was generated
    typer.echo("")
    typer.echo("Generated stub content:")
    typer.echo("-" * 60)
    for line in content.split("\n")[:30]:
        typer.echo(line)
    if len(content.split("\n")) > 30:
        typer.echo("... (truncated)")


@stubs_app.command("sync")
def sync_command(
    services_dir: str = typer.Option("services", "--dir", "-d", help="Directory containing stubs"),
) -> None:
    """
    Update stub headers while preserving implementations.

    Reads the current DSL and regenerates headers for existing stubs
    without touching the implementation code.
    """
    services_path = Path(services_dir)

    if not services_path.exists():
        typer.echo(f"Services directory not found: {services_path}", err=True)
        raise typer.Exit(code=1)

    stub_files = list(services_path.glob("*.py")) + list(services_path.glob("*.ts"))

    if not stub_files:
        typer.echo(f"No stub files found in {services_path}")
        return

    typer.echo(f"Found {len(stub_files)} stub file(s):")
    for stub_file in stub_files:
        typer.echo(f"  - {stub_file.name}")

    typer.echo("")
    typer.echo("Note: Full sync requires domain services in DSL (coming soon).")
    typer.echo("Currently, stubs are preserved as-is.")


@stubs_app.command("list")
def list_command(
    services_dir: str = typer.Option("services", "--dir", "-d", help="Directory containing stubs"),
) -> None:
    """
    Show service → stub mapping.

    Lists domain services declared in DSL and their corresponding stub files.
    """
    services_path = Path(services_dir)

    typer.echo("Domain Service Stubs")
    typer.echo("=" * 50)

    if services_path.exists():
        stub_files = list(services_path.glob("*.py")) + list(services_path.glob("*.ts"))
        if stub_files:
            for stub_file in stub_files:
                service_id = stub_file.stem
                lang = "Python" if stub_file.suffix == ".py" else "TypeScript"
                typer.echo(f"  {service_id} → {stub_file.name} ({lang})")
        else:
            typer.echo("  (no stubs found)")
    else:
        typer.echo(f"  Services directory not found: {services_path}")

    typer.echo("")
    typer.echo("Note: Use 'dazzle stubs generate' to create stubs.")
