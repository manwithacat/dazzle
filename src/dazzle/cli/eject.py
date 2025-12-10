"""
Ejection commands for DAZZLE CLI.

Commands for generating standalone code from DAZZLE specifications:
- eject: Generate standalone application code
- eject status: Check ejection configuration
- eject adapters: List available adapters
"""

from __future__ import annotations

from pathlib import Path

import typer

from dazzle.core.errors import ParseError
from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules

eject_app = typer.Typer(
    help="Generate standalone code from DAZZLE specifications",
    no_args_is_help=True,
)


def _load_appspec(project_dir: Path):
    """Load and build AppSpec from DSL files."""
    # Find DSL files
    dsl_files = discover_dsl_files(project_dir)
    if not dsl_files:
        typer.echo(f"No DSL files found in {project_dir}", err=True)
        raise typer.Exit(code=1)

    # Parse modules
    try:
        modules = parse_modules(dsl_files)
    except ParseError as e:
        typer.echo(f"Parse error: {e}", err=True)
        raise typer.Exit(code=1)

    # Build AppSpec
    try:
        spec = build_appspec(modules)
    except Exception as e:
        typer.echo(f"Error building spec: {e}", err=True)
        raise typer.Exit(code=1)

    return spec


@eject_app.command(name="run")
def eject_run(
    project_dir: Path = typer.Option(  # noqa: B008
        Path("."),
        "--project",
        "-p",
        help="Project directory (default: current directory)",
    ),
    backend: bool = typer.Option(
        True,
        "--backend/--no-backend",
        help="Generate backend code",
    ),
    frontend: bool = typer.Option(
        True,
        "--frontend/--no-frontend",
        help="Generate frontend code",
    ),
    testing: bool = typer.Option(
        True,
        "--testing/--no-testing",
        help="Generate test code",
    ),
    ci: bool = typer.Option(
        True,
        "--ci/--no-ci",
        help="Generate CI configuration",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory (overrides dazzle.toml config)",
    ),
    clean: bool = typer.Option(
        True,
        "--clean/--no-clean",
        help="Clean output directory before generating",
    ),
    verify: bool = typer.Option(
        True,
        "--verify/--no-verify",
        help="Verify ejected code is independent from Dazzle",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Preview what would be generated without writing files",
    ),
) -> None:
    """
    Generate standalone application code.

    Ejects your DAZZLE specification into a standalone application with:
    - Backend: FastAPI with SQLAlchemy models
    - Frontend: React with TypeScript and TanStack Query
    - Testing: Schemathesis contract tests and pytest unit tests
    - CI: GitHub Actions or GitLab CI workflows

    Configuration is read from [ejection] section of dazzle.toml.

    Examples:
        dazzle eject run                    # Full ejection
        dazzle eject run --no-frontend      # Backend only
        dazzle eject run --dry-run          # Preview changes
        dazzle eject run -o ./generated     # Custom output directory
        dazzle eject run --no-verify        # Skip verification
    """
    from dazzle.eject import EjectionRunner, load_ejection_config

    project_path = project_dir.resolve()

    # Check for dazzle.toml
    toml_path = project_path / "dazzle.toml"
    if not toml_path.exists():
        typer.echo(f"Error: No dazzle.toml found in {project_path}", err=True)
        typer.echo("Run 'dazzle init' to create a new project.", err=True)
        raise typer.Exit(code=1)

    # Load config
    config = load_ejection_config(toml_path)

    # Check if ejection is enabled
    if not config.enabled:
        typer.echo("Warning: Ejection not enabled in dazzle.toml", err=True)
        typer.echo("Add [ejection] section with enabled = true to enable ejection.", err=True)
        typer.echo("")
        typer.echo("Example dazzle.toml:")
        typer.echo("  [ejection]")
        typer.echo("  enabled = true")
        typer.echo("")
        typer.echo("  [ejection.backend]")
        typer.echo('  framework = "fastapi"')
        typer.echo("")
        raise typer.Exit(code=1)

    # Override output directory if specified
    if output:
        config.output.directory = str(output)

    # Load AppSpec
    typer.echo(f"Loading specification from {project_path}...")
    spec = _load_appspec(project_path)

    typer.echo(f"Specification loaded: {spec.name}")
    typer.echo(f"  Entities: {len(spec.entities)}")
    typer.echo(f"  Surfaces: {len(spec.surfaces)}")
    typer.echo("")

    # Create runner
    runner = EjectionRunner(spec, project_path, config)

    # Dry run mode
    if dry_run:
        typer.echo("Dry run mode - previewing what would be generated:")
        typer.echo("")
        typer.echo(f"Output directory: {runner.output_dir}")
        typer.echo("")
        typer.echo("Components to generate:")
        if backend:
            typer.echo(f"  Backend: {config.backend.framework.value}")
        if frontend:
            typer.echo(f"  Frontend: {config.frontend.framework.value}")
        if testing:
            typer.echo(f"  Testing: {config.testing.contract.value}, {config.testing.unit.value}")
        if ci:
            typer.echo(f"  CI: {config.ci.template.value}")
        typer.echo("")
        typer.echo("No files were written (dry run mode)")
        return

    # Run ejection
    typer.echo("Generating code...")
    typer.echo("")

    result = runner.run(
        backend=backend,
        frontend=frontend,
        testing=testing,
        ci=ci,
        clean=clean,
        verify=verify,
    )

    # Report results
    if result.success:
        typer.echo(typer.style("✓ Ejection successful!", fg=typer.colors.GREEN, bold=True))
        typer.echo("")
        typer.echo(f"Generated {len(result.files)} files to {runner.output_dir}")

        # Report verification status
        if verify:
            if result.verified:
                typer.echo(typer.style("✓ Verification passed", fg=typer.colors.GREEN))
            else:
                typer.echo(typer.style("✗ Verification failed", fg=typer.colors.RED))
        typer.echo("")

        # Group files by directory
        by_dir: dict[str, list[str]] = {}
        for path in sorted(result.files.keys()):
            rel_path = path.relative_to(runner.output_dir)
            parts = rel_path.parts
            if len(parts) > 1:
                dir_name = parts[0]
            else:
                dir_name = "."
            if dir_name not in by_dir:
                by_dir[dir_name] = []
            by_dir[dir_name].append(str(rel_path))

        for dir_name in sorted(by_dir.keys()):
            typer.echo(f"  {dir_name}/")
            for file_path in by_dir[dir_name][:5]:  # Show first 5 files per dir
                typer.echo(f"    {file_path}")
            remaining = len(by_dir[dir_name]) - 5
            if remaining > 0:
                typer.echo(f"    ... and {remaining} more files")

        typer.echo("")
        typer.echo("Next steps:")
        typer.echo(f"  cd {runner.output_dir}")
        typer.echo("  docker compose -f docker-compose.dev.yml up")
    else:
        typer.echo(typer.style("✗ Ejection failed!", fg=typer.colors.RED, bold=True), err=True)
        typer.echo("", err=True)
        for error in result.errors:
            typer.echo(f"  Error: {error}", err=True)
        raise typer.Exit(code=1)

    # Report warnings
    if result.warnings:
        typer.echo("")
        typer.echo("Warnings:")
        for warning in result.warnings:
            typer.echo(f"  Warning: {warning}")


