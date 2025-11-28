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
from dazzle.core.stacks import StackPreset
from dazzle.core.state import compute_dsl_hashes, load_state, save_state


def get_version() -> str:
    """Get DAZZLE version from package metadata."""
    try:
        from importlib.metadata import version

        return version("dazzle")
    except Exception:
        # Fallback if not installed as package
        return "0.1.0-dev"


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
  • Project Creation: init, clone, demo
    → init: Initialize in current directory (or create new)
    → clone/demo: Create NEW directories

  • Project Operations: validate, build, lint, stacks
    → Operate in CURRENT directory (must have dazzle.toml)
""",
    no_args_is_help=True,
    add_completion=False,
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

        init_project(
            target_dir=target,
            project_name=name,
            from_example=from_example,
            title=title,
            no_llm=no_llm,
            no_git=no_git,
            allow_existing=allow_existing,
        )

        # Success message
        if path is None:
            typer.echo(f"✓ Initialized project in current directory: {target.name}")
        else:
            typer.echo(f"✓ Created project: {target}")

        if not from_example:
            typer.echo("✓ Created SPEC.md template (fill out your requirements)")
        if not no_git:
            typer.echo("✓ Initialized git repository")
        if not no_llm:
            typer.echo("✓ Created LLM context files (LLM_CONTEXT.md, .llm/, .claude/, .copilot/)")

        typer.echo("\nNext steps:")
        if path is not None:
            typer.echo(f"  cd {path}")
        if not from_example:
            typer.echo("  # 1. Edit SPEC.md with your project requirements")
            typer.echo("  # 2. Work with an AI assistant to create DSL from your spec")
        typer.echo("  dazzle validate")
        typer.echo("  dazzle build  # Uses 'micro' stack by default")

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
def demo(
    stack: str | None = typer.Argument(
        None, help="Stack preset name (defaults to 'micro' - simplest setup)"
    ),
    path: str | None = typer.Option(
        None, "--path", "-p", help="Directory to create demo in (default: ./<stack>-demo)"
    ),
    list_stacks: bool = typer.Option(False, "--list", "-l", help="List available stack presets"),
    no_build: bool = typer.Option(
        False, "--no-build", help="Skip automatic build after generation"
    ),
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
    from dazzle.core.stacks import (
        DEFAULT_DEMO_STACK,
        get_stack_description,
        get_stack_preset,
        list_stack_presets,
    )

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
        for line in default_desc.split("\n"):
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
            for line in desc.split("\n"):
                typer.echo(f"    {line}")
            if preset and preset.example_dsl:
                typer.echo(f"    Example: {preset.example_dsl}")
            typer.echo()

        typer.echo("Use: dazzle demo [stack]")
        typer.echo(
            f"     dazzle demo              # Uses '{DEFAULT_DEMO_STACK}' (recommended for beginners)"
        )
        return

    # Use default stack if none provided
    if stack is None:
        stack = DEFAULT_DEMO_STACK
        typer.echo(f"No stack specified, using default: '{stack}'")
        typer.echo("(Run 'dazzle demo --list' to see other options)\n")

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
        typer.echo(
            '    python -c \'import dazzle; print(dazzle.__file__.replace("__init__.py", "../examples"))\''
        )

        typer.echo("=" * 60)

    except Exception as e:
        typer.echo(f"Error creating demo: {e}", err=True)
        raise typer.Exit(code=1)


def _create_demo_project(target_dir: Path, preset: StackPreset) -> None:
    """Create a demo project with example DSL and stack configuration."""
    import subprocess

    from dazzle.core.llm_context import create_llm_instrumentation

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
{chr(10).join(f"- {backend}" for backend in preset.backends)}

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

        warnings.warn(f"Failed to create LLM instrumentation: {e}", stacklevel=2)

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
    source: str | None = typer.Argument(None, help="Example app name or GitHub URL to clone"),
    path: str | None = typer.Option(None, "--path", "-p", help="Directory to clone into"),
    stack: str | None = typer.Option(
        None, "--stack", "-s", help="Stack preset to use (e.g., 'api_only', 'django_next')"
    ),
    list_examples_flag: bool = typer.Option(
        False, "--list", "-l", help="List available example apps"
    ),
    list_stacks: bool = typer.Option(False, "--list-stacks", help="List available stack presets"),
    no_build: bool = typer.Option(False, "--no-build", help="Skip automatic build after cloning"),
    branch: str | None = typer.Option(
        None, "--branch", "-b", help="Git branch to clone (for GitHub URLs)"
    ),
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
    import re

    from dazzle.core.stacks import get_stack_description, list_stack_presets

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
            for line in desc.split("\n"):
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
    is_github_url = bool(re.match(r"https?://(www\.)?github\.com/", source))
    is_git_url = source.endswith(".git") or is_github_url

    if is_git_url:
        # Clone from GitHub
        _clone_from_github(source, path, branch, no_build)
    else:
        # Clone example app
        _clone_example(source, path, stack, no_build)


def _clone_from_github(url: str, path: str | None, branch: str | None, no_build: bool) -> None:
    """Clone a DAZZLE project from GitHub."""
    import re
    import subprocess

    # Extract project name from URL
    match = re.search(r"/([^/]+?)(?:\.git)?$", url)
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
            typer.echo(
                "\n⚠ Warning: This doesn't appear to be a DAZZLE project (no dazzle.toml found)"
            )
            typer.echo(
                "If this is a DAZZLE project, make sure the repository structure is correct."
            )
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
    from dazzle.core.stacks import get_stack_preset, list_stack_presets
    from dazzle.stacks import list_backends

    available_backends = set(list_backends())
    all_stacks = list_stack_presets()
    valid_stacks = []

    for stack_name in all_stacks:
        preset = get_stack_preset(stack_name)
        if preset and all(backend in available_backends for backend in preset.backends):
            valid_stacks.append(stack_name)

    return valid_stacks


def _clone_example(
    example_name: str, path: str | None, stack_name: str | None, no_build: bool
) -> None:
    """Clone a built-in example app."""
    from dazzle.core.stacks import get_stack_description, get_stack_preset
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
            first_line = desc.split("\n")[0] if desc else ""
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

    # Validate stack (stack_name guaranteed set by loop above or function parameter)
    assert stack_name is not None
    preset = get_stack_preset(stack_name)
    if not preset:
        typer.echo(f"Error: Stack '{stack_name}' not found.", err=True)
        typer.echo("Use 'dazzle clone --list-stacks' to see available stacks.", err=True)
        raise typer.Exit(code=1)

    # Validate stack implementations are available
    available_backends = set(list_backends())
    missing_backends = [b for b in preset.backends if b not in available_backends]
    if missing_backends:
        typer.echo(
            f"Error: Stack '{stack_name}' requires unavailable implementations: {', '.join(missing_backends)}",
            err=True,
        )
        typer.echo(f"Available implementations: {', '.join(sorted(available_backends))}", err=True)
        typer.echo("\nUse a different stack or specify custom stack:", err=True)
        typer.echo(
            f"  dazzle build --stack {','.join([b for b in preset.backends if b in available_backends])}",
            err=True,
        )
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
                stack_section = f'\n[stack]\nname = "{stack_name}"\n'
                manifest_path.write_text(manifest_content + stack_section)
            else:
                # Update existing stack name
                import re

                manifest_content = re.sub(
                    r'name = "[^"]*"',
                    f'name = "{stack_name}"',
                    manifest_content,
                    count=1,
                    flags=re.MULTILINE,
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
    db_path: str = typer.Option(".dazzle/data.db", "--db", help="SQLite database path"),
) -> None:
    """
    Serve DNR app (backend API + UI with live data).

    Runs a combined server with:
    - FastAPI backend on api-port (default 8000) with SQLite persistence
    - Frontend dev server on port (default 3000) with API proxy
    - Auto-migration for schema changes
    - Interactive API docs at http://host:api-port/docs

    Examples:
        dazzle dnr serve                    # Backend:8000, Frontend:3000
        dazzle dnr serve --port 4000        # Frontend on 4000
        dazzle dnr serve --api-port 9000    # API on 9000
        dazzle dnr serve --ui-only          # Static UI only (no API)
        dazzle dnr serve --db ./my.db       # Custom database path
    """
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
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        mf = load_manifest(manifest_path)
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
    run_combined_server(
        backend_spec=backend_spec,
        ui_spec=ui_spec,
        backend_port=api_port,
        frontend_port=port,
        db_path=db_file,
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


def main(argv: list[str] | None = None) -> None:
    import os

    # Set umask to 0o000 so files are created with 666 permissions (rw-rw-rw--)
    os.umask(0o000)
    app(standalone_mode=True)


if __name__ == "__main__":
    main(sys.argv[1:])
