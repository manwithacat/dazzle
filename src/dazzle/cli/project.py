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

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer

from dazzle.cli.utils import load_project_appspec
from dazzle.core.admin_builder import format_injected_as_dsl
from dazzle.core.anti_turing import AntiTuringValidator
from dazzle.core.capabilities import suggest_capability, unknown_capability_ids
from dazzle.core.discovery import Relevance
from dazzle.core.errors import DazzleError, ParseError
from dazzle.core.fileset import discover_dsl_files
from dazzle.core.init_impl import (
    InitError,
    init_project,
    list_examples,
    reset_project,
    verify_project,
)
from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.core.manifest import load_manifest, resolve_api_url, resolve_site_url
from dazzle.core.parser import parse_modules
from dazzle.core.renderer_registry import known_renderer_names
from dazzle.core.sitespec_loader import SiteSpecError, load_sitespec, sitespec_exists
from dazzle.core.spec_loader import load_spec

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
    relevance: list[Relevance] | None = None,
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
        for r in relevance:
            example_ref = ""
            if r.examples:
                e = r.examples[0]
                example_ref = f" in {e.app}/{e.file}:{e.line}"
            typer.echo(f"  {r.context} — {r.capability}{example_ref}")


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


def _job_handler_errors(appspec: object, root: Path) -> list[str]:
    """#1490: statically check each job ``run: module:fn`` handler resolves.

    Unlike a runtime-registered renderer (#1413, advisory-only), a job's
    ``run:`` is a real importable module path, so validate *can* check it
    without booting: the module must be a file under the project root or an
    importable installed package. A handler whose module is neither would
    ``ModuleNotFoundError`` the moment the job fires (cron tick / entity event),
    long after validate passed — exactly the "passes validate, fails at runtime"
    class the fuzz sweep flags. Purely filesystem + ``find_spec`` (project root
    is not on ``sys.path`` here, so ``find_spec`` only resolves installed
    packages — a clean discriminator with no project-side import effects).
    """
    import importlib.util

    errors: list[str] = []
    for job in getattr(appspec, "jobs", None) or []:
        run = (getattr(job, "run", "") or "").strip()
        if not run:
            continue
        # `module:fn` (preferred) or `module.fn`; module is everything before
        # the `:`, else the dotted path minus the trailing attribute.
        module_name = run.split(":", 1)[0] if ":" in run else run.rsplit(".", 1)[0]
        if not module_name:
            continue
        rel = module_name.replace(".", "/")
        if (root / f"{rel}.py").is_file() or (root / rel / "__init__.py").is_file():
            continue  # project module present
        try:
            installed = importlib.util.find_spec(module_name) is not None
        except Exception:
            installed = False
        if not installed:
            job_name = getattr(job, "name", "?")
            errors.append(
                f"job '{job_name}' run handler '{run}' — module '{module_name}' "
                f"not found under the project root and not importable. Create "
                f"{rel}.py exporting the handler, or fix the `run:` path (#1490)."
            )
    return errors


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

        # #1490: statically verify declared job `run:` handlers resolve.
        errors.extend(_job_handler_errors(appspec, root))

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
        appspec = load_project_appspec(root)

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


def _resolve_analyze_spec_input(spec_file: str | None) -> tuple[str, str]:
    """Load spec content + display label for analyze-spec (raises typer.Exit)."""
    if spec_file:
        spec_path = Path(spec_file)
        if not spec_path.exists():
            typer.echo(f"Specification not found: {spec_file}", err=True)
            raise typer.Exit(code=1)
        if spec_path.is_dir():
            project_root = spec_path.parent if spec_path.name == "spec" else spec_path
            spec_result = load_spec(project_root, include_sources=True)
            return spec_result.content, f"{spec_file}/ ({spec_result.file_count} files)"
        return spec_path.read_text(encoding="utf-8"), spec_file

    spec_result = load_spec(Path.cwd(), include_sources=True)
    if spec_result.is_empty:
        typer.echo("No specification found. Create SPEC.md or spec/ directory.", err=True)
        raise typer.Exit(code=1)
    if spec_result.source_type == "directory":
        return spec_result.content, f"spec/ ({spec_result.file_count} files)"
    return spec_result.content, "SPEC.md"


def _run_offline_analyze_spec(spec_content: str) -> None:
    """Deterministic extract — same path as MCP discover_entities (#1631)."""
    # Deferred: MCP handlers are optional at CLI import time (#1438 cycle wall).
    from dazzle.mcp.server.handlers.spec_analyze import handle_spec_analyze

    typer.echo("   Mode: offline (deterministic; no LLM)")
    try:
        raw = handle_spec_analyze({"operation": "discover_entities", "spec_text": spec_content})
        data = json.loads(raw)
        if "error" in data:
            typer.echo(f"Error: {data['error']}", err=True)
            raise typer.Exit(code=1)
        entities = data.get("entities", [])
        typer.echo(f"\n🔍 Offline extract: {len(entities)} entity candidates")
        for ent in entities[:30]:
            name = ent.get("name", "?")
            src = ent.get("source", "")
            typ = ent.get("type", "")
            typer.echo(f"  • {name}  ({typ}, {src})")
        if len(entities) > 30:
            typer.echo(f"  … and {len(entities) - 30} more")
        typer.echo(f"\n{data.get('hint', '')}")
        typer.echo("\nNext step: hand-author DSL from the brief + knowledge concepts;")
        typer.echo("treat this extract as untrusted draft (bootstrap_pollution / #1631).")
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Offline extract failed: {e}", err=True)
        raise typer.Exit(code=1)


