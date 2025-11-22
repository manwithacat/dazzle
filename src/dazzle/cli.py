import sys
import os
from pathlib import Path
from typing import Optional

import typer

from dazzle.core.manifest import load_manifest
from dazzle.core.fileset import discover_dsl_files
from dazzle.core.parser import parse_modules
from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.core.init import init_project, list_examples, InitError
from dazzle.core.state import load_state, save_state, clear_state, compute_dsl_hashes
from dazzle.core.changes import detect_changes
from dazzle.core.errors import DazzleError, ParseError


def _print_human_diagnostics(errors: list[str], warnings: list[str]) -> None:
    """Print diagnostics in human-readable format."""
    if errors:
        typer.echo("Validation failed:\n", err=True)
        for err in errors:
            typer.echo(f"ERROR: {err}", err=True)

    if warnings:
        typer.echo("Validation warnings:\n", err=False)
        for warn in warnings:
            typer.echo(f"WARNING: {warn}", err=False)

    if not errors and not warnings:
        typer.echo("OK: spec is valid.")


def _print_vscode_diagnostics(errors: list[str], warnings: list[str], root: Path) -> None:
    """
    Print diagnostics in VS Code format: file:line:col: severity: message

    Since most validation errors don't have location info yet, we output
    them with a generic location. Parse errors will have specific locations.
    """
    for err in errors:
        # Try to extract file info from error message if present
        # Format: "filename.dsl:line:col: error: message"
        # For now, output generic location
        typer.echo(f"dazzle.toml:1:1: error: {err}", err=True)

    for warn in warnings:
        typer.echo(f"dazzle.toml:1:1: warning: {warn}", err=True)

    # If no errors or warnings, output success (for CLI feedback)
    if not errors and not warnings:
        typer.echo("::notice: Validation successful")


def _print_vscode_parse_error(error: ParseError, root: Path) -> None:
    """Print parse error in VS Code format with location info."""
    if error.context:
        # ParseError has file, line, column information
        file_path = error.context.file
        if file_path:
            # Make path relative to root
            try:
                rel_path = Path(file_path).relative_to(root)
            except ValueError:
                rel_path = Path(file_path)

            line = error.context.line or 1
            col = error.context.column or 1
            typer.echo(f"{rel_path}:{line}:{col}: error: {error.message}", err=True)
        else:
            typer.echo(f"::error: {error.message}", err=True)
    else:
        typer.echo(f"::error: {error.message}", err=True)

app = typer.Typer(
    help="""DAZZLE – DSL-first app generator

Command Types:
  • Project Creation: init, clone, demo
    → Create NEW directories with project structure

  • Project Operations: validate, build, lint, stacks
    → Operate in CURRENT directory (must have dazzle.toml)
""",
    no_args_is_help=True,
)


@app.command()
def init(
    path: Optional[str] = typer.Argument(None, help="Directory to create project in"),
    from_example: Optional[str] = typer.Option(
        None, "--from", "-f", help="Copy from example (e.g., 'simple_task', 'support_tickets')"
    ),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Project name (defaults to directory name)"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Project title"),
    list_examples_flag: bool = typer.Option(False, "--list", "-l", help="List available examples"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip LLM instrumentation (context files for AI assistants)"),
    no_git: bool = typer.Option(False, "--no-git", help="Skip git repository initialization"),
) -> None:
    """
    Initialize a new DAZZLE project in a NEW directory.

    ⚠ Creates a NEW directory at the specified path.

    Creates project structure with:
    - dazzle.toml manifest
    - dsl/ directory with starter module
    - README.md with getting started guide
    - .gitignore and git repository (unless --no-git)
    - LLM context files for AI assistants (unless --no-llm)

    Examples:
        dazzle init ./my-project                    # Create blank project
        dazzle init ./my-app --from simple_task     # Copy from example
        dazzle init ./my-app --from support_tickets # Multi-module example
        dazzle init --list                          # Show available examples
        dazzle init ./my-app --no-llm --no-git      # Minimal setup without LLM/git
    """
    if list_examples_flag:
        examples = list_examples()
        if not examples:
            typer.echo("No examples available.")
            return

        typer.echo("Available examples:\n")
        for example in examples:
            typer.echo(f"  {example}")
        typer.echo("\nUse: dazzle init ./my-project --from <example>")
        return

    if path is None:
        typer.echo("Error: Missing argument 'PATH'.", err=True)
        typer.echo("Use: dazzle init ./my-project", err=True)
        typer.echo("Or: dazzle init --list", err=True)
        raise typer.Exit(code=1)

    target = Path(path).resolve()

    try:
        init_project(
            target_dir=target,
            project_name=name,
            from_example=from_example,
            title=title,
            no_llm=no_llm,
            no_git=no_git,
        )

        typer.echo(f"✓ Created project: {target}")
        if not from_example:
            typer.echo("✓ Created SPEC.md template (fill out your requirements)")
        if not no_git:
            typer.echo("✓ Initialized git repository")
        if not no_llm:
            typer.echo("✓ Created LLM context files (LLM_CONTEXT.md, .llm/, .claude/, .copilot/)")
        typer.echo("\nNext steps:")
        typer.echo(f"  cd {path}")
        if not from_example:
            typer.echo("  # 1. Edit SPEC.md with your project requirements")
            typer.echo("  # 2. Work with an AI assistant to create DSL from your spec")
        typer.echo("  dazzle validate")
        typer.echo("  dazzle build  # Uses 'micro' stack by default")

    except InitError as e:
        typer.echo(f"Initialization failed: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def validate(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m", help="Path to dazzle.toml"),
    format: str = typer.Option("human", "--format", "-f", help="Output format: 'human' or 'vscode'"),
) -> None:
    """
    Parse all DSL modules, resolve dependencies, and validate the merged AppSpec.

    ⚠ Operates in CURRENT directory (must contain dazzle.toml).

    Output formats:
    - human: Human-readable output (default)
    - vscode: Machine-readable format for VS Code integration (file:line:col: severity: message)
    """
    root = Path(".").resolve()
    manifest_path = root / manifest

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)

        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)

        errors, warnings = lint_appspec(appspec)

        # Format output based on --format flag
        if format == "vscode":
            _print_vscode_diagnostics(errors, warnings, root)
        else:
            _print_human_diagnostics(errors, warnings)

        # Exit with error code if validation failed
        if errors:
            raise typer.Exit(code=1)

    except ParseError as e:
        # Parse errors have location info
        if format == "vscode":
            _print_vscode_parse_error(e, root)
        else:
            typer.echo(str(e), err=True)
        raise typer.Exit(code=1)
    except (DazzleError, Exception) as e:
        # Other errors
        if format == "vscode":
            typer.echo(f"::error: {e}", err=True)
        else:
            typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def lint(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    strict: bool = typer.Option(False, "--strict", help="Treat warnings as errors."),
) -> None:
    """
    Run extended lint rules (naming, dead modules, unused imports, etc.)

    ⚠ Operates in CURRENT directory (must contain dazzle.toml).
    """
    root = Path(".").resolve()
    manifest_path = root / manifest

    mf = load_manifest(manifest_path)
    dsl_files = discover_dsl_files(root, mf)

    modules = parse_modules(dsl_files)
    appspec = build_appspec(modules, mf.project_root)

    errors, warnings = lint_appspec(appspec, extended=True)

    if errors or (strict and warnings):
        typer.echo("Lint issues found:", err=True)
        for err in errors:
            typer.echo(f"ERROR: {err}", err=True)
        for w in warnings:
            typer.echo(f"WARNING: {w}", err=True)
        raise typer.Exit(code=1)

    typer.echo("OK: no lint issues.")


