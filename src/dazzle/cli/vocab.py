"""
Vocabulary management CLI commands.

Commands for managing app-local vocabulary (macros, aliases, patterns).
"""

from pathlib import Path

import typer

vocab_app = typer.Typer(help="Manage app-local vocabulary (macros, aliases, patterns)")


@vocab_app.command("list")
def vocab_list(
    path: str | None = typer.Option(
        None, "--path", "-p", help="Project directory (default: current)"
    ),
    scope: str | None = typer.Option(
        None, "--scope", "-s", help="Filter by scope (ui, data, workflow, auth, misc)"
    ),
    kind: str | None = typer.Option(
        None, "--kind", "-k", help="Filter by kind (macro, alias, pattern)"
    ),
    tag: str | None = typer.Option(None, "--tag", "-t", help="Filter by tag"),
) -> None:
    """List all vocabulary entries in the project."""
    from dazzle.core.vocab import load_manifest

    project_path = Path(path or ".")
    manifest_path = project_path / "dazzle" / "local_vocab" / "manifest.yml"

    if not manifest_path.exists():
        typer.echo("No vocabulary manifest found.", err=True)
        typer.echo(f"Expected location: {manifest_path}", err=True)
        typer.echo("\nTo create a manifest, use: dazzle vocab create", err=True)
        return

    # Load manifest
    try:
        manifest = load_manifest(manifest_path)
    except Exception as e:
        typer.echo(f"Error loading manifest: {e}", err=True)
        raise typer.Exit(code=1)

    # Filter entries
    entries = manifest.entries
    if scope:
        entries = [e for e in entries if e.scope == scope]
    if kind:
        entries = [e for e in entries if e.kind == kind]
    if tag:
        entries = [e for e in entries if tag in e.tags]

    if not entries:
        typer.echo("No vocabulary entries found matching criteria.")
        return

    # Display entries
    typer.echo(f"Vocabulary Entries ({len(entries)} total):\n")
    for entry in entries:
        stability = entry.stability
        usage = entry.usage_count

        # Format entry line
        typer.echo(f"  {entry.id:30s} [{entry.kind}] {entry.scope}")
        typer.echo(f"    {entry.description}")

        # Show metadata
        meta_parts = []
        if stability != "experimental":
            meta_parts.append(f"stability: {stability}")
        if usage > 0:
            meta_parts.append(f"used {usage}x")
        if entry.tags:
            meta_parts.append(f"tags: {', '.join(entry.tags)}")

        if meta_parts:
            typer.echo(f"    ({', '.join(meta_parts)})")

        typer.echo()


@vocab_app.command("show")
def vocab_show(
    entry_id: str = typer.Argument(..., help="Entry ID to display"),
    path: str | None = typer.Option(
        None, "--path", "-p", help="Project directory (default: current)"
    ),
    show_expansion: bool = typer.Option(
        True, "--expansion/--no-expansion", help="Show expansion body"
    ),
) -> None:
    """Show details and expansion of a vocabulary entry."""
    from dazzle.core.vocab import load_manifest

    project_path = Path(path or ".")
    manifest_path = project_path / "dazzle" / "local_vocab" / "manifest.yml"

    if not manifest_path.exists():
        typer.echo(f"No vocabulary manifest found at: {manifest_path}", err=True)
        raise typer.Exit(code=1)

    # Load manifest
    try:
        manifest = load_manifest(manifest_path)
    except Exception as e:
        typer.echo(f"Error loading manifest: {e}", err=True)
        raise typer.Exit(code=1)

    # Get entry
    entry = manifest.get_entry(entry_id)
    if not entry:
        typer.echo(f"Entry '{entry_id}' not found.", err=True)
        raise typer.Exit(code=1)

    # Display entry details
    typer.echo(f"Vocabulary Entry: {entry.id}\n")
    typer.echo(f"  Kind: {entry.kind}")
    typer.echo(f"  Scope: {entry.scope}")
    typer.echo(f"  Description: {entry.description}")
    typer.echo(f"  Core DSL Version: {entry.dsl_core_version}")

    if entry.tags:
        typer.echo(f"  Tags: {', '.join(entry.tags)}")

    typer.echo(f"  Stability: {entry.stability}")
    typer.echo(f"  Usage Count: {entry.usage_count}")

    # Parameters
    if entry.parameters:
        typer.echo("\nParameters:")
        for param in entry.parameters:
            req = " (required)" if param.required else f" (optional, default: {param.default})"
            typer.echo(f"  - {param.name}: {param.type}{req}")
            if param.description:
                typer.echo(f"      {param.description}")

    # Expansion
    if show_expansion:
        typer.echo("\nExpansion to Core DSL:")
        typer.echo("  " + "-" * 60)
        for line in entry.expansion["body"].split("\n"):
            typer.echo(f"  {line}")
        typer.echo("  " + "-" * 60)


@vocab_app.command("expand")
def vocab_expand(
    file_path: str = typer.Argument(..., help="DSL file to expand"),
    output: str | None = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
    manifest: str | None = typer.Option(None, "--manifest", "-m", help="Path to manifest.yml"),
) -> None:
    """Expand vocabulary references in a DSL file to core DSL."""
    from dazzle.core.expander import ExpansionError, VocabExpander
    from dazzle.core.vocab import load_manifest

    input_path = Path(file_path)

    if not input_path.exists():
        typer.echo(f"Input file not found: {input_path}", err=True)
        raise typer.Exit(code=1)

    # Find manifest
    if manifest:
        manifest_path = Path(manifest)
    else:
        # Look in standard location
        manifest_path = input_path.parent / "dazzle" / "local_vocab" / "manifest.yml"
        if not manifest_path.exists():
            # Try current directory
            manifest_path = Path(".") / "dazzle" / "local_vocab" / "manifest.yml"

    if not manifest_path.exists():
        typer.echo("No vocabulary manifest found.", err=True)
        typer.echo(f"Looked in: {manifest_path}", err=True)
        raise typer.Exit(code=1)

    # Load manifest and expand
    try:
        vocab_manifest = load_manifest(manifest_path)
        expander = VocabExpander(vocab_manifest)

        output_path = Path(output) if output else None
        expanded = expander.expand_file(input_path, output_path)

        if output:
            typer.echo(f"✓ Expanded file written to: {output}")
        else:
            typer.echo(expanded)

    except ExpansionError as e:
        typer.echo(f"Expansion error: {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        import traceback

        traceback.print_exc()
        raise typer.Exit(code=1)
