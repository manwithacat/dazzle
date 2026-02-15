"""
Project commands for DAZZLE CLI.

Commands for creating, validating, and working with DAZZLE projects:
- init: Initialize a new project
- validate: Parse and validate DSL
- lint: Extended validation checks
- inspect: Inspect entities and surfaces
- layout-plan: Preview layout changes
- analyze-spec: LLM-powered spec analysis
- example: Create project from example

For code generation, use:
- dazzle serve: Run your DSL directly (rapid iteration)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer

from dazzle.core.errors import DazzleError, ParseError
from dazzle.core.fileset import discover_dsl_files
from dazzle.core.init_impl import InitError, init_project, list_examples
from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules

if TYPE_CHECKING:
    from dazzle.core import ir

logger = logging.getLogger(__name__)


# =============================================================================
# Helper Functions
# =============================================================================


def _is_directory_empty(directory: Path) -> bool:
    """
    Check if directory is empty (or has only files we commonly allow).

    A directory is considered "empty" for init purposes if it contains:
    - No files at all, OR
    - Only .git directory, OR
    - Only .git and common files (.gitignore, README.md, LICENSE, .DS_Store)
    """
    if not directory.exists():
        return True

    contents = list(directory.iterdir())

    if len(contents) == 0:
        return True

    # Allow some common files that might be pre-created
    allowed_files = {".git", ".gitignore", "README.md", "LICENSE", ".DS_Store"}
    actual_files = {item.name for item in contents}

    # If all files are in allowed list, consider it empty
    if actual_files.issubset(allowed_files):
        return True

    return False


def _print_human_diagnostics(
    errors: list[str],
    warnings: list[str],
    appspec: ir.AppSpec | None = None,
) -> None:
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
        typer.secho("✓ Spec is valid", fg=typer.colors.GREEN)
        # Show summary stats if appspec is provided
        if appspec:
            entity_count = len(appspec.domain.entities)
            surface_count = len(appspec.surfaces)
            workspace_count = len(appspec.workspaces)
            typer.echo(
                f"  {entity_count} entities, {surface_count} surfaces, {workspace_count} workspaces"
            )


def _print_vscode_diagnostics(errors: list[str], warnings: list[str], root: Path) -> None:
    """
    Print diagnostics in VS Code format: file:line:col: severity: message
    """
    for err in errors:
        typer.echo(f"dazzle.toml:1:1: error: {err}", err=True)

    for warn in warnings:
        typer.echo(f"dazzle.toml:1:1: warning: {warn}", err=True)

    if not errors and not warnings:
        typer.echo("::notice: Validation successful")


def _print_vscode_parse_error(error: ParseError, root: Path) -> None:
    """Print parse error in VS Code format with location info."""
    if error.context:
        file_path = error.context.file
        if file_path:
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


def _print_analysis_summary(results: dict[str, Any]) -> None:
    """Print analysis results summary."""
    typer.echo("\n📊 Analysis Summary")
    typer.echo("=" * 50)

    if "entities" in results:
        typer.echo(f"\nEntities Identified: {len(results['entities'])}")
        for entity in results["entities"]:
            typer.echo(f"  • {entity['name']}: {len(entity.get('fields', []))} fields")

    if "surfaces" in results:
        typer.echo(f"\nSurfaces Suggested: {len(results['surfaces'])}")
        for surface in results["surfaces"]:
            typer.echo(f"  • {surface['name']} ({surface.get('mode', 'view')})")

    if "workspaces" in results:
        typer.echo(f"\nWorkspaces: {len(results['workspaces'])}")
        for ws in results["workspaces"]:
            typer.echo(f"  • {ws['name']}")


def _run_interactive_qa(analyzer: Any, results: dict[str, Any]) -> dict[str, Any]:
    """Run interactive Q&A session with the analyzer."""
    typer.echo("\n💬 Interactive Q&A (type 'done' to finish)")
    typer.echo("-" * 50)

    while True:
        question = typer.prompt("\nYour question", default="done")
        if question.lower() == "done":
            break

        try:
            answer = analyzer.ask_question(results, question)
            typer.echo(f"\n{answer}")
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)

    return results


def _generate_dsl(analyzer: Any, results: dict[str, Any], output_path: Path) -> None:
    """Generate DSL from analysis results."""
    typer.echo("\n🔧 Generating DSL...")

    try:
        dsl_code = analyzer.generate_dsl(results)

        # Determine module name from results
        app_info = results.get("app", {})
        module_name = app_info.get("module", "main")
        app_name = app_info.get("name", "app")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(dsl_code)

        typer.echo(f"✓ DSL generated: {output_path}")
        typer.echo(f"   Module: {module_name}")
        typer.echo(f"   App: {app_name}")
        typer.echo("\nNext steps:")
        typer.echo(f"   1. Review and customize {output_path}")
        typer.echo("   2. Run: dazzle validate")
        typer.echo("   3. Run: dazzle build")
    except Exception as e:
        typer.echo(f"Error generating DSL: {e}", err=True)
        raise typer.Exit(code=1)


# =============================================================================
# Project Commands - These are registered directly on the main app
# =============================================================================

# Note: These command functions are defined here but registered on the main app
# in cli/__init__.py. They're top-level commands, not sub-commands.


def init_command(
    path: str | None = typer.Argument(
        None, help="Directory to create project in (defaults to current directory if empty)"
    ),
    from_example: str | None = typer.Option(
        None, "--from", "-f", help="Copy from example (e.g., 'simple_task', 'support_tickets')"
    ),
    name: str | None = typer.Option(
        None, "--name", "-n", help="Project name (defaults to directory name)"
    ),
    title: str | None = typer.Option(None, "--title", "-t", help="Project title"),
    here: bool = typer.Option(
        False, "--here", help="Initialize in current directory even if not empty"
    ),
    list_examples_flag: bool = typer.Option(False, "--list", "-l", help="List available examples"),
    no_llm: bool = typer.Option(
        False, "--no-llm", help="Skip LLM instrumentation (context files for AI assistants)"
    ),
    no_git: bool = typer.Option(False, "--no-git", help="Skip git repository initialization"),
) -> None:
    """
    Initialize a new DAZZLE project.

    By default, initializes in current directory if it's empty,
    or creates a new directory if a path is provided.

    Creates project structure with:
    - dazzle.toml manifest
    - dsl/ directory with starter module
    - README.md with getting started guide
    - .gitignore and git repository (unless --no-git)
    - LLM context files for AI assistants (unless --no-llm)

    Examples:
        dazzle init                              # Init in current dir (if empty)
        dazzle init --here                       # Force init in current dir
        dazzle init ./my-project                 # Create new directory
        dazzle init --from simple_task           # Init from example (current dir)
        dazzle init ./my-app --from support_tickets  # New dir from example
        dazzle init --list                       # Show available examples
        dazzle init --no-llm --no-git            # Minimal setup
    """
    if list_examples_flag:
        examples = list_examples()
        if not examples:
            typer.echo("No examples available.")
            return

        typer.echo("Available examples:\n")
        for ex in examples:
            typer.echo(f"  {ex}")
        typer.echo("\nUse: dazzle init --from <example>  # Current directory")
        typer.echo("Or:  dazzle init ./my-project --from <example>  # New directory")
        return

    # Determine target directory
    if path is None:
        target = Path(".").resolve()

        if not _is_directory_empty(target) and not here:
            typer.echo(f"Error: Current directory is not empty: {target}", err=True)
            typer.echo("", err=True)

            contents = [item.name for item in target.iterdir() if not item.name.startswith(".")]
            if contents:
                typer.echo("Current directory contains:", err=True)
                for item in sorted(contents)[:5]:
                    typer.echo(f"  - {item}", err=True)
                if len(contents) > 5:
                    typer.echo(f"  ... and {len(contents) - 5} more items", err=True)
                typer.echo("", err=True)

            typer.echo("Options:", err=True)
            typer.echo("  1. Initialize anyway:  dazzle init --here", err=True)
            typer.echo("  2. Create new dir:     dazzle init ./my-project", err=True)
            typer.echo("  3. Clear directory first (be careful!)", err=True)
            typer.echo("", err=True)
            typer.echo("Tip: --here will not overwrite existing files", err=True)
            raise typer.Exit(code=1)
    else:
        target = Path(path).resolve()

    try:
        allow_existing = path is None

        def progress(msg: str) -> None:
            typer.echo(msg)

        typer.echo("")

        init_project(
            target_dir=target,
            project_name=name,
            from_example=from_example,
            title=title,
            no_llm=no_llm,
            no_git=no_git,
            allow_existing=allow_existing,
            progress_callback=progress,
        )

        typer.echo("")
        if path is None:
            typer.echo(f"✓ Project initialized in: {target}")
        else:
            typer.echo(f"✓ Project created at: {target}")

        typer.echo("\nNext steps:")
        if path is not None:
            typer.echo(f"  cd {path}")
        if not from_example:
            typer.echo("  # 1. Edit SPEC.md with your project requirements")
            typer.echo("  # 2. Work with an AI assistant to create DSL from your spec")
        typer.echo("  dazzle validate")
        typer.echo("  dazzle serve  # Run your app with Dazzle Runtime")

        try:
            from dazzle.mcp.setup import check_mcp_server

            status = check_mcp_server()
            if not status.get("registered"):
                typer.echo("\n💡 Tip: Enable DAZZLE MCP server for Claude Code:")
                typer.echo("  dazzle mcp-setup")
                typer.echo("  Then restart Claude Code to access DAZZLE tools")
        except Exception:
            logger.debug("Failed to check MCP server status", exc_info=True)

    except InitError as e:
        typer.echo(f"Initialization failed: {e}", err=True)
        raise typer.Exit(code=1)


def validate_command(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m", help="Path to dazzle.toml"),
    format: str = typer.Option(
        "human", "--format", "-f", help="Output format: 'human' or 'vscode'"
    ),
) -> None:
    """
    Parse all DSL modules, resolve dependencies, and validate the merged AppSpec.

    Operates in CURRENT directory (must contain dazzle.toml).
    """
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)
        errors, warnings = lint_appspec(appspec)

        if format == "vscode":
            _print_vscode_diagnostics(errors, warnings, root)
        else:
            _print_human_diagnostics(errors, warnings, appspec)

        if errors:
            raise typer.Exit(code=1)

    except ParseError as e:
        if format == "vscode":
            _print_vscode_parse_error(e, root)
        else:
            typer.echo(f"Parse error: {e}", err=True)
        raise typer.Exit(code=1)
    except DazzleError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


def lint_command(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    format: str = typer.Option("human", "--format", "-f", help="Output format"),
    anti_turing: bool = typer.Option(
        False, "--anti-turing", help="Check for Anti-Turing compliance"
    ),
    strict: bool = typer.Option(
        False, "--strict", help="Fail on any violation (with --anti-turing)"
    ),
) -> None:
    """
    Run extended lint checks (validate + additional warnings).

    Use --anti-turing to check DSL files for forbidden constructs:
    - Control flow keywords (if, for, while, etc.)
    - Function definitions (def, lambda, etc.)
    - Programming patterns (=>, ternary operators, etc.)

    Use --strict with --anti-turing to fail CI on any violation.
    """
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)

        # Anti-Turing validation (raw DSL content)
        if anti_turing:
            from dazzle.core.anti_turing import AntiTuringValidator

            validator = AntiTuringValidator(strict=strict)
            all_violations = []

            for dsl_file in dsl_files:
                content = dsl_file.read_text()
                violations = validator.validate(content, str(dsl_file))
                all_violations.extend(violations)

            if all_violations:
                typer.echo(validator.format_violations(all_violations), err=True)
                if strict:
                    raise typer.Exit(code=1)
            else:
                typer.echo("Anti-Turing validation passed.")

            # If only --anti-turing, we're done
            if not format or format == "human":
                return

        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)
        errors, warnings = lint_appspec(appspec, extended=True)

        if format == "vscode":
            _print_vscode_diagnostics(errors, warnings, root)
        else:
            _print_human_diagnostics(errors, warnings)

        if errors:
            raise typer.Exit(code=1)

    except ParseError as e:
        if format == "vscode":
            _print_vscode_parse_error(e, root)
        else:
            typer.echo(f"Parse error: {e}", err=True)
        raise typer.Exit(code=1)
    except DazzleError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


def inspect_command(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    entity: str | None = typer.Option(None, "--entity", "-e", help="Inspect a specific entity"),
    surface: str | None = typer.Option(None, "--surface", "-s", help="Inspect a specific surface"),
    format: str = typer.Option("tree", "--format", "-f", help="Output format: 'tree' or 'json'"),
) -> None:
    """
    Inspect project entities, surfaces, and structure.
    """
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)

        if format == "json":
            import json

            if entity:
                for e in appspec.domain.entities:
                    if e.name == entity:
                        typer.echo(json.dumps(e.model_dump(), indent=2, default=str))
                        return
                typer.echo(f"Entity not found: {entity}", err=True)
                raise typer.Exit(code=1)
            elif surface:
                for s in appspec.surfaces:
                    if s.name == surface:
                        typer.echo(json.dumps(s.model_dump(), indent=2, default=str))
                        return
                typer.echo(f"Surface not found: {surface}", err=True)
                raise typer.Exit(code=1)
            else:
                typer.echo(json.dumps(appspec.model_dump(), indent=2, default=str))
        else:
            # Tree format
            typer.echo(f"\n📦 {appspec.name}")
            typer.echo(f"   {appspec.title}")

            if appspec.domain.entities:
                typer.echo("\n📊 Entities:")
                for e in appspec.domain.entities:
                    field_count = len(e.fields) if e.fields else 0
                    typer.echo(f"   • {e.name} ({field_count} fields)")
                    if entity and e.name == entity:
                        for f in e.fields or []:
                            typer.echo(f"     - {f.name}: {f.type}")

            if appspec.surfaces:
                typer.echo("\n🖥️  Surfaces:")
                for s in appspec.surfaces:
                    entity_ref = s.entity_ref or "none"
                    typer.echo(f"   • {s.name} ({s.mode}, {entity_ref})")

            if appspec.workspaces:
                typer.echo("\n📁 Workspaces:")
                for w in appspec.workspaces:
                    region_count = len(w.regions) if w.regions else 0
                    typer.echo(f"   • {w.name} ({region_count} regions)")

    except (ParseError, DazzleError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


def layout_plan_command(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Specific workspace"),
    format: str = typer.Option("tree", "--format", "-f", help="Output format"),
) -> None:
    """
    Show the layout plan for workspaces.
    """
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)

        workspaces = appspec.workspaces or []
        if workspace:
            workspaces = [w for w in workspaces if w.name == workspace]
            if not workspaces:
                typer.echo(f"Workspace not found: {workspace}", err=True)
                raise typer.Exit(code=1)

        for ws in workspaces:
            typer.echo(f"\n📁 Workspace: {ws.name}")
            typer.echo(f"   Title: {ws.title}")
            if ws.stage:
                typer.echo(f"   Stage: {ws.stage}")
            if ws.regions:
                typer.echo("   Regions:")
                for region in ws.regions:
                    typer.echo(f"     • {region.name}: {region.source}")

    except (ParseError, DazzleError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


def analyze_spec_command(
    spec_file: str | None = typer.Argument(
        None,
        help="Specification file or directory. If omitted, auto-detects spec/ directory or SPEC.md",
    ),
    output: str | None = typer.Option(None, "--output", "-o", help="Output DSL file"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Interactive Q&A mode"),
    provider: str = typer.Option("anthropic", "--provider", "-p", help="LLM provider"),
) -> None:
    """
    Analyze a specification file using LLM to generate DSL.

    Supports flexible spec organization:
    - spec/ directory with multiple markdown files
    - SPEC.md single file (backward compatible)
    - Explicit file path as argument
    """
    from dazzle.core.spec_loader import load_spec

    # Determine spec content
    if spec_file:
        # Explicit file/directory specified
        spec_path = Path(spec_file)
        if not spec_path.exists():
            typer.echo(f"Specification not found: {spec_file}", err=True)
            raise typer.Exit(code=1)

        if spec_path.is_dir():
            # Load from directory - treat the dir as the project root with spec/ inside,
            # or as the spec directory itself if it's named 'spec'
            if spec_path.name == "spec":
                project_root = spec_path.parent
            else:
                project_root = spec_path
            spec_result = load_spec(project_root, include_sources=True)
            spec_content = spec_result.content
            spec_display = f"{spec_file}/ ({spec_result.file_count} files)"
        else:
            spec_content = spec_path.read_text()
            spec_display = spec_file
    else:
        # Auto-detect from current directory
        spec_result = load_spec(Path.cwd(), include_sources=True)
        if spec_result.is_empty:
            typer.echo("No specification found. Create SPEC.md or spec/ directory.", err=True)
            raise typer.Exit(code=1)
        spec_content = spec_result.content
        if spec_result.source_type == "directory":
            spec_display = f"spec/ ({spec_result.file_count} files)"
        else:
            spec_display = "SPEC.md"

    try:
        from dazzle.llm import LLMProvider, SpecAnalyzer

        typer.echo(f"📄 Analyzing: {spec_display}")
        typer.echo(f"   Provider: {provider}")

        # Convert provider string to enum
        try:
            provider_enum = LLMProvider(provider)
        except ValueError:
            typer.echo(
                f"Invalid provider: {provider}. Use: anthropic, openai, claude_cli", err=True
            )
            raise typer.Exit(code=1)

        analyzer = SpecAnalyzer(provider=provider_enum)

        typer.echo("\n🔍 Analyzing specification...")
        analysis = analyzer.analyze(spec_content)

        # Convert to dict for helper functions
        results = analysis.model_dump()

        _print_analysis_summary(results)

        if interactive:
            results = _run_interactive_qa(analyzer, results)

        if output:
            _generate_dsl(analyzer, results, Path(output))

    except ImportError:
        typer.echo("LLM support not available. Install with: pip install dazzle[llm]", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        import traceback

        traceback.print_exc()
        raise typer.Exit(code=1)


def example_command(
    name: str | None = typer.Argument(
        None, help="Example name (e.g., 'simple_task', 'support_tickets')"
    ),
    path: str | None = typer.Option(
        None, "--path", "-p", help="Directory to create (default: ./<example-name>)"
    ),
    reset: bool = typer.Option(
        False,
        "--reset",
        "-r",
        help="Reset existing dir: overwrite source, delete build artifacts, preserve user files",
    ),
    list_flag: bool = typer.Option(False, "--list", "-l", help="List available examples"),
) -> None:
    """
    Create a new project from a built-in example.

    Creates a NEW directory (default: ./<example-name>).

    This command provides an interactive way to explore and use DAZZLE examples.
    It creates a complete project directory with DSL files, ready for development.

    After creation, run your app with Dazzle Runtime:
        cd <project-name>
        dazzle serve


    Examples:
        dazzle example                        # Interactive selection
        dazzle example simple_task            # Create simple_task example
        dazzle example simple_task --path ./my-app   # Create in custom directory
        dazzle example simple_task --reset    # Reset existing project
        dazzle example --list                 # List available examples
    """
    from rich.text import Text

    from dazzle.cli_ui import (
        SelectOption,
        console,
        display_options_table,
        print_divider,
        print_error,
        print_header,
        print_info,
        print_step,
        print_success,
        print_warning,
        select_interactive,
    )

    # Get available examples
    examples_list = list_examples()
    if not examples_list:
        print_error("No examples found.")
        return

    # Build example options with descriptions
    examples_dir = Path(__file__).parent.parent.parent.parent / "examples"
    example_options = []

    description_map = {
        "simple_task": "Basic CRUD app - perfect for learning DAZZLE",
        "support_tickets": "Multi-entity system with relationships and workflows",
    }

    for example_name in examples_list:
        example_dir = examples_dir / example_name
        readme_file = example_dir / "README.md"

        # Try to get description from README.md
        description = ""
        if readme_file.exists():
            with open(readme_file) as f:
                lines = f.readlines()
                in_overview = False
                for line in lines:
                    if "## Overview" in line or "## What This Example Demonstrates" in line:
                        in_overview = True
                        continue
                    if in_overview and line.strip() and not line.startswith("#"):
                        description = line.strip().split(".")[0] + "."
                        if len(description) > 80:
                            description = description[:77] + "..."
                        break

        if not description:
            description = description_map.get(example_name, "DAZZLE example project")

        example_options.append(
            SelectOption(
                value=example_name,
                label=example_name,
                description=description,
                badge="STARTER" if example_name == "simple_task" else "",
            )
        )

    # List examples mode
    if list_flag:
        print_header("Available DAZZLE Examples", "Ready-to-use project templates")
        display_options_table(example_options, show_numbers=True)

        console.print(Text("Usage:", style="bold"))
        console.print(
            Text("  dazzle example                          ", style="cyan")
            + Text("# Interactive selection", style="bright_black")
        )
        console.print(
            Text("  dazzle example <name>                   ", style="cyan")
            + Text("# Create from example", style="bright_black")
        )
        console.print(
            Text("  dazzle example <name> --path ./my-app   ", style="cyan")
            + Text("# Custom directory", style="bright_black")
        )
        console.print()
        return

    # Interactive example selection
    if name is None:
        print_header("DAZZLE Project Creator", "Create a new project from an example template")

        name = select_interactive(
            example_options,
            title="Select an Example",
            subtitle="Use up/down arrows to navigate, Enter to select",
        )

        if name is None:
            print_info("Selection cancelled.")
            return

        print_success(f"Selected example: {name}")
        console.print()

    # Validate example exists
    if name not in examples_list:
        print_error(f"Example '{name}' not found.")
        console.print(Text(f"Available: {', '.join(examples_list)}", style="bright_black"))
        raise typer.Exit(code=1)

    # Determine target directory
    if path is None:
        path = f"./{name}"

    target_dir = Path(path).resolve()

    # Check if directory exists
    if target_dir.exists():
        if reset:
            # Reset mode: smart overwrite
            print_divider()
            console.print()
            print_step(1, 3, "Resetting project...")

            from dazzle.core.init_impl import reset_project

            try:
                result = reset_project(target_dir, from_example=name)

                # Report what happened
                if result["deleted"]:
                    print_success(f"Deleted {len(result['deleted'])} generated files")
                if result["overwritten"]:
                    print_success(f"Overwrote {len(result['overwritten'])} source files")
                if result["added"]:
                    print_success(f"Added {len(result['added'])} new files")
                if result["preserved"]:
                    print_info(f"Preserved {len(result['preserved'])} user files")

                console.print()

            except Exception as e:
                print_error(f"Reset failed: {e}")
                raise typer.Exit(code=1)

        else:
            print_error(f"Directory '{target_dir}' already exists.")
            console.print(
                Text(
                    "Use --reset to overwrite source files and delete build artifacts.",
                    style="bright_black",
                )
            )
            console.print(Text("Or choose a different path with --path.", style="bright_black"))
            raise typer.Exit(code=1)
    else:
        # Normal creation mode
        try:
            # Create project
            print_divider()
            console.print()
            print_step(1, 3, "Creating project structure...")

            init_project(
                target_dir=target_dir,
                project_name=name,
                from_example=name,
            )

            print_success(f"Project created: {target_dir}")
            print_success("Initialized git repository")
            print_success("Created LLM context files")
            console.print()

        except Exception as e:
            print_error(f"Error creating project: {e}")
            import traceback

            traceback.print_exc()
            raise typer.Exit(code=1)

    # Common post-processing for both reset and create modes
    try:
        # Verify project setup
        print_step(2, 3, "Verifying project setup...")
        from dazzle.core.init_impl import verify_project

        if not verify_project(target_dir):
            print_warning("DSL validation errors detected")
            console.print(
                Text(
                    "Run 'dazzle validate' in the project directory for details",
                    style="bright_black",
                )
            )
            raise typer.Exit(code=1)

        print_success("Verification passed")
        console.print()

        # Print next steps
        print_step(3, 3, "Ready!")
        console.print()

        print_divider("=")
        print_header("Next Steps")

        console.print(Text(f"  cd {path}", style="cyan bold"))
        console.print(Text("  dazzle serve", style="cyan bold"))
        console.print()
        console.print(Text("This will start:", style="bright_black"))
        console.print(Text("  • Backend API at http://localhost:8000", style="bright_black"))
        console.print(Text("  • Frontend UI at http://localhost:3000", style="bright_black"))
        console.print(Text("  • API docs at http://localhost:8000/docs", style="bright_black"))

        console.print()
        console.print()
        print_divider("=")
        console.print(Text("Ready for LLM-driven development!", style="bold bright_cyan"))
        print_divider("=")
        console.print()

    except Exception as e:
        print_error(f"Error: {e}")
        import traceback

        traceback.print_exc()
        raise typer.Exit(code=1)


# Export all command functions
__all__ = [
    # Helper functions
    "_is_directory_empty",
    "_print_human_diagnostics",
    "_print_vscode_diagnostics",
    "_print_vscode_parse_error",
    "_print_analysis_summary",
    "_run_interactive_qa",
    "_generate_dsl",
    # Command functions
    "init_command",
    "validate_command",
    "lint_command",
    "inspect_command",
    "layout_plan_command",
    "analyze_spec_command",
    "example_command",
]