@app.command()
def stacks() -> None:
    """
    List all available stacks (technology combinations).

    Shows both preset stacks and available stack implementations.

    ⚠ No directory required - shows available options.
    """
    from dazzle.stacks import list_backends, get_backend
    from dazzle.core.stacks import list_stack_presets, get_stack_preset

    # Show preset stacks first
    presets = list_stack_presets()
    if presets:
        typer.echo("Preset Stacks:\n")
        for preset_name in presets:
            preset = get_stack_preset(preset_name)
            if preset:
                typer.echo(f"  {preset_name}")
                typer.echo(f"    {preset.description}")
                typer.echo(f"    Implementations: {', '.join(preset.backends)}")
                typer.echo()

    # Show available stack implementations
    available = list_backends()
    if available:
        typer.echo("Stack Implementations:\n")
        for name in sorted(available):
            try:
                backend = get_backend(name)
                capabilities = backend.get_capabilities()
                typer.echo(f"  {name}")
                typer.echo(f"    {capabilities.description}")
                typer.echo(f"    Formats: {', '.join(capabilities.output_formats)}")
            except Exception:
                typer.echo(f"  {name}")
                typer.echo(f"    (Error loading implementation)")


@app.command()
def backends() -> None:
    """
    DEPRECATED: Use 'dazzle stacks' instead.

    List all available backends.
    """
    typer.echo("⚠️  'dazzle backends' is deprecated. Use 'dazzle stacks' instead.\n")
    # Delegate to stacks command
    from dazzle.cli import stacks as stacks_cmd
    stacks_cmd()


