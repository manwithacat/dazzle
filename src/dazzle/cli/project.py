"""
Project commands for DAZZLE CLI.

Commands for creating, validating, and working with DAZZLE projects:
- init: Initialize a new project
- validate: Parse and validate DSL
- lint: Extended validation checks
- inspect: Inspect entities and surfaces
- analyze-spec: LLM-powered spec analysis
- example: Create project from example

For code generation, use:
- dazzle serve: Run your DSL directly (rapid iteration)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from dazzle.cli.utils import load_project_appspec
from dazzle.core.admin_builder import format_injected_as_dsl
from dazzle.core.anti_turing import AntiTuringValidator
from dazzle.core.capabilities import suggest_capability, unknown_capability_ids
from dazzle.core.discovery import RelevanceGroup
from dazzle.core.errors import DazzleError, ParseError
from dazzle.core.fileset import discover_dsl_files
from dazzle.core.init_impl import (
    InitError,
    init_project,
    list_examples,
)
from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules
from dazzle.core.renderer_registry import known_renderer_names
from dazzle.core.sitespec_loader import SiteSpecError, load_sitespec, sitespec_exists

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
    relevance: list[RelevanceGroup] | None = None,
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

    if relevance:
        typer.echo(f"\nRelevant capabilities ({len(relevance)}):")
        for group in relevance:
            places = f" x{group.occurrences}" if group.occurrences > 1 else ""
            example_ref = ""
            if group.examples:
                e = group.examples[0]
                more = f" (+{group.examples_total - 1} more)" if group.examples_total > 1 else ""
                example_ref = f" e.g. {e.app}: {e.context}{more}"
            typer.echo(f"  {group.capability}{places} — {group.kg_entity}{example_ref}")
            for context in group.contexts:
                typer.echo(f"      · {context}")


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


# =============================================================================
# Project Commands - These are registered directly on the main app
# =============================================================================

# Note: These command functions are defined here but registered on the main app
# in cli/__init__.py. They're top-level commands, not sub-commands.


_APP_SUBDIRS = (
    ("app", "Custom application code"),
    ("app/db", "Database operations (snapshots, migrations, fixups)"),
    ("app/sync", "External data integration (API clients, importers)"),
    ("app/render", "Document generation (PDF, reports)"),
    ("app/qa", "Quality assurance tooling"),
    ("app/demo", "Demo data generation and management"),
    ("scripts", "One-shot scripts (fixups, experiments)"),
)


def _scaffold_app_directory(
    target: Path,
    log: Callable[[str], None] | None = None,
) -> None:
    """Generate the recommended app/ directory structure (#715).

    Creates sub-packages with ``__init__.py`` files for production code,
    and a ``scripts/`` directory for one-shot scripts.
    """
    if log is None:

        def log(msg: str) -> None:
            pass

    log("Creating app/ directory structure...")
    for subdir, purpose in _APP_SUBDIRS:
        dir_path = target / subdir
        dir_path.mkdir(parents=True, exist_ok=True)
        init_file = dir_path / "__init__.py"
        if subdir != "scripts" and not init_file.exists():
            init_file.write_text(f'"""{purpose}."""\n', encoding="utf-8")
        log(f"  Created {subdir}/")

    # .gitkeep for scripts/ so it's tracked even when empty
    gitkeep = target / "scripts" / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.write_text("", encoding="utf-8")


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
    with_app: bool = typer.Option(
        False, "--with-app", help="Generate app/ directory structure for custom Python code"
    ),
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

    Use --with-app to also generate the recommended app/ directory structure
    for custom Python code (services, integrations, data generation).

    Examples:
        dazzle init                              # Init in current dir (if empty)
        dazzle init --here                       # Force init in current dir
        dazzle init ./my-project                 # Create new directory
        dazzle init --from simple_task           # Init from example (current dir)
        dazzle init ./my-app --from support_tickets  # New dir from example
        dazzle init --list                       # Show available examples
        dazzle init --no-llm --no-git            # Minimal setup
        dazzle init --with-app                   # Include app/ structure
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

        # Generate app/ structure if requested (#715)
        if with_app:
            _scaffold_app_directory(target, progress)

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


def _renderer_registration_advisory(extra_renderers: list[str]) -> str | None:
    """#1413: a static signpost for declared custom renderers.

    ``validate`` is deliberately static (~50ms, no boot), so it cannot see
    whether a renderer declared in ``[renderers] extra`` actually had its
    runtime handler registered — an unregistered renderer passes validate/lint
    but 500s (FragmentError) at request. Point the author at the boot-time gate
    that *can* confirm it (``dazzle inspect renderers --runtime`` exits non-zero
    on the mismatch). Returns ``None`` when no custom renderers are declared.
    """
    if not extra_renderers:
        return None
    names = ", ".join(sorted(extra_renderers))
    return (
        f"{len(extra_renderers)} custom renderer(s) declared in [renderers] extra "
        f"({names}). validate cannot confirm they are registered at runtime — an "
        f"unregistered renderer passes validate but 500s (FragmentError) at request. "
        f"Run `dazzle inspect renderers --runtime` to verify registration (#1413)."
    )


def _resolve_manifest(manifest: str, project: object) -> Path:
    """Resolve the manifest path from either a CLI call or a direct call.

    Tests and internal callers invoke `validate_command(...)` /
    `lint_command(...)` in-process, where typer's default is still an
    `OptionInfo` rather than `None`. Treating "not a Path" as "no project given"
    keeps both call shapes working — a `Path | None` option is not `None` when
    the function is called directly.
    """
    if isinstance(project, Path):
        return (project / "dazzle.toml").resolve()
    return Path(manifest).resolve()


def validate_command(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m", help="Path to dazzle.toml"),
    project: Path | None = typer.Option(
        None,
        "--project",
        "-p",
        help="Project root containing dazzle.toml (default: cwd)",
    ),
    format: str = typer.Option(
        "human", "--format", "-f", help="Output format: 'human' or 'vscode'"
    ),
) -> None:
    """
    Parse all DSL modules, resolve dependencies, and validate the merged AppSpec.

    Works from the current directory (which must contain dazzle.toml), or point
    at a project with ``-p``/``--project`` — which is what an agent working in the
    framework repo needs, since the repo root is not a Dazzle project (#1759:
    the documented command could not be copied without first guessing a cd).
    """
    manifest_path = _resolve_manifest(manifest, project)
    root = manifest_path.parent

    try:
        # Capability declarations must reference known capabilities (#1342).
        # Checked first so a bad [capabilities] id fails fast and clearly,
        # independent of DSL state.
        declared = load_manifest(manifest_path).capabilities.enabled
        bad_caps = unknown_capability_ids(declared)
        if bad_caps:
            for cid in bad_caps:
                hint = suggest_capability(cid)
                suffix = f" — did you mean '{hint}'?" if hint else ""
                typer.secho(
                    f"✗ Unknown capability '{cid}' in [capabilities].{suffix}",
                    fg=typer.colors.RED,
                    err=True,
                )
            raise typer.Exit(code=1)

        # #1438: importing api_kb registers its pack-ops provider into core's
        # validation registry so the `source=<pack>.<op>` typo check (#996) is active
        # — core no longer imports api_kb itself (core ↛ api_kb/mcp contract).
        import dazzle.api_kb  # noqa: F401

        appspec = load_project_appspec(root)
        errors, warnings, relevance = lint_appspec(appspec)

        # #1413: static signpost — validate can't see runtime renderer
        # registration, so nudge toward the boot-time gate when custom
        # renderers are declared.
        renderer_advisory = _renderer_registration_advisory(
            list(load_manifest(manifest_path).renderers.extra)
        )
        if renderer_advisory:
            warnings.append(renderer_advisory)

        # Statically parse sitespec.yaml (if present) so schema errors
        # surface at validate-time instead of being swallowed by the
        # try/except in serve.py / app_factory.py at boot.
        if sitespec_exists(root):
            try:
                load_sitespec(root)
            except SiteSpecError as e:
                typer.echo(f"sitespec.yaml: {e}", err=True)
                raise typer.Exit(code=1) from e

        if format == "vscode":
            _print_vscode_diagnostics(errors, warnings, root)
        else:
            _print_human_diagnostics(errors, warnings, appspec, relevance=relevance)

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
    project: Path | None = typer.Option(
        None,
        "--project",
        "-p",
        help="Project root containing dazzle.toml (default: cwd)",
    ),
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

    Works from the current directory, or point at a project with
    ``-p``/``--project`` (see `validate`).
    """
    manifest_path = _resolve_manifest(manifest, project)
    root = manifest_path.parent

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)

        # Anti-Turing validation (raw DSL content)
        if anti_turing:
            validator = AntiTuringValidator(strict=strict)
            all_violations = []

            for dsl_file in dsl_files:
                content = dsl_file.read_text(encoding="utf-8")
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
        appspec = build_appspec(modules, mf.project_root, known_renderers=known_renderer_names(mf))
        errors, warnings, relevance = lint_appspec(appspec, extended=True)

        # #1413: same static signpost as `validate` — point at the runtime gate
        # when custom renderers are declared (lint can't see registration either).
        renderer_advisory = _renderer_registration_advisory(list(mf.renderers.extra))
        if renderer_advisory:
            warnings.append(renderer_advisory)

        if format == "vscode":
            _print_vscode_diagnostics(errors, warnings, root)
        else:
            _print_human_diagnostics(errors, warnings, relevance=relevance)

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
    injected: bool = typer.Option(
        False,
        "--injected",
        help="Show framework auto-injected entities, surfaces, and workspaces "
        "(platform-admin infrastructure) as synthetic DSL.",
    ),
) -> None:
    """
    Inspect project entities, surfaces, and structure.
    """
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        appspec = load_project_appspec(root)

        if injected:
            typer.echo(format_injected_as_dsl(appspec))
            return

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


# Export all command functions
__all__ = [
    "init_command",
    "validate_command",
    "lint_command",
    "inspect_command",
]
