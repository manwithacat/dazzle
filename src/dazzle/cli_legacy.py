import os
import platform
import sys
from pathlib import Path
from typing import Any

import typer

from dazzle.core.changes import ChangeSet, detect_changes
from dazzle.core.errors import DazzleError, ParseError
from dazzle.core.fileset import discover_dsl_files
from dazzle.core.init import InitError, init_project, list_examples
from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules
from dazzle.core.stacks import BUILTIN_STACKS
from dazzle.core.state import compute_dsl_hashes, load_state, save_state

# Version is defined here as the single source of truth
__version__ = "0.3.0"


def _get_available_stacks() -> list[str]:
    """Get list of available stack preset names."""
    return list(BUILTIN_STACKS.keys())


def get_version() -> str:
    """Get DAZZLE version from package metadata or fallback to __version__."""
    try:
        from importlib.metadata import version

        return version("dazzle")
    except Exception:
        # Fallback if not installed as package
        return __version__


def version_callback(value: bool) -> None:
    """Display version and environment information."""
    if value:
        # Get DAZZLE version
        dazzle_version = get_version()

        # Get Python version
        python_version = platform.python_version()
        python_impl = platform.python_implementation()

        # Get installation location
        try:
            import dazzle

            install_location = Path(dazzle.__file__).parent.parent.parent
        except Exception:
            install_location = Path.cwd()

        # Check if installed via pip (editable or not)
        install_method = "unknown"
        try:
            from importlib.metadata import distribution

            dist = distribution("dazzle")
            if dist.read_text("direct_url.json"):
                install_method = "pip (editable)"
            else:
                install_method = "pip"
        except Exception:
            # Check if we're in development directory
            if (install_location / "pyproject.toml").exists():
                install_method = "development"

        # Check LSP server availability
        lsp_available = False
        try:
            # Suppress verbose pygls logging during import check
            # MUST set logging level BEFORE importing pygls/dazzle.lsp.server
            import logging

            logging.getLogger("pygls.feature_manager").setLevel(logging.ERROR)
            logging.getLogger("pygls").setLevel(logging.ERROR)

            import dazzle.lsp.server

            lsp_available = True
        except ImportError:
            pass

        # Check available stacks
        available_stacks = []
        try:
            from dazzle.stacks import list_backends

            available_stacks = sorted(list_backends())
        except Exception:
            pass

        # Check LLM support
        llm_available = False
        llm_providers = []
        try:
            import anthropic  # noqa: F401 - intentional import for availability check

            llm_providers.append("anthropic")
            llm_available = True
        except ImportError:
            pass
        try:
            import openai  # noqa: F401 - intentional import for availability check

            llm_providers.append("openai")
            llm_available = True
        except ImportError:
            pass

        # Output version information
        typer.echo(f"DAZZLE version {dazzle_version}")
        typer.echo("")
        typer.echo("Environment:")
        typer.echo(f"  Python:        {python_impl} {python_version}")
        typer.echo(f"  Platform:      {platform.system()} {platform.release()}")
        typer.echo(f"  Architecture:  {platform.machine()}")
        typer.echo("")
        typer.echo("Installation:")
        typer.echo(f"  Method:        {install_method}")
        typer.echo(f"  Location:      {install_location}")
        typer.echo("")
        typer.echo("Features:")
        typer.echo(
            f"  LSP Server:    {'✓ Available' if lsp_available else '✗ Not available (install with: pip install dazzle)'}"
        )
        typer.echo(
            f"  LLM Support:   {'✓ Available (' + ', '.join(llm_providers) + ')' if llm_available else '✗ Not available (install with: pip install dazzle[llm])'}"
        )
        typer.echo("")
        if available_stacks:
            typer.echo("Available Stacks:")
            for stack in available_stacks:
                typer.echo(f"  - {stack}")
        else:
            typer.echo("Available Stacks: None")

        raise typer.Exit()


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


def _is_directory_empty(directory: Path) -> bool:
    """
    Check if directory is empty (or has only files we commonly allow).

    A directory is considered "empty" for init purposes if it contains:
    - No files at all, OR
    - Only .git directory, OR
    - Only .git and common files (.gitignore, README.md, LICENSE, .DS_Store)

    Args:
        directory: Path to check

    Returns:
        True if directory is empty or only has allowed files
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


app = typer.Typer(
    help="""DAZZLE – DSL-first app generator

Command Types:
  • Project Creation: init
    → Initialize in current directory (or create new)

  • Project Operations: validate, build, lint, stacks
    → Operate in CURRENT directory (must have dazzle.toml)

  • Runtime: dnr serve
    → Run your app with Dazzle Native Runtime