@eject_app.command(name="status")
def eject_status(
    project_dir: Path = typer.Option(  # noqa: B008
        Path("."),
        "--project",
        "-p",
        help="Project directory (default: current directory)",
    ),
) -> None:
    """
    Check ejection configuration status.

    Shows the current ejection configuration from dazzle.toml
    and validates that required adapters are available.
    """
    from dazzle.eject import load_ejection_config
    from dazzle.eject.adapters import AdapterRegistry

    project_path = project_dir.resolve()
    toml_path = project_path / "dazzle.toml"

    typer.echo("Ejection Configuration Status")
    typer.echo("=" * 50)
    typer.echo("")

    # Check dazzle.toml
    if not toml_path.exists():
        typer.echo(f"Error: No dazzle.toml found in {project_path}", err=True)
        raise typer.Exit(code=1)

    # Load config
    config = load_ejection_config(toml_path)

    # General status
    typer.echo(f"Project: {project_path}")
    typer.echo(f"Config:  {toml_path}")
    typer.echo("")

    # Ejection enabled
    if config.enabled:
        typer.echo(typer.style("Ejection: Enabled", fg=typer.colors.GREEN))
    else:
        typer.echo(typer.style("Ejection: Disabled", fg=typer.colors.YELLOW))
        typer.echo("  Add [ejection] enabled = true to dazzle.toml to enable")
    typer.echo("")

    # DNR reuse
    if config.reuse_dnr:
        typer.echo("DNR Reuse: Enabled (import DNR components in generated code)")
    else:
        typer.echo("DNR Reuse: Disabled (generate standalone code)")
    typer.echo("")

    # Backend config
    typer.echo("Backend Configuration:")
    typer.echo(f"  Framework: {config.backend.framework.value}")
    typer.echo(f"  Models:    {config.backend.models.value}")
    typer.echo(f"  Async:     {config.backend.async_handlers}")
    typer.echo(f"  Routing:   {config.backend.routing.value}")

    # Check adapter availability
    backend_adapter = AdapterRegistry.get_backend(config.backend.framework.value)
    if backend_adapter:
        typer.echo(typer.style("  Adapter:   ✓ Available", fg=typer.colors.GREEN))
    else:
        typer.echo(typer.style("  Adapter:   ✗ Not found", fg=typer.colors.RED))
    typer.echo("")

    # Frontend config
    typer.echo("Frontend Configuration:")
    typer.echo(f"  Framework:  {config.frontend.framework.value}")
    typer.echo(f"  API Client: {config.frontend.api_client.value}")
    typer.echo(f"  State:      {config.frontend.state.value}")

    frontend_adapter = AdapterRegistry.get_frontend(config.frontend.framework.value)
    if frontend_adapter:
        typer.echo(typer.style("  Adapter:    ✓ Available", fg=typer.colors.GREEN))
    else:
        typer.echo(typer.style("  Adapter:    ✗ Not found", fg=typer.colors.RED))
    typer.echo("")

    # Testing config
    typer.echo("Testing Configuration:")
    typer.echo(f"  Contract: {config.testing.contract.value}")
    typer.echo(f"  Unit:     {config.testing.unit.value}")
    typer.echo(f"  E2E:      {config.testing.e2e.value}")
    typer.echo("")

    # CI config
    typer.echo("CI Configuration:")
    typer.echo(f"  Template: {config.ci.template.value}")
    typer.echo("")

    # Output config
    typer.echo("Output Configuration:")
    output_path = config.get_output_path(project_path)
    typer.echo(f"  Directory: {output_path}")
    typer.echo(f"  Clean:     {config.output.clean}")

    if output_path.exists():
        files = list(output_path.rglob("*"))
        file_count = sum(1 for f in files if f.is_file())
        typer.echo(f"  Existing:  {file_count} files")
    else:
        typer.echo("  Existing:  (not created yet)")