@app.command()
def build(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    stack: Optional[str] = typer.Option(None, "--stack", "-s", help="Stack preset or comma-separated list (e.g., 'micro' or 'django_api,nextjs')"),
    backend: Optional[str] = typer.Option(None, "--backend", "-b", help="DEPRECATED: Use --stack instead"),
    backends: Optional[str] = typer.Option(None, "--backends", help="DEPRECATED: Use --stack instead"),
    out: str = typer.Option("./build", "--out", "-o", help="Output directory"),
    incremental: bool = typer.Option(False, "--incremental", "-i", help="Incremental build (only regenerate changed parts)"),
    force: bool = typer.Option(False, "--force", help="Force full rebuild (ignore previous state)"),
    diff: bool = typer.Option(False, "--diff", help="Show what would change without building"),
) -> None:
    """
    Generate artifacts from the merged AppSpec using a stack.

    ⚠ Operates in CURRENT directory (must contain dazzle.toml).

    A stack can be a preset name (like 'micro', 'django_next') or a custom
    comma-separated list of stack implementations.

    By default, uses the stack defined in dazzle.toml or falls back to 'micro'.

    Examples:
        dazzle build                                    # Use default stack (micro)
        dazzle build --stack django_next                # Use preset stack
        dazzle build --stack openapi                    # Single-implementation stack
        dazzle build --stack django_api,nextjs,docker   # Custom stack
        dazzle build --incremental                      # Incremental build
        dazzle build --diff                             # Show changes without building
    """
    from dazzle.stacks import get_backend
    from dazzle.core.errors import BackendError
    from dazzle.core.stacks import resolve_stack_backends, validate_stack_backends, StackError

    root = Path(".").resolve()
    manifest_path = root / manifest

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)

        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)

        # Validate before building
        errors, warnings = lint_appspec(appspec)
        if errors:
            typer.echo("Cannot build; spec has validation errors:", err=True)
            for err in errors:
                typer.echo(f"ERROR: {err}", err=True)
            raise typer.Exit(code=1)

        if warnings:
            typer.echo("Build warnings:", err=False)
            for warn in warnings:
                typer.echo(f"WARNING: {warn}", err=False)
            typer.echo()

        # Resolve which stack implementations to build
        backend_list = []

        # Show deprecation warnings for old flags
        if backends or backend:
            typer.echo("⚠️  --backend and --backends are deprecated. Use --stack instead.", err=True)
            typer.echo("   Example: dazzle build --stack openapi", err=True)
            typer.echo()

        # Priority: --stack > --backends (deprecated) > --backend (deprecated) > manifest stack > default
        if stack:
            # Stack flag: can be preset name OR comma-separated list
            backend_list = resolve_stack_backends(stack, None)
        elif backends:
            # DEPRECATED: Explicit comma-separated backend list
            backend_list = [b.strip() for b in backends.split(",")]
        elif backend:
            # DEPRECATED: Legacy single backend flag
            backend_list = [backend]
        elif mf.stack and mf.stack.backends:
            # Stack from manifest (explicit backend list)
            backend_list = mf.stack.backends
            typer.echo(f"Using stack '{mf.stack.name}' from manifest")
        elif mf.stack and mf.stack.name:
            # Stack name in manifest, resolve to preset
            backend_list = resolve_stack_backends(mf.stack.name, None)
            typer.echo(f"Using stack preset '{mf.stack.name}'")
        else:
            # Default to 'micro' stack (django_micro_modular)
            backend_list = ["django_micro_modular"]
            typer.echo("Using default stack: 'micro'")

        # Validate all backends exist
        validate_stack_backends(backend_list)

        # Handle --diff flag for change detection
        if diff:
            prev_state = load_state(root)
            if prev_state:
                current_hashes = compute_dsl_hashes(dsl_files, root)
                changeset = detect_changes(prev_state, appspec, current_hashes)

                if changeset.is_empty():
                    typer.echo("No changes detected since last build.")
                else:
                    typer.echo("Changes detected:")
                    typer.echo(changeset.summary())
                    typer.echo("\nRun without --diff to apply changes.")
            else:
                typer.echo("No previous build state found. This would be a full build.")
            return

        # Build each backend in order
        base_output_dir = Path(out).resolve()
        artifacts = {}  # Shared artifacts between backends

        for backend_name in backend_list:
            typer.echo(f"\n{'='*60}")
            typer.echo(f"Building backend: {backend_name}")
            typer.echo(f"{'='*60}\n")

            # Get backend implementation
            backend_impl = get_backend(backend_name)

            # Determine output directory
            if len(backend_list) == 1:
                # Single backend: output directly to out dir
                output_dir = base_output_dir
            else:
                # Multiple backends: create subdirectory per backend
                output_dir = base_output_dir / backend_name

            output_dir.mkdir(parents=True, exist_ok=True)

            # Check for previous state and handle incremental builds
            prev_state = None if force else load_state(root)
            changeset = None

            if prev_state and incremental:
                current_hashes = compute_dsl_hashes(dsl_files, root)
                changeset = detect_changes(prev_state, appspec, current_hashes)

                if changeset.is_empty():
                    typer.echo(f"  No changes detected for {backend_name}, skipping...")
                    continue

                typer.echo("  Changes detected:")
                typer.echo(changeset.summary())

                if changeset.requires_full_rebuild():
                    typer.echo("  ⚠ Changes require full rebuild")
                    incremental = False

            # Validate backend config
            backend_impl.validate_config()

            # Check incremental support
            capabilities = backend_impl.get_capabilities()
            if incremental and not capabilities.supports_incremental:
                typer.echo(
                    f"  ⚠ Backend '{backend_name}' does not support incremental builds"
                )
                incremental = False

            # Generate artifacts
            try:
                if incremental and changeset:
                    typer.echo(f"  Generating incrementally...")
                    if hasattr(backend_impl, "generate_incremental"):
                        backend_impl.generate_incremental(appspec, output_dir, changeset)
                    else:
                        backend_impl.generate(appspec, output_dir)
                else:
                    typer.echo(f"  Generating...")
                    backend_impl.generate(appspec, output_dir, artifacts=artifacts)

                # Save state for incremental builds
                save_state(root, backend_name, output_dir, dsl_files, appspec)

                # Collect artifacts from this backend (for next backends to use)
                if hasattr(backend_impl, "get_artifacts"):
                    artifacts[backend_name] = backend_impl.get_artifacts(output_dir)

                typer.echo(f"  ✓ {backend_name} → {output_dir}")

            except BackendError as e:
                typer.echo(f"  ✗ Backend error: {e}", err=True)
                raise typer.Exit(code=1)

        typer.echo(f"\n{'='*60}")
        typer.echo(f"✓ Build complete: {', '.join(backend_list)}")
        typer.echo(f"{'='*60}")

    except StackError as e:
        typer.echo(f"Stack error: {e}", err=True)
        raise typer.Exit(code=1)
    except BackendError as e:
        typer.echo(f"Backend error: {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"Unexpected error during build: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def demo(
    stack: Optional[str] = typer.Argument(None, help="Stack preset name (defaults to 'micro' - simplest setup)"),
    path: Optional[str] = typer.Option(None, "--path", "-p", help="Directory to create demo in (default: ./<stack>-demo)"),
    list_stacks: bool = typer.Option(False, "--list", "-l", help="List available stack presets"),
    no_build: bool = typer.Option(False, "--no-build", help="Skip automatic build after generation"),
) -> None:
    """
    Create a demo project with example DSL and stack configuration in a NEW directory.

    ⚠ Creates a NEW directory (default: ./<stack>-demo).

    Generates a complete working project with:
    - dazzle.toml with stack configuration
    - Example DSL file
    - README.md with instructions
    - Optionally builds the project

    Defaults to 'micro' stack (simplest setup - Django + SQLite).

    Examples:
        dazzle demo                       # Create micro stack demo (default)
        dazzle demo micro                 # Same as above
        dazzle demo openapi_only          # Create OpenAPI demo
        dazzle demo --list                # List available stacks
    """
    from dazzle.core.stacks import list_stack_presets, get_stack_preset, get_stack_description, DEFAULT_DEMO_STACK

    # List available stacks
    if list_stacks:
        stacks = list_stack_presets()
        if not stacks:
            typer.echo("No stack presets available.")
            return

        typer.echo("Available demo stacks:\n")

        # Show default stack first with indicator
        default_preset = get_stack_preset(DEFAULT_DEMO_STACK)
        default_desc = get_stack_description(DEFAULT_DEMO_STACK)
        typer.echo(f"  {DEFAULT_DEMO_STACK} (default)")
        for line in default_desc.split('\n'):
            typer.echo(f"    {line}")
        if default_preset and default_preset.example_dsl:
            typer.echo(f"    Example: {default_preset.example_dsl}")
        typer.echo()

        # Show other stacks
        for stack_name in stacks:
            if stack_name == DEFAULT_DEMO_STACK:
                continue
            desc = get_stack_description(stack_name)
            preset = get_stack_preset(stack_name)
            typer.echo(f"  {stack_name}")
            for line in desc.split('\n'):
                typer.echo(f"    {line}")
            if preset and preset.example_dsl:
                typer.echo(f"    Example: {preset.example_dsl}")
            typer.echo()

        typer.echo("Use: dazzle demo [stack]")
        typer.echo(f"     dazzle demo              # Uses '{DEFAULT_DEMO_STACK}' (recommended for beginners)")
        return

    # Use default stack if none provided
    if stack is None:
        stack = DEFAULT_DEMO_STACK
        typer.echo(f"No stack specified, using default: '{stack}'")
        typer.echo(f"(Run 'dazzle demo --list' to see other options)\n")

    # Validate stack exists
    preset = get_stack_preset(stack)
    if not preset:
        typer.echo(f"Error: Stack '{stack}' not found.", err=True)
        typer.echo("Use 'dazzle demo --list' to see available stacks.", err=True)
        raise typer.Exit(code=1)

    # Determine target directory
    if path is None:
        path = f"./{stack}-demo"

    target_dir = Path(path).resolve()

    # Check if directory exists
    if target_dir.exists():
        typer.echo(f"Error: Directory '{target_dir}' already exists.", err=True)
        typer.echo("Please choose a different path or remove the existing directory.", err=True)
        raise typer.Exit(code=1)

    try:
        # Create demo project
        typer.echo(f"Creating demo project with stack: {stack}")
        typer.echo(f"Example DSL: {preset.example_dsl or 'simple_task'}")
        typer.echo(f"Location: {target_dir}\n")

        _create_demo_project(target_dir, preset)

        typer.echo(f"✓ Demo project created: {target_dir}")
        typer.echo("✓ Initialized git repository")
        typer.echo("✓ Created LLM context files (LLM_CONTEXT.md, .llm/, .claude/, .copilot/)\n")

        # Verify project setup
        typer.echo("Verifying project setup...")
        from dazzle.core.init import verify_project

        if not verify_project(target_dir):
            typer.echo("⚠ Verification failed - DSL validation errors detected", err=True)
            typer.echo("Run 'dazzle validate' in the project directory for details\n", err=False)
            raise typer.Exit(code=1)

        typer.echo("✓ Verification passed\n")

        # Optionally build the project
        if not no_build:
            typer.echo("Building project...")
            import subprocess
            result = subprocess.run(
                ["python3", "-m", "dazzle.cli", "build"],
                cwd=target_dir,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                typer.echo("✓ Build complete\n")
            else:
                typer.echo("⚠ Build failed:\n", err=True)
                if result.stderr:
                    typer.echo(result.stderr, err=True)
                if result.stdout:
                    typer.echo(result.stdout, err=True)
                typer.echo("\nYou can build manually with 'dazzle build'\n", err=False)

        # Print next steps
        typer.echo("=" * 60)
        typer.echo("Next steps:")
        typer.echo(f"  cd {path}")

        if no_build:
            typer.echo("  dazzle build")

        # Stack-specific instructions
        if stack == "micro":
            typer.echo("\nDjango Micro Stack - All-in-one setup:")
            typer.echo("  - Complete Django application with SQLite")
            typer.echo("  - Models, views, forms, and templates")
            typer.echo("  - Django Admin interface")
            typer.echo("  - Easy deployment to Heroku/Railway/PythonAnywhere")
            typer.echo("\nTo run:")
            typer.echo(f"  cd {path}/build")
            typer.echo("  cd <project-name>")
            typer.echo("  pip install -r requirements.txt")
            typer.echo("  python manage.py migrate")
            typer.echo("  python manage.py runserver")

        if stack == "express_micro":
            typer.echo("\nExpress Micro Stack - Node.js alternative:")
            typer.echo("  - Complete Express.js application with SQLite")
            typer.echo("  - Sequelize ORM models and routes")
            typer.echo("  - EJS templates and AdminJS interface")
            typer.echo("  - Easy deployment to Heroku/Railway/Vercel")
            typer.echo("\nTo run:")
            typer.echo(f"  cd {path}/build")
            typer.echo("  cd <project-name>")
            typer.echo("  npm install")
            typer.echo("  npm start")

        if "docker" in preset.backends:
            typer.echo("\nTo run with Docker:")
            typer.echo("  cd build/docker")
            typer.echo("  docker compose up -d")

        if "terraform" in preset.backends:
            typer.echo("\nTo deploy with Terraform:")
            typer.echo("  cd build/terraform/envs/dev")
            typer.echo("  terraform init")
            typer.echo("  terraform plan")

        if "openapi" in preset.backends:
            typer.echo("\nGenerated artifacts:")
            typer.echo("  - OpenAPI spec: build/openapi/openapi.yaml")

        # Show other available stacks
        typer.echo("\n" + "-" * 60)
        typer.echo("Other available stacks:")
        typer.echo("  dazzle demo --list           # See all stack options")
        typer.echo("\nPopular choices:")
        typer.echo("  dazzle demo openapi_only     # Just OpenAPI spec (no code)")
        typer.echo("  dazzle demo api_only         # Django API + Docker")
        typer.echo("  dazzle demo django_next      # Full-stack with Next.js frontend")

        # Show information about included examples
        typer.echo("\n" + "-" * 60)
        typer.echo("Explore other examples:")
        typer.echo("  DAZZLE includes example projects in your installation:")
        typer.echo("")
        typer.echo("  • simple_task       - Basic CRUD app (1 entity, 4 surfaces)")
        typer.echo("  • support_tickets   - Multi-entity system (3 entities, relationships)")
        typer.echo("")
        typer.echo("  To use an example:")
        typer.echo("    dazzle clone simple_task          # Copy to current directory")
        typer.echo("    dazzle clone support_tickets      # Copy support_tickets example")
        typer.echo("")
        typer.echo("  Or browse examples:")
        typer.echo("    # Find examples directory")
        typer.echo("    python -c 'import dazzle; print(dazzle.__file__.replace(\"__init__.py\", \"../examples\"))'")

        typer.echo("=" * 60)

    except Exception as e:
        typer.echo(f"Error creating demo: {e}", err=True)
        raise typer.Exit(code=1)


def _create_demo_project(target_dir: Path, preset) -> None:
    """Create a demo project with example DSL and stack configuration."""
    from dazzle.core.stacks import StackPreset
    from dazzle.core.llm_context import create_llm_instrumentation
    import subprocess

    # Create directory structure
    target_dir.mkdir(parents=True, exist_ok=True)
    dsl_dir = target_dir / "dsl"
    dsl_dir.mkdir(exist_ok=True)

    # Determine which example DSL to use
    example_dsl = preset.example_dsl or "simple_task"

    # Create dazzle.toml
    manifest_content = f"""[project]
name = "{preset.name}_demo"
version = "0.1.0"
root = "demo.core"

[modules]
paths = ["./dsl"]

[stack]
name = "{preset.name}"
description = "{preset.description}"
"""

    (target_dir / "dazzle.toml").write_text(manifest_content, encoding="utf-8")

    # Create example DSL based on preset
    if example_dsl == "simple_task":
        dsl_content = """module demo.core

app task_demo "Task Demo Application"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  description: text
  status: enum[todo,in_progress,done]=todo
  priority: enum[low,medium,high]=medium
  created_at: datetime auto_add
  updated_at: datetime auto_update

surface task_list "Task List":
  uses entity Task
  mode: list

  section main "Tasks":
    field title "Title"
    field status "Status"
    field priority "Priority"

surface task_detail "Task Detail":
  uses entity Task
  mode: view

  section main "Task Details":
    field title "Title"
    field description "Description"
    field status "Status"
    field priority "Priority"
    field created_at "Created"
    field updated_at "Updated"

surface task_create "Create Task":
  uses entity Task
  mode: create

  section main "New Task":
    field title "Title"
    field description "Description"
    field priority "Priority"

surface task_edit "Edit Task":
  uses entity Task
  mode: edit

  section main "Edit Task":
    field title "Title"
    field description "Description"
    field status "Status"
    field priority "Priority"
"""
    else:  # support_tickets or complex example
        dsl_content = """module demo.core

app ticket_demo "Support Ticket System"

entity User "User":
  id: uuid pk
  email: str(255) required unique
  name: str(200) required
  created_at: datetime auto_add

entity Ticket "Support Ticket":
  id: uuid pk
  title: str(200) required
  description: text required
  status: enum[open,in_progress,resolved,closed]=open
  priority: enum[low,medium,high,critical]=medium
  created_by: ref[User] required
  assigned_to: ref[User]
  created_at: datetime auto_add
  updated_at: datetime auto_update

entity Comment "Comment":
  id: uuid pk
  ticket: ref[Ticket] required
  author: ref[User] required
  content: text required
  created_at: datetime auto_add

surface ticket_list "Ticket List":
  uses entity Ticket
  mode: list

  section main "Support Tickets":
    field title "Title"
    field status "Status"
    field priority "Priority"
    field created_by "Created By"
    field created_at "Created"

surface ticket_detail "Ticket Detail":
  uses entity Ticket
  mode: view

  section main "Ticket Details":
    field title "Title"
    field description "Description"
    field status "Status"
    field priority "Priority"
    field created_by "Created By"
    field assigned_to "Assigned To"
    field created_at "Created"
    field updated_at "Updated"

surface ticket_create "Create Ticket":
  uses entity Ticket
  mode: create

  section main "New Ticket":
    field title "Title"
    field description "Description"
    field priority "Priority"

surface ticket_edit "Edit Ticket":
  uses entity Ticket
  mode: edit

  section main "Edit Ticket":
    field title "Title"
    field description "Description"
    field status "Status"
    field priority "Priority"
    field assigned_to "Assigned To"
"""

    (dsl_dir / "app.dsl").write_text(dsl_content, encoding="utf-8")

    # Create README.md
    readme_content = f"""# {preset.name} Demo

{preset.description}

## Project Structure

```
{preset.name}-demo/
├── dazzle.toml          # Project manifest with stack configuration
├── dsl/                 # DAZZLE DSL modules
│   └── app.dsl         # Example application definition
├── build/              # Generated artifacts (after build)
```

## Getting Started

### 1. Validate the DSL

```bash
dazzle validate
```

### 2. Build the project

The project is configured with the `{preset.name}` stack, which includes:
{chr(10).join(f'- {backend}' for backend in preset.backends)}

```bash
dazzle build
```

This will generate artifacts in the `build/` directory.

### 3. Explore Generated Artifacts

"""

    # Add stack-specific instructions
    if "openapi" in preset.backends:
        readme_content += """
#### OpenAPI Specification

View the generated API specification:
```bash
cat build/openapi/openapi.yaml
```

Or use a tool like Swagger UI to visualize it.

"""

    if "docker" in preset.backends:
        readme_content += """
#### Docker Setup

Run the application locally with Docker:
```bash
cd build/docker
docker compose up -d
```

The compose setup includes all required services (database, cache, etc.).

"""

    if "terraform" in preset.backends:
        readme_content += """
#### Terraform Infrastructure

Deploy to AWS:
```bash
cd build/terraform/envs/dev
terraform init
terraform plan
terraform apply
```

Configure your AWS credentials before running terraform commands.

"""

    readme_content += """
## Customizing the Application

1. **Edit the DSL**: Modify `dsl/app.dsl` to add entities, surfaces, or change behaviors
2. **Rebuild**: Run `dazzle build` to regenerate artifacts
3. **Incremental builds**: Use `dazzle build --incremental` for faster rebuilds

## Learn More

- **DSL Reference**: See DAZZLE documentation for DSL syntax
- **Stack Options**: Run `dazzle stacks` to see all available stacks
- **Other Stacks**: Run `dazzle demo --list` to try different technology combinations

## Need Help?

- Check the generated artifacts in `build/`
- Run `dazzle validate` to check for DSL errors
- Run `dazzle lint` for extended validation
"""

    (target_dir / "README.md").write_text(readme_content, encoding="utf-8")

    # Create .gitignore
    gitignore_content = """# DAZZLE build artifacts
build/
.dazzle/

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
"""

    (target_dir / ".gitignore").write_text(gitignore_content, encoding="utf-8")

    # Create LLM instrumentation
    try:
        create_llm_instrumentation(
            project_dir=target_dir,
            project_name=f"{preset.name}_demo",
            stack_name=preset.name,
        )
    except Exception as e:
        # Don't fail demo creation if LLM instrumentation fails
        import warnings
        warnings.warn(f"Failed to create LLM instrumentation: {e}")

    # Initialize git repository
    try:
        subprocess.run(
            ["git", "init"],
            cwd=target_dir,
            check=True,
            capture_output=True,
            text=True,
        )

        # Make initial commit
        subprocess.run(
            ["git", "add", "."],
            cwd=target_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit: DAZZLE demo project"],
            cwd=target_dir,
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        # git not installed or failed - not critical for demo
        pass


@app.command()
def clone(
    source: Optional[str] = typer.Argument(None, help="Example app name or GitHub URL to clone"),
    path: Optional[str] = typer.Option(None, "--path", "-p", help="Directory to clone into"),
    stack: Optional[str] = typer.Option(None, "--stack", "-s", help="Stack preset to use (e.g., 'api_only', 'django_next')"),
    list_examples_flag: bool = typer.Option(False, "--list", "-l", help="List available example apps"),
    list_stacks: bool = typer.Option(False, "--list-stacks", help="List available stack presets"),
    no_build: bool = typer.Option(False, "--no-build", help="Skip automatic build after cloning"),
    branch: Optional[str] = typer.Option(None, "--branch", "-b", help="Git branch to clone (for GitHub URLs)"),
) -> None:
    """
    Clone an example app or GitHub repository into a NEW directory.

    ⚠ Creates a NEW directory (default: ./<example-name>).

    This command can:
    - Clone built-in example apps (e.g., 'simple_task', 'support_tickets')
    - Clone DAZZLE projects from GitHub URLs

    When cloning an example, you'll be prompted to choose a stack (infrastructure setup)
    unless you specify one with --stack.

    All cloned projects include:
    - LLM context files for AI assistants
    - Git repository initialization
    - Complete project structure

    Examples:
        dazzle clone                               # Show available examples
        dazzle clone --list                        # List example apps
        dazzle clone simple_task                   # Clone example (prompts for stack)
        dazzle clone simple_task --stack api_only  # Clone with specific stack
        dazzle clone simple_task --path ./my-app   # Clone to custom path
        dazzle clone https://github.com/user/dazzle-project  # Clone from GitHub
    """
    from dazzle.core.stacks import list_stack_presets, get_stack_preset, get_stack_description
    import subprocess
    import re

    # List available stacks
    if list_stacks:
        stacks = list_stack_presets()
        if not stacks:
            typer.echo("No stack presets available.")
            return

        typer.echo("Available stack presets:\n")
        for stack_name in stacks:
            desc = get_stack_description(stack_name)
            typer.echo(f"  {stack_name}")
            for line in desc.split('\n'):
                typer.echo(f"    {line}")
            typer.echo()

        typer.echo("Use: dazzle clone <example> --stack <stack-name>")
        return

    # List available examples
    if list_examples_flag or (source is None):
        examples = list_examples()
        if not examples:
            typer.echo("No example apps available.")
            return

        if source is None:
            typer.echo("Usage: dazzle clone [SOURCE] [OPTIONS]\n")
            typer.echo("Clone an example app or GitHub repository.\n")

        typer.echo("Available example apps:\n")
        for example in examples:
            typer.echo(f"  {example}")

        typer.echo("\nExamples:")
        typer.echo("  dazzle clone simple_task                   # Clone example")
        typer.echo("  dazzle clone simple_task --stack api_only  # With specific stack")
        typer.echo("  dazzle clone https://github.com/user/repo  # Clone from GitHub")
        typer.echo("\nOptions:")
        typer.echo("  --list, -l             List all example apps")
        typer.echo("  --list-stacks          List all stack presets")
        typer.echo("  --stack, -s STACK      Stack preset to use")
        typer.echo("  --path, -p PATH        Directory to clone into")
        typer.echo("  --branch, -b NAME      Git branch to clone (GitHub only)")
        typer.echo("  --no-build             Skip automatic build")
        return

    # Check if source is a GitHub URL
    is_github_url = bool(re.match(r'https?://(www\.)?github\.com/', source))
    is_git_url = source.endswith('.git') or is_github_url

    if is_git_url:
        # Clone from GitHub
        _clone_from_github(source, path, branch, no_build)
    else:
        # Clone example app
        _clone_example(source, path, stack, no_build)


def _clone_from_github(url: str, path: Optional[str], branch: Optional[str], no_build: bool) -> None:
    """Clone a DAZZLE project from GitHub."""
    import subprocess
    import re

    # Extract project name from URL
    match = re.search(r'/([^/]+?)(?:\.git)?$', url)
    project_name = match.group(1) if match else "cloned-project"

    # Determine target directory
    if path is None:
        path = f"./{project_name}"

    target_dir = Path(path).resolve()

    # Check if directory exists
    if target_dir.exists():
        typer.echo(f"Error: Directory '{target_dir}' already exists.", err=True)
        typer.echo("Please choose a different path or remove the existing directory.", err=True)
        raise typer.Exit(code=1)

    try:
        typer.echo(f"Cloning from GitHub: {url}")
        typer.echo(f"Location: {target_dir}\n")

        # Build git clone command
        clone_cmd = ["git", "clone"]
        if branch:
            clone_cmd.extend(["--branch", branch])
        clone_cmd.extend([url, str(target_dir)])

        # Clone repository
        result = subprocess.run(
            clone_cmd,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            typer.echo(f"Error cloning repository: {result.stderr}", err=True)
            raise typer.Exit(code=1)

        typer.echo(f"✓ Cloned from GitHub: {target_dir}")

        # Check if it's a DAZZLE project
        if not (target_dir / "dazzle.toml").exists():
            typer.echo("\n⚠ Warning: This doesn't appear to be a DAZZLE project (no dazzle.toml found)")
            typer.echo("If this is a DAZZLE project, make sure the repository structure is correct.")
            return

        typer.echo("✓ DAZZLE project detected\n")

        # Verify project setup
        typer.echo("Verifying project setup...")
        from dazzle.core.init import verify_project

        if not verify_project(target_dir):
            typer.echo("⚠ Verification failed - DSL validation errors detected", err=True)
            typer.echo("Run 'dazzle validate' in the project directory for details\n", err=False)
            # Don't exit here - let user try to fix issues
        else:
            typer.echo("✓ Verification passed\n")

        # Optionally build the project
        if not no_build:
            typer.echo("Building project...")
            result = subprocess.run(
                ["python3", "-m", "dazzle.cli", "build"],
                cwd=target_dir,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                typer.echo("✓ Build complete\n")
            else:
                typer.echo("⚠ Build failed:\n", err=True)
                if result.stderr:
                    typer.echo(result.stderr, err=True)
                if result.stdout:
                    typer.echo(result.stdout, err=True)
                typer.echo("\nYou can build manually with 'dazzle build'\n", err=False)

        # Print next steps
        typer.echo("=" * 60)
        typer.echo("Next steps:")
        typer.echo(f"  cd {path}")
        if no_build:
            typer.echo("  dazzle build")
        typer.echo("  dazzle validate")
        typer.echo("=" * 60)

    except subprocess.CalledProcessError as e:
        typer.echo(f"Error during git clone: {e}", err=True)
        raise typer.Exit(code=1)
    except FileNotFoundError:
        typer.echo("Error: git command not found. Please install git.", err=True)
        raise typer.Exit(code=1)


def _get_available_stacks() -> list[str]:
    """Get list of stacks that have all their backends available."""
    from dazzle.core.stacks import list_stack_presets, get_stack_preset
    from dazzle.stacks import list_backends

    available_backends = set(list_backends())
    all_stacks = list_stack_presets()
    valid_stacks = []

    for stack_name in all_stacks:
        preset = get_stack_preset(stack_name)
        if preset and all(backend in available_backends for backend in preset.backends):
            valid_stacks.append(stack_name)

    return valid_stacks


def _clone_example(example_name: str, path: Optional[str], stack_name: Optional[str], no_build: bool) -> None:
    """Clone a built-in example app."""
    from dazzle.core.stacks import get_stack_preset, list_stack_presets, get_stack_description
    from dazzle.stacks import list_backends

    # Validate example exists
    examples = list_examples()
    if example_name not in examples:
        typer.echo(f"Error: Example '{example_name}' not found.", err=True)
        typer.echo("Use 'dazzle clone --list' to see available examples.", err=True)
        raise typer.Exit(code=1)

    # Prompt for stack if not provided
    if stack_name is None:
        # Only show stacks with available implementations
        stacks = _get_available_stacks()
        if not stacks:
            typer.echo("Error: No compatible stack presets available.", err=True)
            typer.echo(f"Available stack implementations: {', '.join(list_backends())}", err=True)
            raise typer.Exit(code=1)

        typer.echo("\nAvailable stacks:\n")
        for i, stack in enumerate(stacks, 1):
            desc = get_stack_description(stack)
            first_line = desc.split('\n')[0] if desc else ""
            typer.echo(f"  {i}. {stack:20s} - {first_line}")

        typer.echo()
        while True:
            choice = typer.prompt("Select a stack (enter number or name)")

            # Try as number first
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(stacks):
                    stack_name = stacks[idx]
                    break
            except ValueError:
                pass

            # Try as stack name
            if choice in stacks:
                stack_name = choice
                break

            typer.echo(f"Invalid choice. Please enter a number (1-{len(stacks)}) or stack name.")

    # Validate stack
    preset = get_stack_preset(stack_name)
    if not preset:
        typer.echo(f"Error: Stack '{stack_name}' not found.", err=True)
        typer.echo("Use 'dazzle clone --list-stacks' to see available stacks.", err=True)
        raise typer.Exit(code=1)

    # Validate stack implementations are available
    available_backends = set(list_backends())
    missing_backends = [b for b in preset.backends if b not in available_backends]
    if missing_backends:
        typer.echo(f"Error: Stack '{stack_name}' requires unavailable implementations: {', '.join(missing_backends)}", err=True)
        typer.echo(f"Available implementations: {', '.join(sorted(available_backends))}", err=True)
        typer.echo("\nUse a different stack or specify custom stack:", err=True)
        typer.echo(f"  dazzle build --stack {','.join([b for b in preset.backends if b in available_backends])}", err=True)
        raise typer.Exit(code=1)

    # Determine target directory
    if path is None:
        path = f"./{example_name}"

    target_dir = Path(path).resolve()

    # Check if directory exists
    if target_dir.exists():
        typer.echo(f"Error: Directory '{target_dir}' already exists.", err=True)
        typer.echo("Please choose a different path or remove the existing directory.", err=True)
        raise typer.Exit(code=1)

    try:
        # Create project from example
        typer.echo(f"Cloning example: {example_name}")
        typer.echo(f"Stack: {stack_name}")
        typer.echo(f"Location: {target_dir}\n")

        # Initialize from example
        init_project(
            target_dir=target_dir,
            project_name=example_name,
            from_example=example_name,
        )

        # Update dazzle.toml with stack configuration
        manifest_path = target_dir / "dazzle.toml"
        if manifest_path.exists():
            manifest_content = manifest_path.read_text()
            # Add stack section if not present
            if "[stack]" not in manifest_content:
                stack_section = f"\n[stack]\nname = \"{stack_name}\"\n"
                manifest_path.write_text(manifest_content + stack_section)
            else:
                # Update existing stack name
                import re
                manifest_content = re.sub(
                    r'name = "[^"]*"',
                    f'name = "{stack_name}"',
                    manifest_content,
                    count=1,
                    flags=re.MULTILINE
                )
                manifest_path.write_text(manifest_content)

        typer.echo(f"✓ Example cloned: {target_dir}")
        typer.echo("✓ Initialized git repository")
        typer.echo("✓ Created LLM context files (LLM_CONTEXT.md, .llm/, .claude/, .copilot/)\n")

        # Verify project setup
        typer.echo("Verifying project setup...")
        from dazzle.core.init import verify_project

        if not verify_project(target_dir):
            typer.echo("⚠ Verification failed - DSL validation errors detected", err=True)
            typer.echo("Run 'dazzle validate' in the project directory for details\n", err=False)
            raise typer.Exit(code=1)

        typer.echo("✓ Verification passed\n")

        # Optionally build the project
        if not no_build:
            typer.echo("Building project...")
            import subprocess
            result = subprocess.run(
                ["python3", "-m", "dazzle.cli", "build"],
                cwd=target_dir,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                typer.echo("✓ Build complete\n")
            else:
                typer.echo("⚠ Build failed:\n", err=True)
                if result.stderr:
                    typer.echo(result.stderr, err=True)
                if result.stdout:
                    typer.echo(result.stdout, err=True)
                typer.echo("\nYou can build manually with 'dazzle build'\n", err=False)

        # Print next steps
        typer.echo("=" * 60)
        typer.echo("Next steps:")
        typer.echo(f"  cd {path}")

        if no_build:
            typer.echo("  dazzle build")

        # Stack-specific instructions
        if "django" in preset.backends:
            typer.echo("\nDjango API:")
            typer.echo("  cd build  # or build/django_api if multiple backends")
            typer.echo("  pip install -r requirements.txt")
            typer.echo("  python manage.py migrate")
            typer.echo("  python manage.py runserver")

        if "openapi" in preset.backends:
            typer.echo("\nOpenAPI:")
            typer.echo("  View spec: build/openapi/openapi.yaml")

        if "docker" in preset.backends:
            typer.echo("\nDocker:")
            typer.echo("  cd build/docker")
            typer.echo("  docker compose up -d")

        typer.echo("=" * 60)

    except Exception as e:
        typer.echo(f"Error cloning example: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def infra(
    type: Optional[str] = typer.Argument(None, help="DEPRECATED: Use 'dazzle build --stack' instead"),
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    out: Optional[str] = typer.Option(None, "--out", "-o", help="Output directory"),
    list_types: bool = typer.Option(False, "--list", "-l", help="List available stacks"),
    force: bool = typer.Option(False, "--force", help="Force rebuild"),
) -> None:
    """
    DEPRECATED: Use 'dazzle build --stack' instead.

    This command is deprecated. Use the unified build command:
        dazzle build --stack docker
        dazzle build --stack terraform
        dazzle build --stack docker,terraform

    Examples (new way):
        dazzle build --stack docker           # Generate Docker setup
        dazzle build --stack terraform        # Generate Terraform setup
        dazzle stacks                         # List available stacks
    """
    typer.echo("⚠️  'dazzle infra' is deprecated. Use 'dazzle build --stack' instead.\n", err=True)

    # Show migration examples
    if list_types or type is None:
        typer.echo("Migration guide:", err=True)
        typer.echo("  Old: dazzle infra --list", err=True)
        typer.echo("  New: dazzle stacks", err=True)
        typer.echo("", err=True)
        typer.echo("  Old: dazzle infra docker", err=True)
        typer.echo("  New: dazzle build --stack docker", err=True)
        typer.echo("", err=True)
        typer.echo("  Old: dazzle infra terraform", err=True)
        typer.echo("  New: dazzle build --stack terraform", err=True)
        typer.echo("", err=True)
        typer.echo("  Old: dazzle infra all", err=True)
        typer.echo("  New: dazzle build --stack docker,terraform", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Redirecting to: dazzle build --stack {type}", err=True)
    typer.echo("", err=True)

    # For now, just tell them the new command rather than executing it
    # (executing would be complex due to different parameter handling)
    typer.echo(f"Please run: dazzle build --stack {type} --out {out or './build'}", err=True)
    raise typer.Exit(code=1)


@app.command(name="analyze-spec")
def analyze_spec(
    spec_path: str = typer.Argument(..., help="Path to specification file (e.g., SPEC.md)"),
    output_json: bool = typer.Option(False, "--output-json", help="Output analysis as JSON for programmatic use"),
    provider: str = typer.Option("anthropic", "--provider", "-p", help="LLM provider (anthropic|openai)"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model name (defaults to provider's default)"),
    interactive: bool = typer.Option(True, "--interactive/--no-interactive", help="Run interactive Q&A after analysis"),
    generate_dsl: bool = typer.Option(False, "--generate-dsl", help="Generate DSL from analysis (requires --no-interactive or answers)"),
) -> None:
    """
    Analyze a natural language specification using LLM.

    Extracts state machines, CRUD operations, business rules, and generates
    clarifying questions to complete the specification.

    Requires ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable.

    Examples:
        dazzle analyze-spec SPEC.md                  # Analyze and run interactive Q&A
        dazzle analyze-spec SPEC.md --output-json    # Output JSON for VS Code extension
        dazzle analyze-spec SPEC.md --provider openai  # Use OpenAI instead of Anthropic
        dazzle analyze-spec SPEC.md --no-interactive --generate-dsl  # Auto-generate DSL
    """
    from dazzle.llm import SpecAnalyzer, LLMProvider
    import json

    spec_file = Path(spec_path)
    if not spec_file.exists():
        typer.echo(f"Error: Specification file not found: {spec_path}", err=True)
        raise typer.Exit(code=1)

    # Map provider string to enum
    try:
        provider_enum = LLMProvider(provider)
    except ValueError:
        typer.echo(f"Error: Invalid provider '{provider}'. Use 'anthropic' or 'openai'.", err=True)
        raise typer.Exit(code=1)

    # Check for API key
    if provider_enum == LLMProvider.ANTHROPIC:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            typer.echo("Error: ANTHROPIC_API_KEY environment variable not set.", err=True)
            typer.echo("Set it with: export ANTHROPIC_API_KEY=your-key-here", err=True)
            raise typer.Exit(code=1)
    else:
        if not os.environ.get("OPENAI_API_KEY"):
            typer.echo("Error: OPENAI_API_KEY environment variable not set.", err=True)
            typer.echo("Set it with: export OPENAI_API_KEY=your-key-here", err=True)
            raise typer.Exit(code=1)

    try:
        # Read spec content
        spec_content = spec_file.read_text()

        # Create analyzer
        analyzer_kwargs = {}
        if model:
            analyzer_kwargs['model'] = model

        analyzer = SpecAnalyzer(provider=provider_enum, **analyzer_kwargs)

        # Estimate cost
        if not output_json:
            estimated_cost = analyzer.estimate_cost(spec_content)
            if estimated_cost > 0.50:
                typer.echo(f"⚠ Estimated cost: ${estimated_cost:.2f}")
                proceed = typer.confirm("Continue?")
                if not proceed:
                    typer.echo("Analysis cancelled.")
                    raise typer.Exit(code=0)

        # Run analysis
        if not output_json:
            typer.echo(f"🔍 Analyzing specification with {provider} ({analyzer.client.model})...")

        analysis = analyzer.analyze(spec_content, str(spec_file))

        # Output results
        if output_json:
            # JSON output for VS Code extension
            print(json.dumps(analysis.model_dump(by_alias=True), indent=2))
        else:
            # Human-readable output
            _print_analysis_summary(analysis)

            if interactive:
                # Run interactive Q&A
                answers = _run_interactive_qa(analysis)

                if generate_dsl and answers:
                    typer.echo("\n📝 Generating DSL...")
                    _generate_dsl(analysis, answers, spec_file)
            elif generate_dsl:
                # Generate DSL without Q&A (use defaults)
                typer.echo("\n📝 Generating DSL without Q&A...")
                _generate_dsl(analysis, {}, spec_file)

    except ImportError as e:
        typer.echo(f"Error: LLM integration dependencies not installed: {e}", err=True)
        typer.echo("Install with: pip install 'dazzle[llm]' or pip install anthropic openai", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"Error during analysis: {e}", err=True)
        raise typer.Exit(code=1)


def _print_analysis_summary(analysis) -> None:
    """Print human-readable analysis summary."""
    from dazzle.llm.models import SpecAnalysis

    typer.echo("\n" + "="*60)
    typer.echo("📊 Specification Analysis Results")
    typer.echo("="*60 + "\n")

    # State machines
    if analysis.state_machines:
        typer.echo(f"🔄 State Machines: {len(analysis.state_machines)}")
        for sm in analysis.state_machines:
            typer.echo(f"   • {sm.entity}.{sm.field}: {', '.join(sm.states)}")
            typer.echo(f"     - {len(sm.transitions_found)} transitions found")
            if sm.transitions_implied_but_missing:
                typer.echo(f"     - ⚠ {len(sm.transitions_implied_but_missing)} transitions missing")
        typer.echo()

    # CRUD analysis
    if analysis.crud_analysis:
        typer.echo(f"📋 Entities Analyzed: {len(analysis.crud_analysis)}")
        for crud in analysis.crud_analysis:
            if crud.missing_operations:
                typer.echo(f"   ⚠ {crud.entity}: Missing {', '.join(crud.missing_operations)}")
        typer.echo()

    # Business rules
    if analysis.business_rules:
        typer.echo(f"📏 Business Rules: {len(analysis.business_rules)}")
        rule_types = {}
        for rule in analysis.business_rules:
            rule_types[rule.type] = rule_types.get(rule.type, 0) + 1
        for rule_type, count in rule_types.items():
            typer.echo(f"   • {rule_type}: {count}")
        typer.echo()

    # Questions
    question_count = analysis.get_question_count()
    if question_count > 0:
        typer.echo(f"❓ Clarifying Questions: {question_count}")
        for category in analysis.clarifying_questions:
            typer.echo(f"   • {category.category} ({category.priority}): {len(category.questions)} questions")
        typer.echo()

    # Coverage stats
    sm_coverage = analysis.get_state_machine_coverage()
    crud_coverage = analysis.get_crud_coverage()

    typer.echo("📈 Coverage:")
    typer.echo(f"   • State Machines: {sm_coverage['coverage_percent']:.1f}%")
    typer.echo(f"   • CRUD Operations: {crud_coverage['coverage_percent']:.1f}%")
    typer.echo()


def _run_interactive_qa(analysis) -> dict:
    """Run interactive Q&A session."""
    answers = {}

    if analysis.get_question_count() == 0:
        typer.echo("✓ No clarifying questions needed.")
        return answers

    typer.echo("\n" + "="*60)
    typer.echo("💬 Interactive Q&A")
    typer.echo("="*60 + "\n")

    for category in analysis.clarifying_questions:
        typer.echo(f"\n📋 {category.category} (Priority: {category.priority})")
        typer.echo("-"*60)

        for i, question in enumerate(category.questions, 1):
            typer.echo(f"\n{i}. {question.q}")
            typer.echo(f"   Context: {question.context}")
            typer.echo(f"   Impacts: {question.impacts}")
            typer.echo("\n   Options:")
            for j, option in enumerate(question.options, 1):
                typer.echo(f"     {j}) {option}")

            # Get answer
            while True:
                answer = typer.prompt(f"\n   Choose (1-{len(question.options)})", type=int)
                if 1 <= answer <= len(question.options):
                    selected_option = question.options[answer - 1]
                    answers[question.q] = selected_option
                    typer.echo(f"   ✓ Selected: {selected_option}\n")
                    break
                else:
                    typer.echo(f"   Invalid choice. Enter 1-{len(question.options)}.")

    typer.echo("\n" + "="*60)
    typer.echo(f"✓ Q&A complete! {len(answers)} questions answered.")
    typer.echo("="*60 + "\n")

    return answers


def _generate_dsl(analysis, answers: dict, spec_file: Path) -> None:
    """Generate DSL from analysis and answers."""
    from dazzle.llm import DSLGenerator

    # Derive module/app names from spec file location
    spec_dir = spec_file.parent
    module_name = spec_dir.name if spec_dir.name != '.' else 'app'

    # Try to read app name from spec
    spec_content = spec_file.read_text()
    app_name = module_name.replace('_', ' ').title()

    # Look for app name in spec (first line or header)
    for line in spec_content.split('\n')[:5]:
        if line.startswith('#') and not line.startswith('##'):
            # Found title
            app_name = line.lstrip('#').strip()
            break

    # Generate DSL
    generator = DSLGenerator(analysis, answers)
    dsl_code = generator.generate(module_name, app_name)

    # Determine output path
    output_dir = spec_dir / 'dsl'
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / 'generated.dsl'

    # Write DSL
    output_path.write_text(dsl_code)

    typer.echo(f"✓ DSL generated: {output_path}")
    typer.echo(f"   Module: {module_name}")
    typer.echo(f"   App: {app_name}")
    typer.echo(f"\nNext steps:")
    typer.echo(f"   1. Review and customize {output_path}")
    typer.echo(f"   2. Run: dazzle validate")
    typer.echo(f"   3. Run: dazzle build")


@app.command()
def example(
    name: Optional[str] = typer.Argument(None, help="Example name to build (e.g., 'simple_task', 'support_tickets')"),
    list_flag: bool = typer.Option(False, "--list", "-l", help="List available examples"),
    out: Optional[str] = typer.Option(None, "--out", "-o", help="Output directory (default: ./build)"),
    backend: Optional[str] = typer.Option(None, "--backend", "-b", help="Backend to use (defaults to project default)"),
) -> None:
    """
    Build one of the built-in examples in-situ (without creating a new project).

    This is useful for quickly trying out examples or building them for demonstration.
    Unlike 'dazzle clone', this doesn't create a new project directory - it just builds
    the example using the current backend configuration.

    Examples:
        dazzle example --list                      # List available examples
        dazzle example simple_task                 # Build to ./build
        dazzle example support_tickets --out /tmp  # Build to /tmp
        dazzle example simple_task --backend openapi  # Build with specific backend
    """
    from dazzle.core.init import list_examples
    from pathlib import Path
    import subprocess
    import os

    # List available examples
    if list_flag or name is None:
        examples_list = list_examples()

        if not examples_list:
            typer.echo("No examples found.", err=True)
            return

        if name is None:
            typer.echo("Usage: dazzle example [NAME] [OPTIONS]\n")
            typer.echo("Build a built-in example project.\n")

        typer.echo("Available examples:\n")

        # Get examples directory to read descriptions
        examples_dir = Path(__file__).parent.parent.parent.parent / "examples"

        for example_name in examples_list:
            example_dir = examples_dir / example_name
            spec_file = example_dir / "SPEC.md"

            # Try to get description from SPEC.md
            description = ""
            if spec_file.exists():
                with open(spec_file, 'r') as f:
                    lines = f.readlines()
                    # Look for the first descriptive line after title
                    for i, line in enumerate(lines):
                        if line.startswith('**Project Type**:'):
                            description = line.replace('**Project Type**:', '').strip()
                            break
                        elif line.startswith('**Target Users**:'):
                            description = line.replace('**Target Users**:', '').strip()
                            break

            typer.echo(f"  {example_name}")
            if description:
                typer.echo(f"    {description}")
            typer.echo()

        typer.echo("Examples:")
        typer.echo("  dazzle example simple_task                 # Build to ./build")
        typer.echo("  dazzle example support_tickets --out /tmp  # Build to /tmp")
        typer.echo("\nFor creating a new project based on an example, use: dazzle clone")
        return

    # Validate example exists
    examples_list = list_examples()
    if name not in examples_list:
        typer.echo(f"Error: Example '{name}' not found.", err=True)
        typer.echo(f"Available examples: {', '.join(examples_list)}", err=True)
        typer.echo("Use 'dazzle example --list' to see details.", err=True)
        raise typer.Exit(code=1)

    # Get example directory
    examples_dir = Path(__file__).parent.parent.parent.parent / "examples"
    example_dir = examples_dir / name

    if not example_dir.exists() or not (example_dir / "dazzle.toml").exists():
        typer.echo(f"Error: Example directory not found or invalid: {example_dir}", err=True)
        raise typer.Exit(code=1)

    # Determine output directory
    if out is None:
        out = "./build"

    output_dir = Path(out).resolve()

    try:
        typer.echo(f"Building example: {name}")
        typer.echo(f"Source: {example_dir}")
        typer.echo(f"Output: {output_dir}\n")

        # Prepare build command
        build_cmd = [
            "python3", "-m", "dazzle.cli", "build",
            "--out", str(output_dir)
        ]

        if backend:
            build_cmd.extend(["--backend", backend])

        # Set PYTHONPATH if needed
        env = os.environ.copy()
        dazzle_src = Path(__file__).parent.parent
        if 'PYTHONPATH' in env:
            env['PYTHONPATH'] = f"{dazzle_src}:{env['PYTHONPATH']}"
        else:
            env['PYTHONPATH'] = str(dazzle_src)

        # Run build from example directory
        result = subprocess.run(
            build_cmd,
            cwd=example_dir,
            env=env,
            capture_output=False,  # Show output in real-time
        )

        if result.returncode != 0:
            typer.echo(f"\n✗ Build failed with exit code {result.returncode}", err=True)
            raise typer.Exit(code=result.returncode)

        typer.echo(f"\n{'=' * 60}")
        typer.echo(f"✓ Example '{name}' built successfully!")
        typer.echo(f"{'=' * 60}\n")

        # Provide next steps based on backend
        typer.echo("Next steps:")

        # Try to determine what was built
        built_dirs = list(output_dir.glob("*/"))
        if built_dirs:
            app_dir = built_dirs[0]
            typer.echo(f"  cd {app_dir}")

            # Check if it's a Django project
            if (app_dir / "manage.py").exists():
                typer.echo("\nDjango application:")
                if (app_dir / ".venv").exists():
                    typer.echo("  source .venv/bin/activate  # Already set up by hooks!")
                else:
                    typer.echo("  pip install -r requirements.txt")
                    typer.echo("  python manage.py migrate")
                typer.echo("  python manage.py runserver")
                typer.echo("\nAdmin credentials: See .admin_credentials file")

            # Check if it's a Node.js project
            elif (app_dir / "package.json").exists():
                typer.echo("\nNode.js application:")
                typer.echo("  npm install")
                typer.echo("  npm start")
        else:
            typer.echo(f"  Check {output_dir} for generated files")

    except subprocess.CalledProcessError as e:
        typer.echo(f"Error during build: {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"Unexpected error: {e}", err=True)
        raise typer.Exit(code=1)


def main(argv: Optional[list[str]] = None) -> None:
    import os
    # Set umask to 0o000 so files are created with 666 permissions (rw-rw-rw--)
    os.umask(0o000)
    app(standalone_mode=True)


if __name__ == "__main__":
    main(sys.argv[1:])