""",
    no_args_is_help=True,
)


@app.callback()
def main_callback(
    version: bool | None = typer.Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version and environment information",
    ),
) -> None:
    """DAZZLE CLI main callback for global options."""
    pass


@app.command()
def init(
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
        for example in examples:
            typer.echo(f"  {example}")
        typer.echo("\nUse: dazzle init --from <example>  # Current directory")
        typer.echo("Or:  dazzle init ./my-project --from <example>  # New directory")
        return

    # Determine target directory
    if path is None:
        # No path provided, use current directory
        target = Path(".").resolve()

        # Check if current directory is suitable
        if not _is_directory_empty(target) and not here:
            # Directory is not empty
            typer.echo(f"Error: Current directory is not empty: {target}", err=True)
            typer.echo("", err=True)

            # Show what's in the directory
            contents = [item.name for item in target.iterdir() if not item.name.startswith(".")]
            if contents:
                typer.echo("Current directory contains:", err=True)
                for item in sorted(contents)[:5]:  # Show first 5 items
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
        # Path provided, create new directory
        target = Path(path).resolve()

    try:
        # Determine if we're initializing in place
        # If path is None, we're in current directory and already checked it's suitable
        allow_existing = path is None

        # Progress callback to show user what's happening
        def progress(msg: str) -> None:
            typer.echo(msg)

        typer.echo("")  # Blank line before progress

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

        # Success message
        typer.echo("")  # Blank line after progress
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
        typer.echo("  dazzle dnr serve  # Run your app with Dazzle Native Runtime")

        # Check if MCP server is registered and suggest setup if not
        try:
            from dazzle.mcp.setup import check_mcp_server

            status = check_mcp_server()
            if not status.get("registered"):
                typer.echo("\n💡 Tip: Enable DAZZLE MCP server for Claude Code:")
                typer.echo("  dazzle mcp-setup")
                typer.echo("  Then restart Claude Code to access DAZZLE tools")
        except Exception:
            # Don't fail if MCP check fails
            pass

    except InitError as e:
        typer.echo(f"Initialization failed: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def validate(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m", help="Path to dazzle.toml"),
    format: str = typer.Option(
        "human", "--format", "-f", help="Output format: 'human' or 'vscode'"
    ),
) -> None:
    """
    Parse all DSL modules, resolve dependencies, and validate the merged AppSpec.

    ⚠ Operates in CURRENT directory (must contain dazzle.toml).

    Output formats:
    - human: Human-readable output (default)
    - vscode: Machine-readable format for VS Code integration (file:line:col: severity: message)
    """
    # Use manifest path to determine root directory
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

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
    # Use manifest path to determine root directory
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

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
def inspect(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    show_interfaces: bool = typer.Option(
        True, "--interfaces/--no-interfaces", help="Show module interfaces"
    ),
    show_patterns: bool = typer.Option(
        True, "--patterns/--no-patterns", help="Show detected patterns"
    ),
    show_types: bool = typer.Option(False, "--types", help="Show type catalog"),
) -> None:
    """
    Inspect AppSpec structure, module interfaces, and detected patterns.

    ⚠ Operates in CURRENT directory (must contain dazzle.toml).

    Provides insights into:
    - Module interfaces (what each module exports/imports)
    - Detected patterns (CRUD, integrations, experiences)
    - Type catalog (field types used across entities)

    Useful for understanding module boundaries and identifying boilerplate.
    """
    from dazzle.core.linker_impl import build_symbol_table
    from dazzle.core.patterns import analyze_patterns, format_pattern_report

    # Use manifest path to determine root directory
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)

        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)

        # Show module interfaces
        if show_interfaces:
            typer.echo("Module Interfaces")
            typer.echo("=" * 60)
            typer.echo()

            # Build symbol table to get module sources
            build_symbol_table(modules)

            for module in modules:
                typer.echo(f"module: {module.name}")

                # Collect exports
                entities = [e.name for e in module.fragment.entities]
                surfaces = [s.name for s in module.fragment.surfaces]
                experiences = [ex.name for ex in module.fragment.experiences]
                services = [srv.name for srv in module.fragment.services]
                foreign_models = [fm.name for fm in module.fragment.foreign_models]
                integrations = [i.name for i in module.fragment.integrations]

                if entities:
                    typer.echo("  exports:")
                    if entities:
                        typer.echo(f"    entities: {', '.join(entities)}")
                    if surfaces:
                        typer.echo(f"    surfaces: {', '.join(surfaces)}")
                    if experiences:
                        typer.echo(f"    experiences: {', '.join(experiences)}")
                    if services:
                        typer.echo(f"    services: {', '.join(services)}")
                    if foreign_models:
                        typer.echo(f"    foreign_models: {', '.join(foreign_models)}")
                    if integrations:
                        typer.echo(f"    integrations: {', '.join(integrations)}")
                else:
                    typer.echo("  exports: (none)")

                # Show imports
                if module.uses:
                    typer.echo("  imports:")
                    for used_module in module.uses:
                        typer.echo(f"    from {used_module}")
                else:
                    typer.echo("  imports: (none)")

                typer.echo()

        # Show detected patterns
        if show_patterns:
            patterns = analyze_patterns(appspec)
            report = format_pattern_report(patterns)
            typer.echo(report)

        # Show type catalog
        if show_types:
            typer.echo("\nType Catalog")
            typer.echo("=" * 60)

            type_catalog = appspec.type_catalog
            if not type_catalog:
                typer.echo("No types defined.")
            else:
                for field_name, types in sorted(type_catalog.items()):
                    typer.echo(f"\n{field_name}:")
                    for field_type in types:
                        type_desc = f"  {field_type.kind.value}"
                        if field_type.max_length:
                            type_desc += f"({field_type.max_length})"
                        elif field_type.precision:
                            type_desc += f"({field_type.precision},{field_type.scale})"
                        elif field_type.enum_values:
                            type_desc += f"[{','.join(field_type.enum_values)}]"
                        elif field_type.ref_entity:
                            type_desc += f" -> {field_type.ref_entity}"
                        typer.echo(type_desc)

            # Show type conflicts if any
            conflicts = appspec.get_field_type_conflicts()
            if conflicts:
                typer.echo("\n⚠ Type Conflicts:")
                for conflict in conflicts:
                    typer.echo(f"  {conflict}")

    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@app.command(name="layout-plan")
def layout_plan(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    workspace: str | None = typer.Option(
        None, "--workspace", "-w", help="Specific workspace to show (shows all if not specified)"
    ),
    persona: str | None = typer.Option(
        None, "--persona", "-p", help="Persona to generate plan for"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    explain: bool = typer.Option(False, "--explain", "-e", help="Explain archetype selection"),
) -> None:
    """
    Generate and visualize layout plans from workspace definitions.

    ⚠ Operates in CURRENT directory (must contain dazzle.toml).

    Shows:
    - Selected layout archetype
    - Surface allocation
    - Attention signal assignments
    - Attention budget analysis
    - Warnings for over-budget signals

    Use --explain to see why an archetype was selected and scores for alternatives.

    Useful for understanding how workspaces map to UI layouts.
    """
    import json as json_lib

    from dazzle.ui.layout_engine import (
        build_layout_plan,
        enrich_app_spec_with_layouts,
        explain_archetype_selection,
    )

    # Use manifest path to determine root directory
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)

        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)

        # Convert workspaces to layouts if needed
        if not appspec.ux or not appspec.ux.workspaces:
            if appspec.workspaces:
                appspec = enrich_app_spec_with_layouts(appspec)
            else:
                typer.echo("No workspaces defined in DSL.", err=True)
                raise typer.Exit(code=1)

        # Filter to specific workspace if requested
        workspaces_to_show = appspec.ux.workspaces if appspec.ux else []
        if workspace:
            workspaces_to_show = [ws for ws in workspaces_to_show if ws.id == workspace]
            if not workspaces_to_show:
                typer.echo(f"Workspace '{workspace}' not found.", err=True)
                raise typer.Exit(code=1)

        # Find persona if specified
        persona_obj = None
        if persona and appspec.ux and appspec.ux.personas:
            persona_objs = [p for p in appspec.ux.personas if p.id == persona]
            if persona_objs:
                persona_obj = persona_objs[0]
            else:
                typer.echo(f"Warning: Persona '{persona}' not found, using default plan.", err=True)

        # Generate and display plans
        plans = {}
        explanations = {}
        for ws in workspaces_to_show:
            plan = build_layout_plan(ws, persona=persona_obj)
            plans[ws.id] = plan

            # Get explanation if requested
            if explain:
                explanations[ws.id] = explain_archetype_selection(ws, persona_obj)

            if not json_output:
                # Human-readable output
                typer.echo(f"\nWorkspace: {ws.id}")
                typer.echo("=" * 60)
                typer.echo(f"Label: {ws.label}")
                if persona:
                    typer.echo(f"Persona: {persona}")
                typer.echo(f"Archetype: {plan.archetype.value}")
                typer.echo(f"Attention Budget: {ws.attention_budget}")
                typer.echo()

                # Show explanation if requested
                if explain and ws.id in explanations:
                    exp = explanations[ws.id]
                    typer.echo("Selection Explanation:")
                    typer.echo(f"  Reason: {exp.reason}")
                    if exp.engine_hint_used:
                        typer.echo("  (engine_hint override)")
                    if exp.persona_applied:
                        typer.echo("  (persona biases applied)")
                    typer.echo()

                    typer.echo("  Signal Profile:")
                    for key, value in exp.signal_profile.items():
                        typer.echo(f"    {key}: {value:.2f}")
                    typer.echo()

                    typer.echo("  Archetype Scores (ranked):")
                    for score in exp.all_scores:
                        marker = "→" if score.archetype == exp.selected else " "
                        typer.echo(f"  {marker} {score.archetype.value}: {score.score:.2f}")
                        typer.echo(f"      {score.reason}")
                    typer.echo()

                # Show signals
                typer.echo("Attention Signals:")
                for signal in ws.attention_signals:
                    typer.echo(f"  - {signal.id} ({signal.kind.value})")
                    typer.echo(f"    Weight: {signal.attention_weight}")
                    typer.echo(f"    Source: {signal.source}")
                typer.echo()

                # Show surface allocation
                typer.echo("Surface Allocation:")
                for surface in plan.surfaces:
                    typer.echo(f"  - {surface.id} (priority: {surface.priority})")
                    typer.echo(f"    Capacity: {surface.capacity}")
                    if surface.assigned_signals:
                        typer.echo(f"    Signals: {', '.join(surface.assigned_signals)}")
                    else:
                        typer.echo("    Signals: (none)")
                typer.echo()

                # Show warnings
                if plan.warnings:
                    typer.echo("Warnings:")
                    for warning in plan.warnings:
                        typer.echo(f"  - {warning}")
                    typer.echo()

                # Show over-budget signals
                if plan.over_budget_signals:
                    typer.echo("Over-Budget Signals:")
                    for signal_id in plan.over_budget_signals:
                        typer.echo(f"  - {signal_id}")
                    typer.echo()

        if json_output:
            # JSON output
            output = {}
            for ws_id, plan in plans.items():
                ws_output = {
                    "workspace_id": plan.workspace_id,
                    "persona_id": plan.persona_id,
                    "archetype": plan.archetype.value,
                    "surfaces": [
                        {
                            "id": s.id,
                            "archetype": s.archetype.value,
                            "capacity": s.capacity,
                            "priority": s.priority,
                            "assigned_signals": s.assigned_signals,
                            "constraints": s.constraints,
                        }
                        for s in plan.surfaces
                    ],
                    "over_budget_signals": plan.over_budget_signals,
                    "warnings": plan.warnings,
                    "metadata": plan.metadata,
                }

                # Add explanation if requested
                if explain and ws_id in explanations:
                    exp = explanations[ws_id]
                    ws_output["explanation"] = {
                        "selected": exp.selected.value,
                        "reason": exp.reason,
                        "signal_profile": exp.signal_profile,
                        "engine_hint_used": exp.engine_hint_used,
                        "persona_applied": exp.persona_applied,
                        "all_scores": [
                            {
                                "archetype": s.archetype.value,
                                "score": s.score,
                                "reason": s.reason,
                            }
                            for s in exp.all_scores
                        ],
                    }

                output[ws_id] = ws_output
            typer.echo(json_lib.dumps(output, indent=2))

    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        import traceback

        traceback.print_exc()
        raise typer.Exit(code=1)


@app.command()
def stacks() -> None:
    """
    List all available stacks (technology combinations).

    Shows both preset stacks and available stack implementations.

    ⚠ No directory required - shows available options.
    """
    from dazzle.core.stacks import get_stack_preset, list_stack_presets
    from dazzle.stacks import get_backend, list_backends

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
                typer.echo("    (Error loading implementation)")


@app.command()
def build(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    stack: str | None = typer.Option(
        None,
        "--stack",
        "-s",
        help="Stack preset or comma-separated list (e.g., 'micro' or 'django_api,nextjs')",
    ),
    backend: str | None = typer.Option(
        None, "--backend", "-b", help="DEPRECATED: Use --stack instead"
    ),
    backends: str | None = typer.Option(None, "--backends", help="DEPRECATED: Use --stack instead"),
    out: str = typer.Option("./build", "--out", "-o", help="Output directory"),
    incremental: bool = typer.Option(
        False, "--incremental", "-i", help="Incremental build (only regenerate changed parts)"
    ),
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
    from dazzle.core.errors import BackendError
    from dazzle.core.stacks import StackError, resolve_stack_backends, validate_stack_backends
    from dazzle.stacks import get_backend

    # Use manifest path to determine root directory
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

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
            # Check for DNR - it's a runtime, not a code generator
            if mf.stack.name.lower() == "dnr":
                typer.echo("This project uses DNR (Dazzle Native Runtime).")
                typer.echo("")
                typer.echo("DNR runs your DSL directly without code generation.")
                typer.echo("To run your app, use:")
                typer.echo("")
                typer.echo("  dazzle dnr serve")
                typer.echo("")
                typer.echo("To generate code for a specific stack, specify --stack:")
                typer.echo("  dazzle build --stack micro")
                typer.echo("  dazzle build --stack base")
                return
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
                diff_changeset = detect_changes(prev_state, appspec, current_hashes)

                if diff_changeset.is_empty():
                    typer.echo("No changes detected since last build.")
                else:
                    typer.echo("Changes detected:")
                    typer.echo(diff_changeset.summary())
                    typer.echo("\nRun without --diff to apply changes.")
            else:
                typer.echo("No previous build state found. This would be a full build.")
            return

        # Build each backend in order
        base_output_dir = Path(out).resolve()
        artifacts: dict[str, Any] = {}  # Shared artifacts between backends

        for backend_name in backend_list:
            typer.echo(f"\n{'=' * 60}")
            typer.echo(f"Building backend: {backend_name}")
            typer.echo(f"{'=' * 60}\n")

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
            changeset: ChangeSet | None = None

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
                typer.echo(f"  ⚠ Backend '{backend_name}' does not support incremental builds")
                incremental = False

            # Generate artifacts
            try:
                if incremental and changeset:
                    typer.echo("  Generating incrementally...")
                    if hasattr(backend_impl, "generate_incremental"):
                        backend_impl.generate_incremental(appspec, output_dir, changeset)
                    else:
                        backend_impl.generate(appspec, output_dir)
                else:
                    typer.echo("  Generating...")
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

        typer.echo(f"\n{'=' * 60}")
        typer.echo(f"✓ Build complete: {', '.join(backend_list)}")
        typer.echo(f"{'=' * 60}")

    except StackError as e:
        typer.echo(f"Stack error: {e}", err=True)
        raise typer.Exit(code=1)
    except BackendError as e:
        typer.echo(f"Backend error: {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        import traceback

        typer.echo(f"Unexpected error during build: {e}", err=True)
        traceback.print_exc()
        raise typer.Exit(code=1)


@app.command()
def infra(
    type: str | None = typer.Argument(None, help="DEPRECATED: Use 'dazzle build --stack' instead"),
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    out: str | None = typer.Option(None, "--out", "-o", help="Output directory"),
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
    output_json: bool = typer.Option(
        False, "--output-json", help="Output analysis as JSON for programmatic use"
    ),
    provider: str = typer.Option(
        "anthropic", "--provider", "-p", help="LLM provider (anthropic|openai)"
    ),
    model: str | None = typer.Option(
        None, "--model", "-m", help="Model name (defaults to provider's default)"
    ),
    interactive: bool = typer.Option(
        True, "--interactive/--no-interactive", help="Run interactive Q&A after analysis"
    ),
    generate_dsl: bool = typer.Option(
        False,
        "--generate-dsl",
        help="Generate DSL from analysis (requires --no-interactive or answers)",
    ),
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
    import json

    from dazzle.llm import LLMProvider, SpecAnalyzer

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

    # Check for API key (or Claude CLI fallback)
    import shutil

    claude_cli_available = shutil.which("claude") is not None

    if provider_enum == LLMProvider.ANTHROPIC:
        if not os.environ.get("ANTHROPIC_API_KEY") and not claude_cli_available:
            typer.echo("Error: No authentication method available.", err=True)
            typer.echo("Options:", err=True)
            typer.echo("  1. Set ANTHROPIC_API_KEY: export ANTHROPIC_API_KEY=your-key", err=True)
            typer.echo("  2. Install Claude CLI: https://claude.ai/download", err=True)
            typer.echo("     (Uses your Claude subscription, no API key needed)", err=True)
            raise typer.Exit(code=1)
    elif provider_enum == LLMProvider.OPENAI:
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
            analyzer_kwargs["model"] = model

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
        typer.echo(
            "Install with: pip install 'dazzle[llm]' or pip install anthropic openai", err=True
        )
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"Error during analysis: {e}", err=True)
        raise typer.Exit(code=1)


def _print_analysis_summary(analysis: Any) -> None:
    """Print human-readable analysis summary."""

    typer.echo("\n" + "=" * 60)
    typer.echo("📊 Specification Analysis Results")
    typer.echo("=" * 60 + "\n")

    # State machines
    if analysis.state_machines:
        typer.echo(f"🔄 State Machines: {len(analysis.state_machines)}")
        for sm in analysis.state_machines:
            typer.echo(f"   • {sm.entity}.{sm.field}: {', '.join(sm.states)}")
            typer.echo(f"     - {len(sm.transitions_found)} transitions found")
            if sm.transitions_implied_but_missing:
                typer.echo(
                    f"     - ⚠ {len(sm.transitions_implied_but_missing)} transitions missing"
                )
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
        rule_types: dict[str, int] = {}
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
            typer.echo(
                f"   • {category.category} ({category.priority}): {len(category.questions)} questions"
            )
        typer.echo()

    # Coverage stats
    sm_coverage = analysis.get_state_machine_coverage()
    crud_coverage = analysis.get_crud_coverage()

    typer.echo("📈 Coverage:")
    typer.echo(f"   • State Machines: {sm_coverage['coverage_percent']:.1f}%")
    typer.echo(f"   • CRUD Operations: {crud_coverage['coverage_percent']:.1f}%")
    typer.echo()


def _run_interactive_qa(analysis: Any) -> dict[str, str]:
    """Run interactive Q&A session."""
    answers: dict[str, str] = {}

    if analysis.get_question_count() == 0:
        typer.echo("✓ No clarifying questions needed.")
        return answers

    typer.echo("\n" + "=" * 60)
    typer.echo("💬 Interactive Q&A")
    typer.echo("=" * 60 + "\n")

    for category in analysis.clarifying_questions:
        typer.echo(f"\n📋 {category.category} (Priority: {category.priority})")
        typer.echo("-" * 60)

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

    typer.echo("\n" + "=" * 60)
    typer.echo(f"✓ Q&A complete! {len(answers)} questions answered.")
    typer.echo("=" * 60 + "\n")

    return answers


def _generate_dsl(analysis: Any, answers: dict[str, str], spec_file: Path) -> None:
    """Generate DSL from analysis and answers."""
    from dazzle.llm import DSLGenerator

    # Derive module/app names from spec file location
    spec_dir = spec_file.parent
    module_name = spec_dir.name if spec_dir.name != "." else "app"

    # Try to read app name from spec
    spec_content = spec_file.read_text()
    app_name = module_name.replace("_", " ").title()

    # Look for app name in spec (first line or header)
    for line in spec_content.split("\n")[:5]:
        if line.startswith("#") and not line.startswith("##"):
            # Found title
            app_name = line.lstrip("#").strip()
            break

    # Generate DSL
    generator = DSLGenerator(analysis, answers)
    dsl_code = generator.generate(module_name, app_name)

    # Determine output path
    output_dir = spec_dir / "dsl"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "generated.dsl"

    # Write DSL
    output_path.write_text(dsl_code)

    typer.echo(f"✓ DSL generated: {output_path}")
    typer.echo(f"   Module: {module_name}")
    typer.echo(f"   App: {app_name}")
    typer.echo("\nNext steps:")
    typer.echo(f"   1. Review and customize {output_path}")
    typer.echo("   2. Run: dazzle validate")
    typer.echo("   3. Run: dazzle build")


@app.command()
def example(
    name: str | None = typer.Argument(
        None, help="Example name (e.g., 'simple_task', 'support_tickets')"
    ),
    stack: str | None = typer.Option(
        None, "--stack", "-s", help="Stack preset to use (e.g., 'micro', 'nextjs_onebox')"
    ),
    path: str | None = typer.Option(
        None, "--path", "-p", help="Directory to create (default: ./<example-name>)"
    ),
    reset: bool = typer.Option(
        False,
        "--reset",
        "-r",
        help="Reset existing directory: overwrite source files, delete build artifacts, preserve user files",
    ),
    list_flag: bool = typer.Option(False, "--list", "-l", help="List available examples"),
    list_stacks: bool = typer.Option(False, "--list-stacks", help="List available stack presets"),
    no_build: bool = typer.Option(False, "--no-build", help="Skip automatic build after creation"),
) -> None:
    """
    Create a new project from a built-in example with interactive selection.

    ⚠ Creates a NEW directory (default: ./<example-name>).

    This command provides an interactive way to explore and use DAZZLE examples.
    It creates a complete project directory with DSL files, ready for LLM-driven
    development.

    Interactive modes:
        dazzle example                        # Interactive selection with arrow keys
        dazzle example simple_task            # Select stack for simple_task
        dazzle example simple_task --stack nextjs_onebox  # Direct creation

    List options:
        dazzle example --list                 # List available examples
        dazzle example --list-stacks          # List available stack presets

    Reset mode (--reset):
        Resets an existing directory to match the example template:
        • Overwrites DSL source files with example versions
        • Deletes build/ directory (generated artifacts)
        • Deletes .dazzle/ directory (build state)
        • Preserves user-created files not in the example
        • Preserves .git/, .vscode/, .env files

    Examples:
        dazzle example                               # Interactive mode
        dazzle example simple_task                   # Select stack for example
        dazzle example simple_task --stack micro     # Create with specific stack
        dazzle example simple_task --path ./my-app   # Create in custom directory
        dazzle example simple_task --reset           # Reset existing project
        dazzle example --no-build                    # Skip automatic build
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
    from dazzle.core.init import list_examples
    from dazzle.core.stacks import get_stack_preset

    # List stacks
    if list_stacks:
        stacks = _get_available_stacks()
        if not stacks:
            print_error("No stack presets available.")
            return

        print_header("Available Stack Presets", "Choose a technology stack for your project")

        stack_options = []
        for stack_name in stacks:
            preset = get_stack_preset(stack_name)
            desc = preset.description if preset else ""
            badge = ""
            if stack_name == "nextjs_onebox":
                badge = "NEW"
            elif stack_name == "micro":
                badge = "RECOMMENDED"

            stack_options.append(
                SelectOption(
                    value=stack_name,
                    label=stack_name,
                    description=desc,
                    badge=badge,
                )
            )

        display_options_table(stack_options, show_numbers=True)

        console.print(
            Text("Usage: ", style="bright_black")
            + Text("dazzle example <name> --stack <stack-name>", style="cyan")
        )
        console.print()
        return

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
            + Text("# Select stack for example", style="bright_black")
        )
        console.print(
            Text("  dazzle example <name> --stack <stack>   ", style="cyan")
            + Text("# Direct creation", style="bright_black")
        )
        console.print()
        return

    # Interactive example selection
    if name is None:
        print_header("DAZZLE Project Creator", "Create a new project from an example template")

        name = select_interactive(
            example_options,
            title="Select an Example",
            subtitle="Use ↑/↓ arrows to navigate, Enter to select",
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

    # Interactive stack selection
    if stack is None:
        stacks = _get_available_stacks()
        if not stacks:
            print_error("No compatible stack presets available.")
            raise typer.Exit(code=1)

        stack_options = []
        for stack_name in stacks:
            preset = get_stack_preset(stack_name)
            desc = preset.description if preset else ""

            badge = ""
            if stack_name == "nextjs_onebox":
                badge = "NEW"
            elif stack_name == "micro":
                badge = "RECOMMENDED"

            stack_options.append(
                SelectOption(
                    value=stack_name,
                    label=stack_name,
                    description=desc,
                    badge=badge,
                )
            )

        stack = select_interactive(
            stack_options,
            title="Select a Stack",
            subtitle="Choose the technology stack for your project",
        )

        if stack is None:
            print_info("Selection cancelled.")
            return

        print_success(f"Selected stack: {stack}")
        console.print()

    # Validate stack
    preset = get_stack_preset(stack)
    if not preset:
        print_error(f"Stack '{stack}' not found.")
        console.print(
            Text(
                "Use 'dazzle example --list-stacks' to see available stacks.", style="bright_black"
            )
        )
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
            print_step(1, 4, "Resetting project...")

            from dazzle.core.init import reset_project

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

            # Update dazzle.toml with stack configuration
            manifest_path = target_dir / "dazzle.toml"
            if manifest_path.exists():
                manifest_content = manifest_path.read_text()
                if "[stack]" not in manifest_content:
                    stack_section = f'\n[stack]\nname = "{stack}"\n'
                    manifest_path.write_text(manifest_content + stack_section)
                else:
                    import re

                    manifest_content = re.sub(
                        r'name = "[^"]*"',
                        f'name = "{stack}"',
                        manifest_content,
                        count=1,
                        flags=re.MULTILINE,
                    )
                    manifest_path.write_text(manifest_content)

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
            print_step(1, 4, "Creating project structure...")

            from dazzle.core.init import init_project

            init_project(
                target_dir=target_dir,
                project_name=name,
                from_example=name,
            )

            # Update dazzle.toml with stack configuration
            manifest_path = target_dir / "dazzle.toml"
            if manifest_path.exists():
                manifest_content = manifest_path.read_text()
                if "[stack]" not in manifest_content:
                    stack_section = f'\n[stack]\nname = "{stack}"\n'
                    manifest_path.write_text(manifest_content + stack_section)
                else:
                    import re

                    manifest_content = re.sub(
                        r'name = "[^"]*"',
                        f'name = "{stack}"',
                        manifest_content,
                        count=1,
                        flags=re.MULTILINE,
                    )
                    manifest_path.write_text(manifest_content)

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
        print_step(2, 4, "Verifying project setup...")
        from dazzle.core.init import verify_project

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

        # Build the project
        if not no_build:
            print_step(3, 4, "Building project...")
            import subprocess

            build_result = subprocess.run(
                ["python3", "-m", "dazzle.cli", "build"],
                cwd=target_dir,
                capture_output=True,
                text=True,
            )

            if build_result.returncode == 0:
                print_success("Build complete")
            else:
                print_warning("Build failed")
                if build_result.stderr:
                    console.print(Text(build_result.stderr, style="red"))
                console.print(
                    Text("You can build manually with 'dazzle build'", style="bright_black")
                )
        else:
            print_step(3, 4, "Skipping build (--no-build)")

        console.print()

        # Print next steps
        print_step(4, 4, "Ready!")
        console.print()

        print_divider("═")
        print_header("Next Steps")

        console.print(Text(f"  cd {path}", style="cyan bold"))

        if no_build:
            console.print(Text("  dazzle build", style="cyan"))

        # Stack-specific instructions
        if "nextjs_onebox" in preset.backends:
            console.print()
            console.print(Text("Next.js Application:", style="bold green"))
            console.print(Text("  cd build/<project-name>", style="cyan"))
            console.print(Text("  npm install", style="cyan"))
            console.print(Text("  npm run db:generate", style="cyan"))
            console.print(Text("  npm run db:push", style="cyan"))
            console.print(Text("  npm run dev", style="cyan"))

        if "django_micro_modular" in preset.backends:
            console.print()
            console.print(Text("Django Application:", style="bold green"))
            console.print(Text("  cd build/<project-name>", style="cyan"))
            console.print(Text("  source .venv/bin/activate", style="cyan"))
            console.print(Text("  python manage.py runserver", style="cyan"))
            console.print(
                Text("\nAdmin credentials: See .admin_credentials file", style="bright_black")
            )

        if "express_micro" in preset.backends:
            console.print()
            console.print(Text("Express Application:", style="bold green"))
            console.print(Text("  cd build/<project-name>", style="cyan"))
            console.print(Text("  npm install", style="cyan"))
            console.print(Text("  npm start", style="cyan"))

        if "openapi" in preset.backends:
            console.print()
            console.print(Text("OpenAPI spec:", style="bold"))
            console.print(Text("  View: build/openapi/openapi.yaml", style="cyan"))

        if "docker" in preset.backends:
            console.print()
            console.print(Text("Docker:", style="bold"))
            console.print(Text("  cd build/docker", style="cyan"))
            console.print(Text("  docker compose up -d", style="cyan"))

        console.print()
        print_divider("═")
        console.print(Text("🚀 Ready for LLM-driven development!", style="bold bright_cyan"))
        print_divider("═")
        console.print()

    except Exception as e:
        print_error(f"Error: {e}")
        import traceback

        traceback.print_exc()
        raise typer.Exit(code=1)


# Vocabulary management commands
vocab_app = typer.Typer(help="Manage app-local vocabulary (macros, aliases, patterns)")
app.add_typer(vocab_app, name="vocab")


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
    from pathlib import Path

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
    from pathlib import Path

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
    from pathlib import Path

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


@app.command()
def mcp(
    working_dir: Path = typer.Option(  # noqa: B008
        None,
        "--working-dir",
        help="Project root directory (default: current directory)",
    ),
) -> None:
    """
    Run DAZZLE MCP server.

    Starts the MCP (Model Context Protocol) server that provides tools
    for working with DAZZLE projects from Claude Code.
    """
    import asyncio

    from dazzle.mcp.server import run_server

    # Use provided directory or current directory
    project_root = working_dir.resolve() if working_dir else Path.cwd()

    # Run the async server
    try:
        asyncio.run(run_server(project_root))
    except KeyboardInterrupt:
        typer.echo("\nMCP server stopped.")
    except Exception as e:
        typer.echo(f"Error running MCP server: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def mcp_setup(
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite existing MCP server config",
    ),
) -> None:
    """
    Register DAZZLE MCP server with Claude Code.

    This command registers the MCP server in your Claude Code configuration
    so that DAZZLE tools are automatically available in all projects.
    """
    from dazzle.mcp.setup import get_claude_config_path, register_mcp_server

    config_path = get_claude_config_path()
    if not config_path:
        typer.echo("Error: Could not find Claude Code config directory", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Registering MCP server at: {config_path}")

    if register_mcp_server(force=force):
        typer.echo("✅ DAZZLE MCP server registered successfully")
        typer.echo("")
        typer.echo("Next steps:")
        typer.echo("  1. Restart Claude Code")
        typer.echo("  2. Open a DAZZLE project")
        typer.echo('  3. Ask Claude: "What DAZZLE tools do you have access to?"')
    else:
        typer.echo("❌ Failed to register MCP server", err=True)
        raise typer.Exit(code=1)


@app.command()
def mcp_check() -> None:
    """
    Check DAZZLE MCP server status.

    Verifies that the MCP server is registered with Claude Code and
    shows available tools.
    """
    from dazzle.mcp.setup import check_mcp_server

    status = check_mcp_server()

    typer.echo("DAZZLE MCP Server Status")
    typer.echo("=" * 50)
    typer.echo(f"Status:        {status['status']}")
    typer.echo(f"Registered:    {'✓ Yes' if status['registered'] else '✗ No'}")

    if status["config_path"]:
        typer.echo(f"Config:        {status['config_path']}")

    if status["server_command"]:
        typer.echo(f"Command:       {status['server_command']}")

    if status["tools"]:
        typer.echo("")
        typer.echo(f"Available Tools ({len(status['tools'])}):")
        for tool in sorted(status["tools"]):
            typer.echo(f"  • {tool}")
    elif status["registered"]:
        typer.echo("")
        typer.echo("Tools: Unable to enumerate (MCP SDK not available)")

    if not status["registered"]:
        typer.echo("")
        typer.echo("💡 To register the MCP server, run: dazzle mcp-setup")
        raise typer.Exit(code=1)


# =============================================================================
# DNR (Dazzle Native Runtime) Commands
# =============================================================================

dnr_app = typer.Typer(
    help="Dazzle Native Runtime (DNR) commands for generating and serving runtime apps.",
    no_args_is_help=True,
)
app.add_typer(dnr_app, name="dnr")


@dnr_app.command("build-ui")
def dnr_build_ui(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    out: str = typer.Option("./dnr-ui", "--out", "-o", help="Output directory"),
    format: str = typer.Option(
        "vite",
        "--format",
        "-f",
        help="Output format: 'vite' (default), 'js' (split files), or 'html' (single file)",
    ),
) -> None:
    """
    Generate DNR UI artifacts from AppSpec.

    Converts AppSpec to UISpec and generates:
    - vite: Full Vite project with ES modules (production-ready)
    - js: Split HTML/JS files for development
    - html: Single HTML file with embedded runtime (quick preview)

    Examples:
        dazzle dnr build-ui                         # Vite project in ./dnr-ui
        dazzle dnr build-ui --format html -o out    # Single HTML file
        dazzle dnr build-ui --format js             # Split JS files
    """
    try:
        # Import DNR UI components
        from dazzle_dnr_ui.converters import convert_appspec_to_ui
        from dazzle_dnr_ui.runtime import (
            generate_js_app,
            generate_single_html,
            generate_vite_app,
        )
    except ImportError as e:
        typer.echo(f"DNR UI not available: {e}", err=True)
        typer.echo("Install with: pip install dazzle-dnr-ui", err=True)
        raise typer.Exit(code=1)

    # Load and build AppSpec
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)

        # Validate
        errors, warnings = lint_appspec(appspec)
        if errors:
            typer.echo("Cannot generate UI; spec has validation errors:", err=True)
            for err in errors:
                typer.echo(f"  ERROR: {err}", err=True)
            raise typer.Exit(code=1)

        for warn in warnings:
            typer.echo(f"WARNING: {warn}")

    except (ParseError, DazzleError) as e:
        typer.echo(f"Error loading spec: {e}", err=True)
        raise typer.Exit(code=1)

    # Convert to UISpec
    typer.echo(f"Converting AppSpec '{appspec.name}' to UISpec...")
    ui_spec = convert_appspec_to_ui(appspec)
    typer.echo(f"  • {len(ui_spec.workspaces)} workspace(s)")
    typer.echo(f"  • {len(ui_spec.components)} component(s)")
    typer.echo(f"  • {len(ui_spec.themes)} theme(s)")

    # Generate based on format
    output_dir = Path(out).resolve()

    if format == "vite":
        typer.echo(f"\nGenerating Vite project → {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
        files = generate_vite_app(ui_spec, str(output_dir))
        typer.echo(f"  ✓ Generated {len(files)} files")
        typer.echo("\nTo run:")
        typer.echo(f"  cd {output_dir}")
        typer.echo("  npm install")
        typer.echo("  npm run dev")

    elif format == "js":
        typer.echo(f"\nGenerating JS app → {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
        files = generate_js_app(ui_spec, str(output_dir))
        typer.echo(f"  ✓ Generated {len(files)} files")
        typer.echo("\nTo run:")
        typer.echo(f"  cd {output_dir}")
        typer.echo("  python -m http.server 8000")

    elif format == "html":
        output_file = output_dir / "index.html" if output_dir.suffix != ".html" else output_dir
        output_file.parent.mkdir(parents=True, exist_ok=True)
        typer.echo(f"\nGenerating single HTML → {output_file}")
        html = generate_single_html(ui_spec)
        output_file.write_text(html)
        typer.echo(f"  ✓ Generated {len(html)} bytes")
        typer.echo(f"\nOpen in browser: file://{output_file}")

    else:
        typer.echo(f"Unknown format: {format}", err=True)
        typer.echo("Use one of: vite, js, html", err=True)
        raise typer.Exit(code=1)


@dnr_app.command("build-api")
def dnr_build_api(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    out: str = typer.Option("./dnr-api", "--out", "-o", help="Output directory"),
    format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Output format: 'json' (spec file) or 'python' (stub module)",
    ),
) -> None:
    """
    Generate DNR API spec from AppSpec.

    Converts AppSpec to BackendSpec suitable for FastAPI runtime.

    Examples:
        dazzle dnr build-api                        # JSON spec in ./dnr-api
        dazzle dnr build-api --format python        # Python module stub
    """
    try:
        from dazzle_dnr_back.converters import convert_appspec_to_backend
        from dazzle_dnr_back.specs import BackendSpec as _BackendSpec  # noqa: F401
    except ImportError as e:
        typer.echo(f"DNR Backend not available: {e}", err=True)
        typer.echo("Install with: pip install dazzle-dnr-back", err=True)
        raise typer.Exit(code=1)
    del _BackendSpec  # Used only to verify import availability

    # Load and build AppSpec
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)

        errors, warnings = lint_appspec(appspec)
        if errors:
            typer.echo("Cannot generate API; spec has validation errors:", err=True)
            for err in errors:
                typer.echo(f"  ERROR: {err}", err=True)
            raise typer.Exit(code=1)

        for warn in warnings:
            typer.echo(f"WARNING: {warn}")

    except (ParseError, DazzleError) as e:
        typer.echo(f"Error loading spec: {e}", err=True)
        raise typer.Exit(code=1)

    # Convert to BackendSpec
    typer.echo(f"Converting AppSpec '{appspec.name}' to BackendSpec...")
    backend_spec = convert_appspec_to_backend(appspec)
    typer.echo(f"  • {len(backend_spec.entities)} entities")
    typer.echo(f"  • {len(backend_spec.services)} services")
    typer.echo(f"  • {len(backend_spec.endpoints)} endpoints")

    # Output
    output_dir = Path(out).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if format == "json":
        spec_file = output_dir / "backend-spec.json"
        typer.echo(f"\nWriting BackendSpec → {spec_file}")
        spec_file.write_text(backend_spec.model_dump_json(indent=2))
        typer.echo(f"  ✓ Written {spec_file.stat().st_size} bytes")

    elif format == "python":
        stub_file = output_dir / "api_stub.py"
        typer.echo(f"\nWriting Python stub → {stub_file}")

        stub_content = f'''"""
Auto-generated DNR API stub for {backend_spec.name}.

Usage:
    from dazzle_dnr_back.runtime import create_app_from_json
    app = create_app_from_json('backend-spec.json')

Or run directly:
    uvicorn api_stub:app --reload
"""

from pathlib import Path

try:
    from dazzle_dnr_back.runtime import create_app_from_json, FASTAPI_AVAILABLE
    if not FASTAPI_AVAILABLE:
        raise ImportError("FastAPI not installed")

    spec_path = Path(__file__).parent / "backend-spec.json"
    app = create_app_from_json(str(spec_path))

except ImportError as e:
    print(f"DNR runtime not available: {{e}}")
    print("Install with: pip install fastapi uvicorn")
    app = None
'''
        stub_file.write_text(stub_content)

        # Also write the JSON spec
        spec_file = output_dir / "backend-spec.json"
        spec_file.write_text(backend_spec.model_dump_json(indent=2))

        typer.echo("  ✓ Generated stub and spec")
        typer.echo("\nTo run:")
        typer.echo(f"  cd {output_dir}")
        typer.echo("  pip install fastapi uvicorn")
        typer.echo("  uvicorn api_stub:app --reload")

    else:
        typer.echo(f"Unknown format: {format}", err=True)
        typer.echo("Use one of: json, python", err=True)
        raise typer.Exit(code=1)