@eject_app.command(name="adapters")
def eject_adapters() -> None:
    """
    List available ejection adapters.

    Shows all registered adapters for backend, frontend,
    testing, and CI generation.
    """
    from dazzle.eject.adapters import AdapterRegistry

    typer.echo("Available Ejection Adapters")
    typer.echo("=" * 50)
    typer.echo("")

    # Backend adapters
    backends = AdapterRegistry.list_backends()
    typer.echo(f"Backend Adapters ({len(backends)}):")
    if backends:
        for name in sorted(backends):
            typer.echo(f"  • {name}")
    else:
        typer.echo("  (none registered)")
    typer.echo("")

    # Frontend adapters
    frontends = AdapterRegistry.list_frontends()
    typer.echo(f"Frontend Adapters ({len(frontends)}):")
    if frontends:
        for name in sorted(frontends):
            typer.echo(f"  • {name}")
    else:
        typer.echo("  (none registered)")
    typer.echo("")

    # Testing adapters
    testing = AdapterRegistry.list_testing()
    typer.echo(f"Testing Adapters ({len(testing)}):")
    if testing:
        for name in sorted(testing):
            typer.echo(f"  • {name}")
    else:
        typer.echo("  (none registered)")
    typer.echo("")

    # CI adapters
    ci = AdapterRegistry.list_ci()
    typer.echo(f"CI Adapters ({len(ci)}):")
    if ci:
        for name in sorted(ci):
            typer.echo(f"  • {name}")
    else:
        typer.echo("  (none registered)")
    typer.echo("")

    typer.echo("To add custom adapters, see the adapter extension guide.")


