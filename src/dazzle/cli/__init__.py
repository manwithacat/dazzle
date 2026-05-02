"""
DAZZLE CLI Package.

This package contains the main CLI application and modularized sub-commands:

- runtime_impl/: Runtime commands (serve, build, stop, etc.)
- project.py: Project commands (init, validate, lint, etc.)
- vocab.py: Vocabulary management commands
- testing.py: Test commands
- e2e.py: Docker-based E2E testing
- mcp.py: MCP server commands
- specs.py: Specification generation commands (OpenAPI, AsyncAPI)
- deploy.py: Deploy commands
- stubs.py: Stub generation commands
- story.py: Story commands
- events.py: Event system commands
- migrate.py: Migration commands
- db.py: Database migration commands (Alembic)
- pitch.py: Pitch deck commands
- utils.py: Shared utilities
"""

import os
import sys
from pathlib import Path

import typer

from dazzle.cli.utils import version_callback

# =============================================================================
# Main Application
# =============================================================================

app = typer.Typer(
    help="""DAZZLE - DSL-first app generator

Command Types:
  - Project Creation: init
  - Project Operations: validate, lint, inspect, analyze-spec
  - Runtime: serve, build, stop, logs, status
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
    env: str = typer.Option(
        "",
        "--env",
        help="Environment profile from dazzle.toml (e.g. staging, production)",
    ),
) -> None:
    """DAZZLE CLI main callback for global options."""
    from dazzle.cli.env import resolve_env_name, set_active_env

    resolved = resolve_env_name(env)
    if resolved:
        set_active_env(resolved)


# =============================================================================
# Project Commands (top-level)
# =============================================================================
from dazzle.cli.project import (  # noqa: E402
    analyze_spec_command,
    example_command,
    init_command,
    inspect_command,
    layout_plan_command,
    lint_command,
    validate_command,
)

app.command(name="init")(init_command)
app.command(name="validate")(validate_command)
app.command(name="lint")(lint_command)
app.command(name="inspect")(inspect_command)
app.command(name="layout-plan")(layout_plan_command)
app.command(name="analyze-spec")(analyze_spec_command)
app.command(name="example")(example_command)

# Doctor command
from dazzle.cli.doctor import doctor_command  # noqa: E402

app.command(name="doctor")(doctor_command)

# Coverage command — framework-artefact coverage audit across example apps
from dazzle.cli.coverage import coverage_command  # noqa: E402

app.command(name="coverage")(coverage_command)

# Sweep command group — unified health check across every example app.
# `dazzle sweep examples` runs validate + lint + framework coverage snapshot
# and emits a single report suitable for weekly scheduled runs.
from dazzle.cli.sweep import sweep_examples_command  # noqa: E402

_sweep_app = typer.Typer(help="Run unified health checks across example apps.")
_sweep_app.command(name="examples")(sweep_examples_command)
app.add_typer(_sweep_app, name="sweep")


# Version command — mirrors `dazzle --version`. The subcommand form is
# what `brew test dazzle` (in the homebrew-tap validate-formula
# workflow) invokes, and what most CLI conventions (`npm version`,
# `docker version`) use. Adding this as a proper subcommand also lets
# tab-completion discover it.
@app.command(name="version")
def version_command(
    full: bool = typer.Option(
        False,
        "--full",
        help=(
            "Include feature-availability flags (python_available, "
            "lsp_available, llm_available) for automation consumers."
        ),
    ),
) -> None:
    """Show version and environment information."""
    from dazzle.cli.utils import print_version_info

    print_version_info(full=full)


# Grammar command
def grammar_command(
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path (defaults to docs/reference/grammar.md)",
    ),
    stdout: bool = typer.Option(
        False,
        "--stdout",
        help="Print to stdout instead of writing a file",
    ),
) -> None:
    """Regenerate the DSL grammar reference from parser source code."""
    from dazzle.core.grammar_gen import generate_grammar, write_grammar

    if stdout:
        typer.echo(generate_grammar())
    else:
        out_path = output if output else None
        path = write_grammar(out_path)
        typer.echo(f"Grammar written to {path}")


app.command(name="grammar")(grammar_command)


# =============================================================================
# Discoverability Commands
# =============================================================================


@app.command(name="commands")
def commands_command(
    category: str | None = typer.Option(None, "--category", "-c", help="Filter by category"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """List all available CLI commands with descriptions."""
    from dazzle.mcp.cli_help import _get_commands

    cmds = _get_commands()
    if category:
        cmds = {k: v for k, v in cmds.items() if v.get("category", "").lower() == category.lower()}

    if json_output:
        import json

        typer.echo(json.dumps(cmds, indent=2))
        return

    # Group by category
    by_cat: dict[str, list[tuple[str, str]]] = {}
    for cmd, info in sorted(cmds.items()):
        cat = info.get("category", "Other")
        by_cat.setdefault(cat, []).append((cmd, info.get("description", "")))

    for cat in sorted(by_cat):
        typer.echo(f"\n{cat}:")
        for cmd, desc in by_cat[cat]:
            typer.echo(f"  dazzle {cmd:30s} {desc[:60]}")


@app.command(name="search")
def search_command(
    keyword: str = typer.Argument(..., help="Keyword to search for"),
) -> None:
    """Search commands by keyword (name, description, or category)."""
    from dazzle.mcp.cli_help import search_commands

    results = search_commands(keyword)
    if not results:
        typer.echo(f"No commands found matching '{keyword}'")
        raise typer.Exit(1)

    typer.echo(f"Commands matching '{keyword}':\n")
    for r in results:
        typer.echo(f"  dazzle {r['command']:30s} {r['description'][:60]}")


# =============================================================================
# Runtime Commands (formerly under 'dnr' sub-app, now top-level)
# =============================================================================
from dazzle.cli.runtime_impl import (  # noqa: E402
    build_api_command,
    build_command,
    build_ui_command,
    check_command,
    info_command,
    logs_command,
    migrate_command,
    rebuild_command,
    schema_command,
    serve_command,
    status_command,
    stop_command,
)

app.command(name="serve")(serve_command)
app.command(name="build")(build_command)
app.command(name="build-ui")(build_ui_command)
app.command(name="build-api")(build_api_command)
# `dazzle build-css` removed in v0.62 (Phase 4 teardown of build_css.py).
app.command(name="info")(info_command)
app.command(name="stop")(stop_command)
app.command(name="rebuild")(rebuild_command)
app.command(name="logs")(logs_command)
app.command(name="status")(status_command)
app.command(name="migrate")(migrate_command)
app.command(name="schema")(schema_command)
app.command(name="check")(check_command)

# Database shell command
from dazzle.cli.dbshell import dbshell_command  # noqa: E402

app.command(name="dbshell")(dbshell_command)


# =============================================================================
# Sub-apps
# =============================================================================
from dazzle.cli.agent_commands import agent_app  # noqa: E402
from dazzle.cli.analytics import analytics_app  # noqa: E402
from dazzle.cli.api_pack import api_pack_app  # noqa: E402
from dazzle.cli.auth import auth_app  # noqa: E402
from dazzle.cli.backup import backup_app  # noqa: E402
from dazzle.cli.compliance import compliance_app  # noqa: E402
from dazzle.cli.composition import composition_app  # noqa: E402
from dazzle.cli.conformance import conformance_app  # noqa: E402
from dazzle.cli.contribution import contribution_app  # noqa: E402
from dazzle.cli.db import db_app  # noqa: E402
from dazzle.cli.demo import demo_app  # noqa: E402
from dazzle.cli.deploy import deploy_app  # noqa: E402
from dazzle.cli.discovery import discovery_app  # noqa: E402
from dazzle.cli.docs import docs_app  # noqa: E402
from dazzle.cli.e2e import e2e_app  # noqa: E402
from dazzle.cli.events import dlq_app, events_app, outbox_app  # noqa: E402
from dazzle.cli.feedback import feedback_app  # noqa: E402
from dazzle.cli.fitness import fitness_app  # noqa: E402
from dazzle.cli.kg import kg_app  # noqa: E402
from dazzle.cli.lsp import lsp_app  # noqa: E402
from dazzle.cli.mcp import mcp_app  # noqa: E402
from dazzle.cli.migrate import migrate_app  # noqa: E402
from dazzle.cli.mock import mock_app  # noqa: E402
from dazzle.cli.nightly import nightly_app  # noqa: E402
from dazzle.cli.overrides import overrides_app  # noqa: E402
from dazzle.cli.param import param_app  # noqa: E402
from dazzle.cli.pipeline import pipeline_app  # noqa: E402
from dazzle.cli.pitch import pitch_app  # noqa: E402
from dazzle.cli.process_cli import process_app  # noqa: E402
from dazzle.cli.pulse import pulse_app  # noqa: E402
from dazzle.cli.qa import qa_app  # noqa: E402
from dazzle.cli.quality import quality_app  # noqa: E402
from dazzle.cli.rbac import rbac_app  # noqa: E402
from dazzle.cli.rhythm import rhythm_app  # noqa: E402
from dazzle.cli.sentinel import sentinel_app  # noqa: E402
from dazzle.cli.specs import specs_app  # noqa: E402
from dazzle.cli.story import story_app  # noqa: E402
from dazzle.cli.stubs import stubs_app  # noqa: E402
from dazzle.cli.tenant import tenant_app  # noqa: E402
from dazzle.cli.test_design import test_design_app  # noqa: E402
from dazzle.cli.testing import test_app  # noqa: E402
from dazzle.cli.theme import theme_app  # noqa: E402
from dazzle.cli.ux import ux_app  # noqa: E402
from dazzle.cli.vocab import vocab_app  # noqa: E402

app.add_typer(analytics_app, name="analytics")
app.add_typer(agent_app, name="agent")
app.add_typer(api_pack_app, name="api-pack")
app.add_typer(auth_app, name="auth")
app.add_typer(compliance_app, name="compliance")
app.add_typer(conformance_app, name="conformance")
app.add_typer(backup_app, name="backup")
app.add_typer(composition_app, name="composition")
app.add_typer(contribution_app, name="contribution")
app.add_typer(db_app, name="db")
app.add_typer(demo_app, name="demo")
app.add_typer(discovery_app, name="discovery")
app.add_typer(feedback_app, name="feedback")
app.add_typer(fitness_app, name="fitness")
app.add_typer(docs_app, name="docs")
app.add_typer(vocab_app, name="vocab")
app.add_typer(stubs_app, name="stubs")
app.add_typer(story_app, name="story")
app.add_typer(tenant_app, name="tenant")
app.add_typer(theme_app, name="theme")
app.add_typer(test_app, name="test")
app.add_typer(e2e_app, name="e2e")
app.add_typer(specs_app, name="specs")
app.add_typer(deploy_app, name="deploy")
app.add_typer(events_app, name="events")
app.add_typer(dlq_app, name="dlq")
app.add_typer(outbox_app, name="outbox")
app.add_typer(migrate_app, name="process-migrate")
app.add_typer(nightly_app, name="nightly")
app.add_typer(pipeline_app, name="pipeline")
app.add_typer(pitch_app, name="pitch")
app.add_typer(pulse_app, name="pulse")
app.add_typer(quality_app, name="quality")
app.add_typer(rbac_app, name="rbac")
app.add_typer(kg_app, name="kg")
app.add_typer(lsp_app, name="lsp")
app.add_typer(mcp_app, name="mcp")
app.add_typer(mock_app, name="mock")
app.add_typer(process_app, name="process")
app.add_typer(rhythm_app, name="rhythm")
app.add_typer(qa_app, name="qa")
app.add_typer(sentinel_app, name="sentinel")
app.add_typer(ux_app, name="ux")
app.add_typer(test_design_app, name="test-design")
app.add_typer(overrides_app, name="overrides")
app.add_typer(param_app, name="param")

from dazzle.cli.i18n import i18n_app  # noqa: E402
from dazzle.cli.inspect_api import inspect_api_app  # noqa: E402

app.add_typer(inspect_api_app, name="inspect-api")
app.add_typer(i18n_app, name="i18n")


# =============================================================================
# Main Entry Point
# =============================================================================


def main(argv: list[str] | None = None) -> None:
    """Main CLI entry point."""
    # Set umask so files are created with 666 permissions
    os.umask(0o000)
    app(standalone_mode=True)


if __name__ == "__main__":
    main(sys.argv[1:])


__all__ = [
    "app",
    "main",
]