@dnr_app.command("serve")
def dnr_serve(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    port: int = typer.Option(3000, "--port", "-p", help="Frontend port"),
    api_port: int = typer.Option(8000, "--api-port", help="Backend API port"),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    ui_only: bool = typer.Option(False, "--ui-only", help="Serve UI only (static files)"),
    backend_only: bool = typer.Option(
        False,
        "--backend-only",
        help="Serve backend API only (no frontend UI)",
    ),
    db_path: str = typer.Option(".dazzle/data.db", "--db", help="SQLite database path"),
    test_mode: bool = typer.Option(
        False,
        "--test-mode",
        help="Enable test endpoints (/__test__/seed, /__test__/reset, etc.)",
    ),
    local: bool = typer.Option(
        False,
        "--local",
        help="Run locally without Docker (default is docker-first)",
    ),
    rebuild: bool = typer.Option(
        False,
        "--rebuild",
        help="Force rebuild of Docker image",
    ),
    attach: bool = typer.Option(
        False,
        "--attach",
        "-a",
        help="Run Docker container attached (stream logs to terminal)",
    ),
    single_container: bool = typer.Option(
        False,
        "--single-container",
        help="Use legacy single-container mode (combined frontend + backend)",
    ),
) -> None:
    """
    Serve DNR app (backend API + UI with live data).

    By default, runs frontend and backend in separate Docker containers.
    Use --single-container for legacy combined mode, --local to run without Docker.

    Runs:
    - FastAPI backend on api-port (default 8000) with SQLite persistence
    - Vite frontend dev server on port (default 3000) with hot reload
    - Auto-migration for schema changes
    - Interactive API docs at http://host:api-port/docs

    Examples:
        dazzle dnr serve                    # Split containers (default)
        dazzle dnr serve --attach           # Run Docker with log streaming
        dazzle dnr serve --local            # Run locally without Docker
        dazzle dnr serve --single-container # Legacy single-container mode
        dazzle dnr serve --backend-only     # API server only (for separate frontend)
        dazzle dnr serve --rebuild          # Force Docker image rebuild
        dazzle dnr serve --port 4000        # Frontend on 4000
        dazzle dnr serve --api-port 9000    # API on 9000
        dazzle dnr serve --ui-only          # Static UI only (no API)
        dazzle dnr serve --db ./my.db       # Custom database path
        dazzle dnr serve --test-mode        # Enable E2E test endpoints

    Related commands:
        dazzle dnr stop                     # Stop the running container
        dazzle dnr rebuild                  # Rebuild and restart container
        dazzle dnr logs                     # View container logs
    """
    # Resolve project path from manifest
    manifest_path = Path(manifest).resolve()
    project_root = manifest_path.parent

    # Load manifest to get auth config and project name (needed for both Docker and local modes)
    mf = None
    try:
        mf = load_manifest(manifest_path)
        auth_enabled = mf.auth.enabled
        project_name = mf.name
    except Exception:
        auth_enabled = False
        project_name = None

    # Docker-first: unless --local is specified, try Docker first
    if not local and not ui_only and not backend_only:
        try:
            from dazzle_dnr_ui.runtime import is_docker_available, run_in_docker

            if is_docker_available():
                detach = not attach  # Default to detached (no logs), --attach streams logs
                mode_desc = "single-container" if single_container else "split containers"
                auth_desc = " with auth" if auth_enabled else ""
                typer.echo(
                    f"Running in Docker mode ({mode_desc}{auth_desc}, use --local to run without Docker)"
                    if attach
                    else f"Starting Docker containers in background ({mode_desc}{auth_desc})..."
                )
                exit_code = run_in_docker(
                    project_path=project_root,
                    frontend_port=port,
                    api_port=api_port,
                    test_mode=test_mode,
                    auth_enabled=auth_enabled,
                    rebuild=rebuild,
                    detach=detach,
                    single_container=single_container,
                    project_name=project_name,
                )
                raise typer.Exit(code=exit_code)
            else:
                typer.echo("Docker not available, falling back to local mode")
                typer.echo("Install Docker for the recommended development experience")
                typer.echo()
        except ImportError:
            pass  # Docker runner not available, fall back to local

    # Local mode execution
    try:
        from dazzle_dnr_back.converters import convert_appspec_to_backend
        from dazzle_dnr_back.runtime import FASTAPI_AVAILABLE
        from dazzle_dnr_ui.converters import convert_appspec_to_ui
        from dazzle_dnr_ui.runtime import generate_single_html, run_combined_server
    except ImportError as e:
        typer.echo(f"DNR runtime not available: {e}", err=True)
        typer.echo("Install with: pip install dazzle-dnr-back dazzle-dnr-ui", err=True)
        raise typer.Exit(code=1)

    if not FASTAPI_AVAILABLE and not ui_only:
        typer.echo("FastAPI not installed. Use --ui-only or install:", err=True)
        typer.echo("  pip install fastapi uvicorn", err=True)
        raise typer.Exit(code=1)

    # Load AppSpec
    root = project_root

    try:
        # Use mf if already loaded, otherwise load it now
        if mf is None:
            mf = load_manifest(manifest_path)
            auth_enabled = mf.auth.enabled
        dsl_files = discover_dsl_files(root, mf)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)

        errors, _ = lint_appspec(appspec)
        if errors:
            typer.echo("Cannot serve; spec has validation errors:", err=True)
            for err in errors:
                typer.echo(f"  ERROR: {err}", err=True)
            raise typer.Exit(code=1)

    except (ParseError, DazzleError) as e:
        typer.echo(f"Error loading spec: {e}", err=True)
        raise typer.Exit(code=1)

    if ui_only:
        # Serve UI only with simple HTTP server
        import http.server
        import socketserver
        import tempfile

        ui_spec = convert_appspec_to_ui(appspec)
        html = generate_single_html(ui_spec)

        with tempfile.TemporaryDirectory() as tmpdir:
            html_path = Path(tmpdir) / "index.html"
            html_path.write_text(html)

            os.chdir(tmpdir)
            handler = http.server.SimpleHTTPRequestHandler
            typer.echo(f"\nServing DNR UI at http://{host}:{port}")
            typer.echo("Press Ctrl+C to stop\n")

            with socketserver.TCPServer((host, port), handler) as httpd:
                try:
                    httpd.serve_forever()
                except KeyboardInterrupt:
                    typer.echo("\nStopped.")
        return

    if backend_only:
        # Serve backend API only (no frontend UI)
        from dazzle_dnr_ui.runtime import run_backend_only

        backend_spec = convert_appspec_to_backend(appspec)

        typer.echo(f"Starting DNR backend for '{appspec.name}'...")
        typer.echo(f"  • {len(backend_spec.entities)} entities")
        typer.echo(f"  • {len(backend_spec.endpoints)} endpoints")
        typer.echo(f"  • Database: {db_path}")
        if test_mode:
            typer.echo("  • Test mode: ENABLED (/__test__/* endpoints available)")
        typer.echo()
        typer.echo(f"API: http://{host}:{api_port}")
        typer.echo(f"Docs: http://{host}:{api_port}/docs")
        typer.echo()

        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        run_backend_only(
            backend_spec=backend_spec,
            port=api_port,
            db_path=db_file,
            enable_test_mode=test_mode,
            host=host,
        )
        return

    # Full combined server with API + UI
    typer.echo(f"Starting DNR server for '{appspec.name}'...")

    # Convert specs
    backend_spec = convert_appspec_to_backend(appspec)
    ui_spec = convert_appspec_to_ui(appspec)

    typer.echo(f"  • {len(backend_spec.entities)} entities")
    typer.echo(f"  • {len(backend_spec.endpoints)} endpoints")
    typer.echo(f"  • {len(ui_spec.workspaces)} workspaces")
    typer.echo(f"  • Database: {db_path}")
    typer.echo()

    # Ensure database directory exists
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    # Run combined server
    # Show test mode status
    if test_mode:
        typer.echo("  • Test mode: ENABLED (/__test__/* endpoints available)")

    run_combined_server(
        backend_spec=backend_spec,
        ui_spec=ui_spec,
        backend_port=api_port,
        frontend_port=port,
        db_path=db_file,
        enable_test_mode=test_mode,
        enable_auth=auth_enabled,
        host=host,
    )