@eject_app.command(name="openapi")
def eject_openapi(
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
        dazzle eject openapi                    # Print to stdout
        dazzle eject openapi -o openapi.yaml    # Save to file
        dazzle eject openapi -f json            # Output as JSON
    """
    from dazzle.eject import generate_openapi, openapi_to_json, openapi_to_yaml

    project_path = project_dir.resolve()

    # Load AppSpec
    spec = _load_appspec(project_path)

    # Generate OpenAPI
    openapi = generate_openapi(spec)

    # Format output
    if format.lower() == "json":
        content = openapi_to_json(openapi)
    else:
        content = openapi_to_yaml(openapi)

    # Write output
    if output:
        output.write_text(content)
        typer.echo(f"OpenAPI specification written to {output}")
    else:
        typer.echo(content)


@eject_app.command(name="verify")
def eject_verify(
    output_dir: Path = typer.Argument(  # noqa: B008
        ...,
        help="Directory containing ejected code to verify",
    ),
) -> None:
    """
    Verify ejected code is independent from Dazzle.

    Scans all generated files for:
    - Forbidden Dazzle imports (from dazzle, @dazzle/*)
    - Runtime DSL/AppSpec loaders
    - Template merge markers

    Examples:
        dazzle eject verify ./generated
    """
    import re

    from dazzle.eject.runner import (
        FORBIDDEN_JS_IMPORTS,
        FORBIDDEN_PYTHON_IMPORTS,
        FORBIDDEN_RUNTIME_LOADERS,
        FORBIDDEN_TEMPLATE_MARKERS,
        VerificationResult,
    )

    output_path = output_dir.resolve()

    if not output_path.exists():
        typer.echo(f"Error: Directory does not exist: {output_path}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Verifying ejected code in {output_path}...")
    typer.echo("")

    result = VerificationResult()

    # Scan Python files
    py_files = list(output_path.rglob("*.py"))
    typer.echo(f"Scanning {len(py_files)} Python files...")

    for py_file in py_files:
        try:
            content = py_file.read_text()
        except Exception:
            continue

        rel_path = py_file.relative_to(output_path)

        for pattern in FORBIDDEN_PYTHON_IMPORTS:
            for match in re.finditer(pattern, content, re.MULTILINE):
                line_num = content[: match.start()].count("\n") + 1
                result.add_error(
                    f"{rel_path}:{line_num}: Forbidden import: {match.group().strip()}"
                )

        for pattern in FORBIDDEN_RUNTIME_LOADERS:
            for match in re.finditer(pattern, content):
                line_num = content[: match.start()].count("\n") + 1
                result.add_error(f"{rel_path}:{line_num}: Runtime loader: {match.group()}")

    # Scan JS/TS files
    js_files = []
    for pattern in ["*.js", "*.ts", "*.tsx", "*.jsx"]:
        js_files.extend(output_path.rglob(pattern))
    typer.echo(f"Scanning {len(js_files)} JavaScript/TypeScript files...")

    for js_file in js_files:
        try:
            content = js_file.read_text()
        except Exception:
            continue

        rel_path = js_file.relative_to(output_path)

        for pattern in FORBIDDEN_JS_IMPORTS:
            for match in re.finditer(pattern, content):
                line_num = content[: match.start()].count("\n") + 1
                result.add_error(
                    f"{rel_path}:{line_num}: Forbidden import: {match.group().strip()}"
                )

    # Scan for template markers
    all_files = []
    for pattern in ["*.py", "*.js", "*.ts", "*.tsx", "*.jsx", "*.html", "*.yaml", "*.yml"]:
        all_files.extend(output_path.rglob(pattern))

    for file in all_files:
        try:
            content = file.read_text()
        except Exception:
            continue

        rel_path = file.relative_to(output_path)

        for pattern in FORBIDDEN_TEMPLATE_MARKERS:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[: match.start()].count("\n") + 1
                result.add_error(f"{rel_path}:{line_num}: Template marker: {match.group()}")

    typer.echo("")

    if result.verified:
        typer.echo(typer.style("✓ Verification passed!", fg=typer.colors.GREEN, bold=True))
        typer.echo("")
        typer.echo("The ejected code is independent from Dazzle:")
        typer.echo("  • No Dazzle imports found")
        typer.echo("  • No runtime DSL/AppSpec loaders")
        typer.echo("  • No template merge markers")
    else:
        typer.echo(typer.style("✗ Verification failed!", fg=typer.colors.RED, bold=True), err=True)
        typer.echo("", err=True)
        typer.echo(f"Found {len(result.errors)} violations:", err=True)
        for error in result.errors:
            typer.echo(f"  {error}", err=True)
        raise typer.Exit(code=1)


@eject_app.callback(invoke_without_command=True)
def eject_callback(ctx: typer.Context) -> None:
    """
    Generate standalone code from DAZZLE specifications.

    The eject command provides a path from DAZZLE's native runtime (DNR)
    to standalone, generated code when your project needs:
    - Custom deployment requirements
    - Performance optimization
    - Independence from DAZZLE runtime
    - Advanced customization

    Use 'dazzle eject run' to generate code.
    """
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