def _run_llm_analyze_spec(
    spec_content: str,
    *,
    provider: str,
    timeout: float,
    interactive: bool,
) -> None:
    """LLM analyze-spec path with loud timeout (#1631)."""
    try:
        from dazzle.llm import LLMProvider, SpecAnalyzer
    except ImportError:
        typer.echo("LLM support not available. Install with: pip install dazzle[llm]", err=True)
        typer.echo("Or use: dazzle analyze-spec --offline", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"   Provider: {provider}  timeout={timeout}s")
    try:
        provider_enum = LLMProvider(provider)
    except ValueError:
        typer.echo(f"Invalid provider: {provider}. Use: anthropic, openai, claude_cli", err=True)
        raise typer.Exit(code=1)

    analyzer = SpecAnalyzer(provider=provider_enum, timeout=timeout)
    typer.echo("\n🔍 Analyzing specification...")
    try:
        analysis = analyzer.analyze(spec_content)
        results = analysis.model_dump()
        _print_analysis_summary(results)
        if interactive:
            _run_interactive_qa(analyzer, results)
        typer.echo("\nNext step: hand this analysis to a Dazzle agent in-session")
        typer.echo("to author the DSL — structural authoring is not delegated to")
        typer.echo("external API calls (see CLAUDE.md / #1222).")
        typer.echo("Prefer offline hand-author when bootstrap pollution is a risk (#1631).")
    except Exception as e:
        err_name = type(e).__name__
        typer.echo(f"Error ({err_name}): {e}", err=True)
        if "timeout" in err_name.lower() or "timeout" in str(e).lower():
            typer.echo(
                f"analyze-spec timed out after {timeout}s. "
                "Retry with a higher --timeout, use --offline for deterministic extract, "
                "or hand-author from the brief (bootstrap_pollution / #1631).",
                err=True,
            )
        import traceback

        traceback.print_exc()
        raise typer.Exit(code=1)


def analyze_spec_command(
    spec_file: str | None = typer.Argument(
        None,
        help="Specification file or directory. If omitted, auto-detects spec/ directory or SPEC.md",
    ),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Interactive Q&A mode"),
    provider: str = typer.Option("anthropic", "--provider", "-p", help="LLM provider"),
    offline: bool = typer.Option(
        False,
        "--offline",
        help="Deterministic extract (no LLM) — same path as MCP discover_entities (#1631)",
    ),
    timeout: float = typer.Option(
        90.0,
        "--timeout",
        help="LLM call timeout seconds; fail loud on hang (#1631). Ignored with --offline.",
    ),
) -> None:
    """
    Analyze a specification file. Prints structured analysis
    (entities, personas, business rules, state machines) for an agent
    in-session to use as context when authoring DSL.

    Default path uses an LLM (with timeout). Prefer ``--offline`` for a
    deterministic extract that refuses markdown-table chrome entities
    (#1631). Bootstrap / discover_entities share that offline path.

    DSL synthesis is NOT performed here — Dazzle structural authoring
    stays in the agent session (#1222). An in-session Claude Code agent
    holds the framework-specific knowledge to write valid, idiomatic
    DSL; an out-of-context API call cannot. Run this command to get the
    analysis, then have the agent author the DSL with that context.

    Supports flexible spec organization:
    - spec/ directory with multiple markdown files
    - SPEC.md single file (backward compatible)
    - Explicit file path as argument
    """
    spec_content, spec_display = _resolve_analyze_spec_input(spec_file)
    typer.echo(f"📄 Analyzing: {spec_display}")
    if offline:
        _run_offline_analyze_spec(spec_content)
        return
    _run_llm_analyze_spec(spec_content, provider=provider, timeout=timeout, interactive=interactive)


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
            with open(readme_file, encoding="utf-8") as f:
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
        _api_url = resolve_api_url()
        _site_url = resolve_site_url()
        console.print(Text("This will start:", style="bright_black"))
        console.print(Text(f"  • Backend API at {_api_url}", style="bright_black"))
        console.print(Text(f"  • Frontend UI at {_site_url}", style="bright_black"))
        console.print(Text(f"  • API docs at {_api_url}/docs", style="bright_black"))

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
    "init_command",
    "validate_command",
    "lint_command",
    "inspect_command",
    "layout_plan_command",
    "analyze_spec_command",
    "example_command",
]