@dnr_app.command("info")
def dnr_info() -> None:
    """
    Show DNR installation status and available features.
    """
    typer.echo("Dazzle Native Runtime (DNR) Status")
    typer.echo("=" * 50)

    # Check DNR Backend
    dnr_back_available = False
    fastapi_available = False
    try:
        import dazzle_dnr_back  # noqa: F401

        dnr_back_available = True
        from dazzle_dnr_back.runtime import FASTAPI_AVAILABLE

        fastapi_available = FASTAPI_AVAILABLE
    except ImportError:
        pass

    # Check DNR UI
    dnr_ui_available = False
    try:
        import dazzle_dnr_ui  # noqa: F401

        dnr_ui_available = True
    except ImportError:
        pass

    # Check uvicorn
    uvicorn_available = False
    try:
        import uvicorn  # noqa: F401

        uvicorn_available = True
    except ImportError:
        pass

    typer.echo(
        f"DNR Backend:   {'✓' if dnr_back_available else '✗'} {'installed' if dnr_back_available else 'not installed'}"
    )
    typer.echo(
        f"DNR UI:        {'✓' if dnr_ui_available else '✗'} {'installed' if dnr_ui_available else 'not installed'}"
    )
    typer.echo(
        f"FastAPI:       {'✓' if fastapi_available else '✗'} {'installed' if fastapi_available else 'not installed'}"
    )
    typer.echo(
        f"Uvicorn:       {'✓' if uvicorn_available else '✗'} {'installed' if uvicorn_available else 'not installed'}"
    )

    typer.echo("\nAvailable Commands:")
    if dnr_ui_available:
        typer.echo("  dazzle dnr build-ui   Generate UI (Vite/JS/HTML)")
    if dnr_back_available:
        typer.echo("  dazzle dnr build-api  Generate API spec")
    if dnr_back_available and fastapi_available and uvicorn_available:
        typer.echo("  dazzle dnr serve      Run development server")
    elif dnr_ui_available:
        typer.echo("  dazzle dnr serve --ui-only  Serve UI only")

    if not (dnr_back_available and dnr_ui_available):
        typer.echo("\nTo install DNR packages:")
        if not dnr_back_available:
            typer.echo("  pip install dazzle-dnr-back")
        if not dnr_ui_available:
            typer.echo("  pip install dazzle-dnr-ui")
        if not fastapi_available:
            typer.echo("  pip install fastapi")
        if not uvicorn_available:
            typer.echo("  pip install uvicorn")


