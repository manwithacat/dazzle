"""
Vocabulary management CLI commands.

Commands for managing app-local vocabulary (macros, aliases, patterns).
"""

from pathlib import Path

import typer

vocab_app = typer.Typer(help="Manage app-local vocabulary (macros, aliases, patterns)")

EXAMPLE_MANIFEST = """\
# Local Vocabulary Manifest
# Define reusable macros, aliases, and patterns for your project.
# See: https://dazzle.dev/docs/vocabulary

version: 1.0.0
app_id: {app_id}
dsl_core_version: 1.0.0

entries:
  # Example: Standard audit timestamp fields
  - id: audit_fields
    kind: macro
    scope: data
    dsl_core_version: 1.0.0
    description: Standard audit timestamp fields (created_at, updated_at)
    parameters: []
    expansion:
      language: dazzle-core-dsl
      body: |
        created_at: datetime auto_add
        updated_at: datetime auto_update
    metadata:
      stability: stable
      source: user
      created_at: "{created_at}"
      usage_count: 0
    tags:
      - audit
      - timestamp

  # Example: Priority enum field
  - id: priority_enum
    kind: macro
    scope: data
    dsl_core_version: 1.0.0
    description: Standard priority enum field (low, medium, high)
    parameters:
      - name: default_value
        type: string
        required: false
        default: medium
        description: Default priority value
    expansion:
      language: dazzle-core-dsl
      body: "priority: enum[low,medium,high]={{{{ default_value }}}}"
    metadata:
      stability: stable
      source: user
      created_at: "{created_at}"
      usage_count: 0
    tags:
      - enum
      - priority
"""


@vocab_app.command("init")
def vocab_init(
    path: str | None = typer.Option(
        None, "--path", "-p", help="Project directory (default: current)"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing manifest"
    ),
) -> None:
    """Initialize a local vocabulary manifest with example entries."""
    from datetime import datetime, timezone

    project_path = Path(path or ".")
    vocab_dir = project_path / "dazzle" / "local_vocab"
    manifest_path = vocab_dir / "manifest.yml"

    if manifest_path.exists() and not force:
        typer.echo(f"Manifest already exists: {manifest_path}")
        typer.echo("Use --force to overwrite.")
        raise typer.Exit(code=1)

    # Try to get app_id from dazzle.toml
    app_id = "my_app"
    toml_path = project_path / "dazzle.toml"
    if toml_path.exists():
        try:
            import tomllib

            with open(toml_path, "rb") as f:
                config = tomllib.load(f)
                app_id = config.get("project", {}).get("name", app_id)
        except Exception:
            pass

    # Create directory and manifest
    vocab_dir.mkdir(parents=True, exist_ok=True)

    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    content = EXAMPLE_MANIFEST.format(app_id=app_id, created_at=created_at)

    manifest_path.write_text(content)
    typer.echo(f"✓ Created vocabulary manifest: {manifest_path}")
    typer.echo("")
    typer.echo("Example entries included:")
    typer.echo("  - audit_fields: Standard timestamp fields")
    typer.echo("  - priority_enum: Priority enum with default parameter")
    typer.echo("")
    typer.echo("Usage in DSL:")
    typer.echo("  @use audit_fields()")
    typer.echo("  @use priority_enum(default_value=high)")
    typer.echo("")
    typer.echo("Commands:")
    typer.echo("  dazzle vocab list          # List all entries")
    typer.echo("  dazzle vocab show <id>     # Show entry details")


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
        typer.echo("No local vocabulary defined (this is optional).")
        typer.echo("")
        typer.echo("Local vocabulary lets you define reusable macros and patterns")
        typer.echo("for your project. Most projects don't need this.")
        typer.echo("")
        typer.echo(f"To create one: dazzle vocab init")
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
