"""
Pitch deck CLI commands.

Commands:
- pitch scaffold: Create starter pitchspec.yaml
- pitch generate: Generate pitch deck (PPTX, narrative, or all)
- pitch validate: Validate pitchspec.yaml
"""

from __future__ import annotations

from pathlib import Path

import typer

pitch_app = typer.Typer(
    help="Generate investor pitch materials from DSL.",
    no_args_is_help=True,
)


@pitch_app.command("scaffold")
def pitch_scaffold(
    project_dir: Path = typer.Option(".", "--project", "-p", help="Project directory"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing pitchspec.yaml"),
) -> None:
    """Create starter pitchspec.yaml with DSL-extracted defaults."""
    from dazzle.pitch.loader import scaffold_pitchspec

    project_dir = project_dir.resolve()

    result = scaffold_pitchspec(project_dir, overwrite=overwrite)
    if result:
        typer.echo(f"Created {result}")
        typer.echo("Edit pitchspec.yaml then run: dazzle pitch generate")
    else:
        typer.echo("pitchspec.yaml already exists. Use --overwrite to replace.")


@pitch_app.command("generate")
def pitch_generate(
    project_dir: Path = typer.Option(".", "--project", "-p", help="Project directory"),
    format: str = typer.Option(
        "pptx", "--format", "-f", help="Output format: pptx, narrative, or all"
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file path"),
) -> None:
    """Generate pitch deck from pitchspec.yaml."""
    from dazzle.pitch.extractor import extract_pitch_context
    from dazzle.pitch.loader import PitchSpecError, load_pitchspec

    project_dir = project_dir.resolve()

    try:
        spec = load_pitchspec(project_dir)
    except PitchSpecError as e:
        typer.echo(f"Error: {e}", err=True)
        typer.echo("Run 'dazzle pitch scaffold' to create pitchspec.yaml")
        raise typer.Exit(1)

    ctx = extract_pitch_context(project_dir, spec)
    ctx.project_root = project_dir

    formats = ["pptx", "narrative"] if format == "all" else [format]

    for fmt in formats:
        if fmt == "pptx":
            from dazzle.pitch.generators.pptx_gen import generate_pptx

            out_path = output or (project_dir / "pitch_deck.pptx")
            result = generate_pptx(ctx, out_path)
            if result.success:
                typer.echo(f"Generated PPTX: {result.output_path} ({result.slide_count} slides)")
                if result.warnings:
                    typer.echo(f"Warnings ({len(result.warnings)}):")
                    for w in result.warnings:
                        typer.echo(f"  ⚠ {w}")
            else:
                typer.echo(f"Error: {result.error}", err=True)
                raise typer.Exit(1)

        elif fmt == "narrative":
            from dazzle.pitch.generators.narrative import generate_narrative

            out_path = output or (project_dir / "pitch_narrative.md")
            result = generate_narrative(ctx, out_path)
            if result.success:
                typer.echo(f"Generated narrative: {result.output_path}")
                if len(result.files_created) > 1:
                    typer.echo(f"  + {len(result.files_created) - 1} chart(s)")
            else:
                typer.echo(f"Error: {result.error}", err=True)
                raise typer.Exit(1)

        else:
            typer.echo(f"Unknown format: {fmt}", err=True)
            raise typer.Exit(1)


@pitch_app.command("validate")
def pitch_validate(
    project_dir: Path = typer.Option(".", "--project", "-p", help="Project directory"),
) -> None:
    """Validate pitchspec.yaml."""
    from dazzle.pitch.loader import PitchSpecError, load_pitchspec, validate_pitchspec

    project_dir = project_dir.resolve()

    try:
        spec = load_pitchspec(project_dir)
    except PitchSpecError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    result = validate_pitchspec(spec)

    if result.errors:
        typer.echo(f"Errors ({len(result.errors)}):")
        for err in result.errors:
            typer.echo(f"  ✗ {err}")

    if result.warnings:
        typer.echo(f"Warnings ({len(result.warnings)}):")
        for warn in result.warnings:
            typer.echo(f"  ⚠ {warn}")

    if result.is_valid:
        typer.echo("PitchSpec is valid.")
    else:
        typer.echo("PitchSpec has errors.")
        raise typer.Exit(1)