def _get_container_name(project_root: Path) -> str:
    """Get the Docker container name for a project."""
    return f"dazzle-{project_root.resolve().name}"


def _is_container_running(container_name: str) -> bool:
    """Check if a Docker container is running."""
    import subprocess

    try:
        result = subprocess.run(
            ["docker", "ps", "-q", "-f", f"name={container_name}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return bool(result.stdout.strip())
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


@dnr_app.command("stop")
def dnr_stop(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    remove: bool = typer.Option(
        True,
        "--remove/--no-remove",
        help="Remove the container after stopping",
    ),
) -> None:
    """
    Stop the running DNR Docker container.

    Stops and optionally removes the Docker container for this project.

    Examples:
        dazzle dnr stop              # Stop and remove container
        dazzle dnr stop --no-remove  # Stop but keep container
    """
    import subprocess

    manifest_path = Path(manifest).resolve()
    project_root = manifest_path.parent
    container_name = _get_container_name(project_root)

    # Check if container is running
    if not _is_container_running(container_name):
        typer.echo(f"Container '{container_name}' is not running")
        raise typer.Exit(code=0)

    typer.echo(f"Stopping container: {container_name}")

    try:
        # Stop the container
        result = subprocess.run(
            ["docker", "stop", container_name],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            typer.echo(f"Failed to stop container: {result.stderr}", err=True)
            raise typer.Exit(code=1)

        typer.echo("Container stopped")

        # Remove if requested
        if remove:
            result = subprocess.run(
                ["docker", "rm", container_name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                typer.echo("Container removed")

    except subprocess.TimeoutExpired:
        typer.echo("Timeout stopping container", err=True)
        raise typer.Exit(code=1)
    except FileNotFoundError:
        typer.echo("Docker not found", err=True)
        raise typer.Exit(code=1)


@dnr_app.command("rebuild")
def dnr_rebuild(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    port: int = typer.Option(3000, "--port", "-p", help="Frontend port"),
    api_port: int = typer.Option(8000, "--api-port", help="Backend API port"),
    test_mode: bool = typer.Option(
        False,
        "--test-mode",
        help="Enable test endpoints (/__test__/seed, /__test__/reset, etc.)",
    ),
    attach: bool = typer.Option(
        False,
        "--attach",
        "-a",
        help="Run Docker container attached (stream logs to terminal)",
    ),
) -> None:
    """
    Rebuild the Docker image and restart the container.

    Stops any running container, rebuilds the Docker image from the current
    DSL files, and starts a fresh container.

    Examples:
        dazzle dnr rebuild              # Rebuild and restart (detached)
        dazzle dnr rebuild --attach     # Rebuild and restart with logs
        dazzle dnr rebuild --test-mode  # Rebuild with test endpoints
    """
    import subprocess

    manifest_path = Path(manifest).resolve()
    project_root = manifest_path.parent
    container_name = _get_container_name(project_root)

    # Stop existing container if running
    if _is_container_running(container_name):
        typer.echo(f"Stopping existing container: {container_name}")
        subprocess.run(
            ["docker", "stop", container_name],
            capture_output=True,
            timeout=30,
        )
        subprocess.run(
            ["docker", "rm", container_name],
            capture_output=True,
            timeout=10,
        )
        typer.echo("Stopped existing container")

    # Now start with rebuild flag
    typer.echo("Rebuilding Docker image from DSL...")

    try:
        from dazzle_dnr_ui.runtime import is_docker_available, run_in_docker

        if not is_docker_available():
            typer.echo("Docker is not available", err=True)
            raise typer.Exit(code=1)

        detach = not attach
        exit_code = run_in_docker(
            project_path=project_root,
            frontend_port=port,
            api_port=api_port,
            test_mode=test_mode,
            rebuild=True,  # Force rebuild
            detach=detach,
        )
        raise typer.Exit(code=exit_code)

    except ImportError as e:
        typer.echo(f"DNR runtime not available: {e}", err=True)
        raise typer.Exit(code=1)


@dnr_app.command("logs")
def dnr_logs(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    follow: bool = typer.Option(
        False,
        "--follow",
        "-f",
        help="Follow log output (stream new logs)",
    ),
    tail: int = typer.Option(
        100,
        "--tail",
        "-n",
        help="Number of lines to show from end of logs",
    ),
) -> None:
    """
    View logs from the running DNR Docker container.

    Shows the most recent logs from the container. Use --follow to stream
    new logs as they are generated.

    Examples:
        dazzle dnr logs              # Show last 100 lines
        dazzle dnr logs -f           # Follow/stream logs
        dazzle dnr logs -n 50        # Show last 50 lines
        dazzle dnr logs -f -n 10     # Follow starting from last 10 lines
    """
    import subprocess

    manifest_path = Path(manifest).resolve()
    project_root = manifest_path.parent
    container_name = _get_container_name(project_root)

    # Check if container exists
    if not _is_container_running(container_name):
        typer.echo(f"Container '{container_name}' is not running")
        typer.echo("Start it with: dazzle dnr serve")
        raise typer.Exit(code=1)

    # Build docker logs command
    cmd = ["docker", "logs"]

    if follow:
        cmd.append("-f")

    cmd.extend(["--tail", str(tail)])
    cmd.append(container_name)

    typer.echo(f"Logs from container: {container_name}")
    typer.echo("-" * 50)

    try:
        # Run docker logs, passing output directly to terminal
        subprocess.run(cmd)
    except KeyboardInterrupt:
        typer.echo("\nStopped following logs")
    except FileNotFoundError:
        typer.echo("Docker not found", err=True)
        raise typer.Exit(code=1)


@dnr_app.command("status")
def dnr_status(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
) -> None:
    """
    Show the status of the DNR Docker container.

    Displays whether the container is running, its ports, and resource usage.

    Examples:
        dazzle dnr status
    """
    import subprocess

    manifest_path = Path(manifest).resolve()
    project_root = manifest_path.parent
    container_name = _get_container_name(project_root)

    typer.echo(f"DNR Container Status: {container_name}")
    typer.echo("=" * 50)

    # Check if container is running
    if not _is_container_running(container_name):
        typer.echo("Status: NOT RUNNING")
        typer.echo("\nStart with: dazzle dnr serve")
        return

    typer.echo("Status: RUNNING")

    # Get container details
    try:
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{range .NetworkSettings.Ports}}{{.}}{{end}}",
                container_name,
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            typer.echo(f"Ports: {result.stdout.strip()}")

        # Get container stats (CPU, memory)
        result = subprocess.run(
            [
                "docker",
                "stats",
                "--no-stream",
                "--format",
                "CPU: {{.CPUPerc}}, Memory: {{.MemUsage}}",
                container_name,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            typer.echo(result.stdout.strip())

        # Health check
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.Health.Status}}",
                container_name,
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            health = result.stdout.strip()
            typer.echo(f"Health: {health}")

    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    typer.echo("\nCommands:")
    typer.echo("  dazzle dnr logs     - View container logs")
    typer.echo("  dazzle dnr stop     - Stop the container")
    typer.echo("  dazzle dnr rebuild  - Rebuild and restart")


# =============================================================================
# Test Commands (dazzle test)
# =============================================================================

test_app = typer.Typer(
    help="Semantic E2E testing commands for Dazzle applications.",
    no_args_is_help=True,
)
app.add_typer(test_app, name="test")


@test_app.command("generate")
def test_generate(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    output: str = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file for E2ETestSpec JSON (default: stdout)",
    ),
    include_flows: bool = typer.Option(
        True,
        "--flows/--no-flows",
        help="Include auto-generated CRUD and validation flows",
    ),
    include_fixtures: bool = typer.Option(
        True,
        "--fixtures/--no-fixtures",
        help="Include auto-generated fixtures",
    ),
    format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Output format: json (default) or yaml",
    ),
) -> None:
    """
    Generate E2ETestSpec from AppSpec.

    Creates a complete test specification including:
    - CRUD flows for each entity (create, view, update, delete)
    - Validation flows from field constraints
    - Navigation flows for each surface
    - Fixtures from entity schemas
    - Usability and accessibility rules

    Examples:
        dazzle test generate                    # Print to stdout
        dazzle test generate -o tests.json      # Save to file
        dazzle test generate --no-flows         # Skip auto-generated flows
        dazzle test generate --format yaml      # YAML output
    """
    try:
        from dazzle.testing.testspec_generator import generate_e2e_testspec
    except ImportError as e:
        typer.echo(f"E2E testing module not available: {e}", err=True)
        raise typer.Exit(code=1)

    # Load AppSpec
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)

        errors, warnings = lint_appspec(appspec)
        for warn in warnings:
            typer.echo(f"WARNING: {warn}", err=True)

        if errors:
            typer.echo("Cannot generate tests; spec has validation errors:", err=True)
            for err in errors:
                typer.echo(f"  ERROR: {err}", err=True)
            raise typer.Exit(code=1)

    except (ParseError, DazzleError) as e:
        typer.echo(f"Error loading spec: {e}", err=True)
        raise typer.Exit(code=1)

    # Generate E2ETestSpec
    testspec = generate_e2e_testspec(appspec)

    # Apply filters if requested
    if not include_flows:
        # Keep only DSL-defined flows (not auto-generated)
        testspec.flows = [f for f in testspec.flows if not getattr(f, "auto_generated", False)]

    if not include_fixtures:
        testspec.fixtures = []

    # Output statistics
    typer.echo(f"Generated E2ETestSpec for '{appspec.name}':", err=True)
    typer.echo(f"  • {len(testspec.fixtures)} fixtures", err=True)
    typer.echo(f"  • {len(testspec.flows)} flows", err=True)
    typer.echo(f"  • {len(testspec.usability_rules)} usability rules", err=True)
    typer.echo(f"  • {len(testspec.a11y_rules)} accessibility rules", err=True)

    # Serialize
    if format == "json":
        content = testspec.model_dump_json(indent=2)
    elif format == "yaml":
        try:
            import yaml

            content = yaml.safe_dump(
                testspec.model_dump(mode="json"),
                default_flow_style=False,
                allow_unicode=True,
            )
        except ImportError:
            typer.echo("YAML output requires PyYAML: pip install pyyaml", err=True)
            raise typer.Exit(code=1)
    else:
        typer.echo(f"Unknown format: {format}", err=True)
        raise typer.Exit(code=1)

    # Output
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content)
        typer.echo(f"  → Saved to {output_path}", err=True)
    else:
        typer.echo(content)


