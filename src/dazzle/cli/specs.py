"""
Specification generation commands for DAZZLE CLI.

Commands for generating API specifications from DAZZLE projects:
- specs openapi: Generate OpenAPI 3.1 specification
- specs asyncapi: Generate AsyncAPI 3.0 specification
"""

from __future__ import annotations

from pathlib import Path

import typer

from dazzle.core import ir
from dazzle.core.errors import ParseError
from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules

specs_app = typer.Typer(
    help="Generate API specifications from DAZZLE projects",
    no_args_is_help=True,
)


def _load_appspec(project_dir: Path) -> ir.AppSpec:
    """Load and build AppSpec from DSL files."""
    manifest_path = project_dir / "dazzle.toml"
    if not manifest_path.exists():
        typer.echo(f"No dazzle.toml found in {project_dir}", err=True)
        raise typer.Exit(code=1)

    try:
        manifest = load_manifest(manifest_path)
    except Exception as e:
        typer.echo(f"Error loading manifest: {e}", err=True)
        raise typer.Exit(code=1)

    dsl_files = discover_dsl_files(project_dir, manifest)
    if not dsl_files:
        typer.echo(f"No DSL files found in {project_dir}", err=True)
        raise typer.Exit(code=1)

    try:
        modules = parse_modules(dsl_files)
    except ParseError as e:
        typer.echo(f"Parse error: {e}", err=True)
        raise typer.Exit(code=1)

    try:
        spec = build_appspec(modules, manifest.project_root)
    except Exception as e:
        typer.echo(f"Error building spec: {e}", err=True)
        raise typer.Exit(code=1)

    return spec


@specs_app.command(name="openapi")
def specs_openapi(
    project_dir: Path = typer.Option(  # noqa: B008
        Path("."),
        "--project",
        "-p",
        help="Project directory (default: current directory)",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file (default: stdout)",
    ),
    format: str = typer.Option(
        "yaml",
        "--format",
        "-f",
        help="Output format (yaml or json)",
    ),
) -> None:
    """
    Generate OpenAPI specification from DAZZLE spec.

    Generates an OpenAPI 3.1 specification from your DAZZLE
    entities, including CRUD operations and state transitions.

    Examples:
        dazzle specs openapi                    # Print to stdout
        dazzle specs openapi -o openapi.yaml    # Save to file
        dazzle specs openapi -f json            # Output as JSON
    """
    from dazzle.specs import generate_openapi, openapi_to_json, openapi_to_yaml

    project_path = project_dir.resolve()
    spec = _load_appspec(project_path)
    openapi = generate_openapi(spec)

    if format.lower() == "json":
        content = openapi_to_json(openapi)
    else:
        content = openapi_to_yaml(openapi)

    if output:
        output.write_text(content)
        typer.echo(f"OpenAPI specification written to {output}")
    else:
        typer.echo(content)


@specs_app.command(name="asyncapi")
def specs_asyncapi(
    project_dir: Path = typer.Option(  # noqa: B008
        Path("."),
        "--project",
        "-p",
        help="Project directory (default: current directory)",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file (default: stdout)",
    ),
    format: str = typer.Option(
        "yaml",
        "--format",
        "-f",
        help="Output format (yaml or json)",
    ),
) -> None:
    """
    Generate AsyncAPI specification from DAZZLE spec.

    Generates an AsyncAPI 3.0 specification from your DAZZLE
    event model, including topics, events, and subscriptions.

    Examples:
        dazzle specs asyncapi                     # Print to stdout
        dazzle specs asyncapi -o asyncapi.yaml    # Save to file
        dazzle specs asyncapi -f json             # Output as JSON
    """
    from dazzle.specs import asyncapi_to_json, asyncapi_to_yaml, generate_asyncapi

    project_path = project_dir.resolve()
    spec = _load_appspec(project_path)

    if not spec.event_model and not spec.streams:
        typer.echo(
            "Warning: No event_model or HLESS streams defined in DSL. "
            "AsyncAPI will only contain entity schemas.",
            err=True,
        )

    asyncapi = generate_asyncapi(spec)

    if format.lower() == "json":
        content = asyncapi_to_json(asyncapi)
    else:
        content = asyncapi_to_yaml(asyncapi)

    if output:
        output.write_text(content)
        typer.echo(f"AsyncAPI specification written to {output}")
    else:
        typer.echo(content)


@specs_app.callback(invoke_without_command=True)
def specs_callback(ctx: typer.Context) -> None:
    """
    Generate API specifications from DAZZLE projects.

    Generate OpenAPI and AsyncAPI specifications from your DSL definitions.

    Use 'dazzle specs openapi' or 'dazzle specs asyncapi'.
    """
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