@test_app.command("run")
def test_run(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    priority: str = typer.Option(
        None,
        "--priority",
        "-p",
        help="Run only flows with this priority (high, medium, low)",
    ),
    tag: str = typer.Option(
        None,
        "--tag",
        "-t",
        help="Run only flows with this tag",
    ),
    flow: str = typer.Option(
        None,
        "--flow",
        "-f",
        help="Run only this specific flow by ID",
    ),
    base_url: str = typer.Option(
        "http://localhost:3000",
        "--base-url",
        help="Base URL of the running application",
    ),
    api_url: str = typer.Option(
        "http://localhost:8000",
        "--api-url",
        help="Base URL of the API server",
    ),
    headless: bool = typer.Option(
        True,
        "--headless/--headed",
        help="Run browser in headless mode",
    ),
    timeout: int = typer.Option(
        30000,
        "--timeout",
        help="Default timeout in milliseconds",
    ),
    output: str = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file for test results JSON",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output",
    ),
) -> None:
    """
    Run E2E tests using Playwright.

    Requires the application to be running (use 'dazzle dnr serve --test-mode').

    Examples:
        dazzle test run                             # Run all tests
        dazzle test run --priority high             # Run high-priority only
        dazzle test run --tag crud                  # Run tests tagged 'crud'
        dazzle test run --flow Task_create_valid    # Run specific flow
        dazzle test run --headed                    # Show browser window
    """
    # Check for playwright
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        typer.echo("Playwright not installed. Install with:", err=True)
        typer.echo("  pip install playwright", err=True)
        typer.echo("  playwright install chromium", err=True)
        raise typer.Exit(code=1)

    try:
        from dazzle.testing.testspec_generator import generate_e2e_testspec
        from dazzle_e2e.adapters.dnr import DNRAdapter
    except ImportError as e:
        typer.echo(f"E2E testing modules not available: {e}", err=True)
        raise typer.Exit(code=1)

    # Load AppSpec
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)

        errors, _ = lint_appspec(appspec)
        if errors:
            typer.echo("Cannot run tests; spec has validation errors:", err=True)
            for err in errors:
                typer.echo(f"  ERROR: {err}", err=True)
            raise typer.Exit(code=1)

    except (ParseError, DazzleError) as e:
        typer.echo(f"Error loading spec: {e}", err=True)
        raise typer.Exit(code=1)

    # Generate E2ETestSpec
    testspec = generate_e2e_testspec(appspec)

    # Include any DSL-defined flows from appspec
    if appspec.e2e_flows:
        testspec.flows.extend(appspec.e2e_flows)

    # Filter flows
    flows_to_run = testspec.flows

    if flow:
        flows_to_run = [f for f in flows_to_run if f.id == flow]
        if not flows_to_run:
            typer.echo(f"Flow not found: {flow}", err=True)
            typer.echo("Available flows:", err=True)
            for f in testspec.flows[:10]:
                typer.echo(f"  - {f.id}", err=True)
            if len(testspec.flows) > 10:
                typer.echo(f"  ... and {len(testspec.flows) - 10} more", err=True)
            raise typer.Exit(code=1)

    if priority:
        from dazzle.core.ir import FlowPriority

        try:
            priority_enum = FlowPriority(priority)
            flows_to_run = [f for f in flows_to_run if f.priority == priority_enum]
        except ValueError:
            typer.echo(f"Invalid priority: {priority}", err=True)
            typer.echo("Valid priorities: high, medium, low", err=True)
            raise typer.Exit(code=1)

    if tag:
        flows_to_run = [f for f in flows_to_run if tag in f.tags]

    if not flows_to_run:
        typer.echo("No flows match the specified filters.", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Running {len(flows_to_run)} E2E flows for '{appspec.name}'...")
    typer.echo(f"  • Base URL: {base_url}")
    typer.echo(f"  • API URL: {api_url}")
    typer.echo()

    # Build fixtures dict
    fixtures = {f.id: f for f in testspec.fixtures}

    # Run with Playwright (sync API for CLI)
    results: list[dict[str, Any]] = []
    passed = 0
    failed = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(timeout)

        # Create adapter
        adapter = DNRAdapter(base_url=base_url, api_url=api_url)

        for flow_spec in flows_to_run:
            if verbose:
                typer.echo(f"Running: {flow_spec.id}...")

            try:
                # Reset test data before each flow
                adapter.reset_sync()

                # Apply preconditions
                if flow_spec.preconditions:
                    if flow_spec.preconditions.fixtures:
                        fixtures_to_seed = [
                            fixtures[fid]
                            for fid in flow_spec.preconditions.fixtures
                            if fid in fixtures
                        ]
                        if fixtures_to_seed:
                            adapter.seed_sync(fixtures_to_seed)

                    if flow_spec.preconditions.authenticated:
                        adapter.authenticate_sync(role=flow_spec.preconditions.user_role)

                    if flow_spec.preconditions.view:
                        url = adapter.resolve_view_url(flow_spec.preconditions.view)
                        page.goto(url)

                # Execute steps
                step_errors: list[str] = []
                for step in flow_spec.steps:
                    try:
                        _execute_step_sync(page, step, adapter, fixtures, timeout)
                    except Exception as e:
                        step_errors.append(f"Step {step.kind.value}: {e}")
                        break

                if step_errors:
                    failed += 1
                    status = "FAIL"
                    error = step_errors[0]
                else:
                    passed += 1
                    status = "PASS"
                    error = None

            except Exception as e:
                failed += 1
                status = "FAIL"
                error = str(e)

            result = {
                "flow_id": flow_spec.id,
                "status": status,
                "error": error,
            }
            results.append(result)

            # Output result
            icon = "✓" if status == "PASS" else "✗"
            color = typer.colors.GREEN if status == "PASS" else typer.colors.RED
            typer.secho(f"  {icon} {flow_spec.id}", fg=color)
            if error and verbose:
                typer.echo(f"    Error: {error}")

        browser.close()

    # Summary
    typer.echo()
    typer.echo(f"Results: {passed} passed, {failed} failed")

    # Output results to file
    if output:
        import json

        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(results, indent=2))
        typer.echo(f"Results saved to {output_path}")

    # Exit with error code if any failures
    if failed > 0:
        raise typer.Exit(code=1)


def _execute_step_sync(
    page: Any,
    step: Any,
    adapter: Any,
    fixtures: dict[str, Any],
    timeout: int,
) -> None:
    """Execute a single flow step synchronously."""
    from dazzle.core.ir import FlowStepKind

    if step.kind == FlowStepKind.NAVIGATE:
        if step.target and step.target.startswith("view:"):
            view_id = step.target.split(":", 1)[1]
            url = adapter.resolve_view_url(view_id)
        else:
            url = step.target or adapter.base_url
        page.goto(url)

    elif step.kind == FlowStepKind.FILL:
        if not step.target:
            raise ValueError("Fill step requires target")
        # Build selector from semantic target
        selector = _build_selector(step.target)
        value = _resolve_step_value(step, fixtures)
        page.locator(selector).fill(str(value))

    elif step.kind == FlowStepKind.CLICK:
        if not step.target:
            raise ValueError("Click step requires target")
        selector = _build_selector(step.target)
        page.locator(selector).click()

    elif step.kind == FlowStepKind.WAIT:
        if step.value:
            page.wait_for_timeout(int(step.value))
        elif step.target:
            selector = _build_selector(step.target)
            page.locator(selector).wait_for(state="visible", timeout=timeout)
        else:
            page.wait_for_timeout(1000)

    elif step.kind == FlowStepKind.ASSERT:
        if not step.assertion:
            raise ValueError("Assert step requires assertion")
        _execute_assertion_sync(page, step.assertion, adapter, timeout)

    elif step.kind == FlowStepKind.SNAPSHOT:
        # Just capture state, nothing to do in sync mode
        pass

    else:
        raise ValueError(f"Unknown step kind: {step.kind}")


def _build_selector(target: str) -> str:
    """Build a CSS selector from a semantic target."""
    if target.startswith("view:"):
        view_id = target.split(":", 1)[1]
        return f'[data-dazzle-view="{view_id}"]'
    elif target.startswith("field:"):
        field_id = target.split(":", 1)[1]
        return f'[data-dazzle-field="{field_id}"]'
    elif target.startswith("action:"):
        action_id = target.split(":", 1)[1]
        return f'[data-dazzle-action="{action_id}"]'
    elif target.startswith("entity:"):
        entity_name = target.split(":", 1)[1]
        return f'[data-dazzle-entity="{entity_name}"]'
    elif target.startswith("row:"):
        entity_name = target.split(":", 1)[1]
        return f'[data-dazzle-entity="{entity_name}"]'
    elif target.startswith("message:"):
        target_id = target.split(":", 1)[1]
        return f'[data-dazzle-message="{target_id}"]'
    elif target.startswith("nav:"):
        nav_id = target.split(":", 1)[1]
        return f'[data-dazzle-nav="{nav_id}"]'
    else:
        # Fallback to CSS selector
        return target


def _resolve_step_value(step: Any, fixtures: dict[str, Any]) -> str | int | float | bool:
    """Resolve the value for a fill step."""
    if step.value is not None:
        value: str | int | float | bool = step.value
        return value

    if step.fixture_ref:
        parts = step.fixture_ref.split(".")
        if len(parts) == 2:
            fixture_id, field_name = parts
            if fixture_id in fixtures:
                fixture = fixtures[fixture_id]
                if field_name in fixture.data:
                    result: str | int | float | bool = fixture.data[field_name]
                    return result

    raise ValueError("Could not resolve value for step")


def _execute_assertion_sync(
    page: Any,
    assertion: Any,
    adapter: Any,
    timeout: int,
) -> None:
    """Execute an assertion synchronously."""
    from playwright.sync_api import expect

    from dazzle.core.ir import FlowAssertionKind

    if assertion.kind == FlowAssertionKind.VISIBLE:
        target = assertion.target or ""
        selector = _build_selector(target)
        expect(page.locator(selector)).to_be_visible(timeout=timeout)

    elif assertion.kind == FlowAssertionKind.NOT_VISIBLE:
        target = assertion.target or ""
        selector = _build_selector(target)
        expect(page.locator(selector)).to_be_hidden(timeout=timeout)

    elif assertion.kind == FlowAssertionKind.TEXT_CONTAINS:
        expect(page.locator("body")).to_contain_text(str(assertion.expected), timeout=timeout)

    elif assertion.kind == FlowAssertionKind.ENTITY_EXISTS:
        # Check via API
        entity_name = assertion.target or ""
        if entity_name.startswith("entity:"):
            entity_name = entity_name.split(":", 1)[1]
        count = adapter.get_entity_count_sync(entity_name)
        if count == 0:
            raise AssertionError(f"Expected {entity_name} to exist, but count is 0")

    elif assertion.kind == FlowAssertionKind.ENTITY_NOT_EXISTS:
        entity_name = assertion.target or ""
        if entity_name.startswith("entity:"):
            entity_name = entity_name.split(":", 1)[1]
        count = adapter.get_entity_count_sync(entity_name)
        if count > 0:
            raise AssertionError(f"Expected {entity_name} to not exist, but count is {count}")

    elif assertion.kind == FlowAssertionKind.VALIDATION_ERROR:
        target = assertion.target or ""
        if target.startswith("field:"):
            target = target.split(":", 1)[1]
        selector = f'[data-dazzle-message="{target}"][data-dazzle-message-kind="validation"]'
        expect(page.locator(selector)).to_be_visible(timeout=timeout)

    elif assertion.kind == FlowAssertionKind.REDIRECTS_TO:
        target = assertion.target or ""
        if target.startswith("view:"):
            view_id = target.split(":", 1)[1]
            selector = f'[data-dazzle-view="{view_id}"]'
            expect(page.locator(selector)).to_be_visible(timeout=timeout)

    elif assertion.kind == FlowAssertionKind.COUNT:
        entity_name = assertion.target or ""
        if entity_name.startswith("entity:"):
            entity_name = entity_name.split(":", 1)[1]
        expected = int(assertion.expected) if assertion.expected is not None else 0
        count = adapter.get_entity_count_sync(entity_name)
        if count != expected:
            raise AssertionError(f"Expected {entity_name} count to be {expected}, but was {count}")

    elif assertion.kind == FlowAssertionKind.FIELD_VALUE:
        target = assertion.target or ""
        if target.startswith("field:"):
            target = target.split(":", 1)[1]
        selector = f'[data-dazzle-field="{target}"]'
        expect(page.locator(selector)).to_have_value(str(assertion.expected), timeout=timeout)

    else:
        raise ValueError(f"Unknown assertion kind: {assertion.kind}")


@test_app.command("list")
def test_list(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    priority: str = typer.Option(
        None,
        "--priority",
        "-p",
        help="Filter by priority (high, medium, low)",
    ),
    tag: str = typer.Option(
        None,
        "--tag",
        "-t",
        help="Filter by tag",
    ),
) -> None:
    """
    List available E2E test flows.

    Examples:
        dazzle test list                    # List all flows
        dazzle test list --priority high    # List high-priority flows
        dazzle test list --tag crud         # List flows tagged 'crud'
    """
    try:
        from dazzle.testing.testspec_generator import generate_e2e_testspec
    except ImportError as e:
        typer.echo(f"E2E testing module not available: {e}", err=True)
        raise typer.Exit(code=1)

    # Load AppSpec
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)
    except (ParseError, DazzleError) as e:
        typer.echo(f"Error loading spec: {e}", err=True)
        raise typer.Exit(code=1)

    # Generate E2ETestSpec
    testspec = generate_e2e_testspec(appspec)

    # Include any DSL-defined flows
    if appspec.e2e_flows:
        testspec.flows.extend(appspec.e2e_flows)

    # Filter
    flows = testspec.flows

    if priority:
        from dazzle.core.ir import FlowPriority

        try:
            priority_enum = FlowPriority(priority)
            flows = [f for f in flows if f.priority == priority_enum]
        except ValueError:
            typer.echo(f"Invalid priority: {priority}", err=True)
            raise typer.Exit(code=1)

    if tag:
        flows = [f for f in flows if tag in f.tags]

    # Display
    typer.echo(f"E2E Flows for '{appspec.name}' ({len(flows)} total):\n")

    for f in flows:
        priority_color = {
            "high": typer.colors.RED,
            "medium": typer.colors.YELLOW,
            "low": typer.colors.CYAN,
        }.get(f.priority.value, typer.colors.WHITE)

        typer.echo(f"  {f.id}")
        typer.secho(f"    Priority: {f.priority.value}", fg=priority_color)
        if f.description:
            typer.echo(f"    Description: {f.description}")
        if f.tags:
            typer.echo(f"    Tags: {', '.join(f.tags)}")
        typer.echo()


# =============================================================================
# E2E Commands (dazzle e2e) - Docker-based E2E testing
# =============================================================================

e2e_app = typer.Typer(
    help="Docker-based E2E testing with UX coverage tracking.",
    no_args_is_help=True,
)
app.add_typer(e2e_app, name="e2e")


@e2e_app.command("run")
def e2e_run(
    example: str = typer.Argument(
        ...,
        help="Name of the example to test (e.g., 'simple_task', 'contact_manager')",
    ),
    coverage_threshold: int = typer.Option(
        0,
        "--coverage-threshold",
        "-c",
        help="Minimum UX coverage percentage required (0-100)",
    ),
    copy_screenshots: bool = typer.Option(
        False,
        "--copy-screenshots",
        help="Copy screenshots to example directory after test",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed output",
    ),
) -> None:
    """
    Run E2E tests for an example project using Docker.

    This command handles the full Docker lifecycle:
    1. Builds the DNR container with the specified example
    2. Starts containers with health checks
    3. Runs Playwright tests
    4. Captures screenshots and UX coverage
    5. Cleans up containers

    Examples:
        dazzle e2e run simple_task                    # Test simple_task example
        dazzle e2e run contact_manager -c 80          # Require 80% coverage
        dazzle e2e run ops_dashboard --copy-screenshots  # Copy screenshots after
    """
    import shutil
    import subprocess

    # Find the run_ux_coverage.sh script
    try:
        import dazzle

        dazzle_root = Path(dazzle.__file__).parent.parent.parent
    except Exception:
        dazzle_root = Path.cwd()

    script_path = dazzle_root / "tests" / "e2e" / "docker" / "run_ux_coverage.sh"

    if not script_path.exists():
        typer.echo(f"E2E test script not found: {script_path}", err=True)
        typer.echo("Make sure you're running from the Dazzle repository.", err=True)
        raise typer.Exit(code=2)

    # Validate example exists
    examples_dir = dazzle_root / "examples"
    example_path = examples_dir / example

    if not example_path.exists():
        typer.echo(f"Example '{example}' not found at {example_path}", err=True)
        typer.echo(
            f"Available examples: {', '.join(d.name for d in examples_dir.iterdir() if d.is_dir())}",
            err=True,
        )
        raise typer.Exit(code=2)

    # Check Docker is available
    try:
        subprocess.run(
            ["docker", "info"],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        typer.echo("Docker is not running. Please start Docker first.", err=True)
        raise typer.Exit(code=2)
    except FileNotFoundError:
        typer.echo("Docker not found. Please install Docker.", err=True)
        raise typer.Exit(code=2)

    typer.echo(f"Running E2E tests for '{example}'...")
    if coverage_threshold > 0:
        typer.echo(f"Coverage threshold: {coverage_threshold}%")

    # Build command
    cmd = [str(script_path), example]
    if coverage_threshold > 0:
        cmd.extend(["--coverage-threshold", str(coverage_threshold)])

    # Run the script
    try:
        result = subprocess.run(
            cmd,
            cwd=dazzle_root,
            capture_output=not verbose,
            text=True,
        )

        if result.returncode == 0:
            typer.secho("✓ E2E tests passed!", fg=typer.colors.GREEN)
        elif result.returncode == 1:
            typer.secho("✗ Coverage below threshold", fg=typer.colors.YELLOW)
        else:
            typer.secho("✗ E2E tests failed", fg=typer.colors.RED)
            if not verbose and result.stderr:
                typer.echo(result.stderr)

        # Copy screenshots if requested
        if copy_screenshots:
            screenshots_src = dazzle_root / "tests" / "e2e" / "docker" / "screenshots" / example
            screenshots_dst = example_path / "screenshots"

            if screenshots_src.exists():
                screenshots_dst.mkdir(exist_ok=True)
                for png in screenshots_src.glob("*.png"):
                    shutil.copy2(png, screenshots_dst / png.name)
                typer.echo(f"Copied screenshots to {screenshots_dst}")

        raise typer.Exit(code=result.returncode)

    except KeyboardInterrupt:
        typer.echo("\nTest interrupted. Cleaning up containers...")
        raise typer.Exit(code=2)


@e2e_app.command("run-all")
def e2e_run_all(
    coverage_threshold: int = typer.Option(
        0,
        "--coverage-threshold",
        "-c",
        help="Minimum UX coverage percentage required (0-100)",
    ),
    copy_screenshots: bool = typer.Option(
        False,
        "--copy-screenshots",
        help="Copy screenshots to example directories after tests",
    ),
    stop_on_failure: bool = typer.Option(
        False,
        "--stop-on-failure",
        help="Stop at first failure",
    ),
) -> None:
    """
    Run E2E tests for all example projects.

    Examples:
        dazzle e2e run-all                          # Test all examples
        dazzle e2e run-all --copy-screenshots       # Copy screenshots after
        dazzle e2e run-all --stop-on-failure        # Stop at first failure
    """
    import shutil
    import subprocess

    try:
        import dazzle

        dazzle_root = Path(dazzle.__file__).parent.parent.parent
    except Exception:
        dazzle_root = Path.cwd()

    examples_dir = dazzle_root / "examples"
    examples = sorted(
        d.name for d in examples_dir.iterdir() if d.is_dir() and (d / "dazzle.toml").exists()
    )

    if not examples:
        typer.echo("No examples found with dazzle.toml", err=True)
        raise typer.Exit(code=2)

    # Find dazzle CLI executable once
    dazzle_cmd = shutil.which("dazzle")
    if not dazzle_cmd:
        # Fallback: try to find it relative to sys.executable
        dazzle_cmd = str(Path(sys.executable).parent / "dazzle")
        if not Path(dazzle_cmd).exists():
            typer.echo("Could not find dazzle CLI executable", err=True)
            raise typer.Exit(code=2)

    typer.echo(f"Running E2E tests for {len(examples)} examples: {', '.join(examples)}\n")

    results: dict[str, str] = {}

    for example in examples:
        typer.echo(f"\n{'=' * 60}")
        typer.echo(f"Testing: {example}")
        typer.echo(f"{'=' * 60}")

        cmd = [dazzle_cmd, "e2e", "run", example]
        if coverage_threshold > 0:
            cmd.extend(["--coverage-threshold", str(coverage_threshold)])
        if copy_screenshots:
            cmd.append("--copy-screenshots")

        result = subprocess.run(cmd, cwd=dazzle_root)

        if result.returncode == 0:
            results[example] = "PASS"
        elif result.returncode == 1:
            results[example] = "COVERAGE"
        else:
            results[example] = "FAIL"
            if stop_on_failure:
                typer.echo(f"\nStopping due to failure in {example}")
                break

    # Summary
    typer.echo(f"\n{'=' * 60}")
    typer.echo("E2E Test Summary")
    typer.echo(f"{'=' * 60}")

    for example, status in results.items():
        color = {
            "PASS": typer.colors.GREEN,
            "COVERAGE": typer.colors.YELLOW,
            "FAIL": typer.colors.RED,
        }.get(status, typer.colors.WHITE)
        typer.secho(f"  {example}: {status}", fg=color)

    passed = sum(1 for s in results.values() if s == "PASS")
    total = len(results)
    typer.echo(f"\n{passed}/{total} examples passed")

    if passed < total:
        raise typer.Exit(code=1)


@e2e_app.command("clean")
def e2e_clean() -> None:
    """
    Clean up any lingering E2E test containers.

    Use this if containers are left running after a failed test.
    """
    import subprocess

    typer.echo("Cleaning up E2E test containers...")

    # Check Docker is available
    try:
        subprocess.run(
            ["docker", "info"],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        typer.echo("Docker is not running. Please start Docker first.", err=True)
        raise typer.Exit(code=2)
    except FileNotFoundError:
        typer.echo("Docker not found. Please install Docker.", err=True)
        raise typer.Exit(code=2)

    # Find and stop dazzle-e2e containers (don't use check=True since empty result is OK)
    result = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=dazzle-e2e", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        typer.echo(f"Error listing containers: {result.stderr}", err=True)
        raise typer.Exit(code=2)

    containers = result.stdout.strip().split("\n")
    containers = [c for c in containers if c]

    if not containers:
        typer.echo("No E2E containers found.")
        return

    typer.echo(f"Found {len(containers)} containers: {', '.join(containers)}")

    for container in containers:
        subprocess.run(["docker", "stop", container], capture_output=True)
        subprocess.run(["docker", "rm", container], capture_output=True)
        typer.echo(f"  Removed: {container}")

    typer.secho("✓ Cleanup complete", fg=typer.colors.GREEN)


def main(argv: list[str] | None = None) -> None:
    import os

    # Set umask to 0o000 so files are created with 666 permissions (rw-rw-rw--)
    os.umask(0o000)
    app(standalone_mode=True)


if __name__ == "__main__":
    main(sys.argv[1:])
