"""
DAZZLE CLI Package.

This package contains the main CLI application and modularized sub-commands:

- runtime_impl/: Runtime commands (serve, build, stop, etc.)
- project.py: Project commands (init, validate, lint, etc.)
- vocab.py: Vocabulary management commands
- testing.py: Test commands
- e2e.py: E2E testing (UX coverage, viewport)
- mcp.py: MCP server commands
- deploy.py: Deploy commands
- story.py: Story commands
- db.py: Database migration commands (Alembic)
- utils.py: Shared utilities
"""

import os
import sys
from pathlib import Path

import typer

from dazzle.cli.utils import version_callback
from dazzle.core.grammar_gen import generate_grammar, write_grammar
from dazzle.perf.bootstrap import maybe_configure_tracer

maybe_configure_tracer()

# =============================================================================
# Main Application
# =============================================================================

app = typer.Typer(
    help="""DAZZLE - DSL-first app generator

Command Types:
  - Project Creation: init
  - Project Operations: validate, lint, inspect
  - Runtime: serve, build, migrate
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
    inspect_command,
    lint_command,
    validate_command,
)

app.command(name="validate")(validate_command)
app.command(name="lint")(lint_command)
# `inspect_command` (project entities/surfaces dumper) is registered
# as `dazzle inspect project` under the new inspect typer group —
# see the `app.add_typer(inspect_app, name="inspect")` registration
# below. Pre-v0.71.23 it lived at the top-level `dazzle inspect`;
# the rename moves it under the inspect group alongside `inspect
# renderers` / `inspect primitives` / etc. so the command tree has
# a single owner for the `inspect` namespace (#1120 fallout).

# Doctor command
from dazzle.cli.doctor import doctor_command  # noqa: E402

app.command(name="doctor")(doctor_command)

# Coverage command — framework-artefact coverage audit across example apps
from dazzle.cli.coverage import coverage_command  # noqa: E402

app.command(name="coverage")(coverage_command)

# Fragment-audit command — Fragment-rendering coverage for a single project
from dazzle.cli.fragment_audit import fragment_audit_command  # noqa: E402

app.command(name="fragment-audit")(fragment_audit_command)


# Version command — mirrors `dazzle --version`. The subcommand form is
# what `brew test dazzle` (in the homebrew-tap validate-formula
# workflow) invokes, and what most CLI conventions (`npm version`,
# `cargo version`) use. Adding this as a proper subcommand also lets
# tab-completion discover it.
@app.command(name="version")
def version_command(
    full: bool = typer.Option(
        False,
        "--full",
        help=(
            "Include feature-availability flags (python_available, "
            "llm_available) for automation consumers."
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
    migrate_command,
    serve_command,
)

app.command(name="serve")(serve_command)
app.command(name="build")(build_command)
app.command(name="build-ui")(build_ui_command)
app.command(name="build-api")(build_api_command)
app.command(name="migrate")(migrate_command)


# =============================================================================
# Sub-apps
# =============================================================================
from dazzle.cli.agent_commands import agent_app  # noqa: E402
from dazzle.cli.analytics import analytics_app  # noqa: E402
from dazzle.cli.auth import auth_app  # noqa: E402
from dazzle.cli.compliance import compliance_app  # noqa: E402
from dazzle.cli.db import db_app  # noqa: E402
from dazzle.cli.demo import demo_app  # noqa: E402
from dazzle.cli.deploy import deploy_app  # noqa: E402
from dazzle.cli.docs import docs_app  # noqa: E402
from dazzle.cli.e2e import e2e_app  # noqa: E402
from dazzle.cli.fitness import fitness_app  # noqa: E402
from dazzle.cli.mcp import mcp_app  # noqa: E402
from dazzle.cli.perf import perf_app  # noqa: E402
from dazzle.cli.pipeline import pipeline_app  # noqa: E402
from dazzle.cli.prove import prove_app  # noqa: E402
from dazzle.cli.qa import qa_app  # noqa: E402
from dazzle.cli.rbac import rbac_app  # noqa: E402
from dazzle.cli.representation import representation_app  # noqa: E402
from dazzle.cli.rhythm import rhythm_app  # noqa: E402
from dazzle.cli.scaffold import scaffold_app  # noqa: E402
from dazzle.cli.sentinel import sentinel_app  # noqa: E402
from dazzle.cli.signing import signing_app  # noqa: E402
from dazzle.cli.spec import spec_app  # noqa: E402
from dazzle.cli.story import story_app  # noqa: E402
from dazzle.cli.tenant import tenant_app  # noqa: E402
from dazzle.cli.testing import test_app  # noqa: E402
from dazzle.cli.ux import ux_app  # noqa: E402
from dazzle.cli.vocab import vocab_app  # noqa: E402

app.add_typer(analytics_app, name="analytics")
app.add_typer(agent_app, name="agent")
app.add_typer(auth_app, name="auth")
app.add_typer(compliance_app, name="compliance")
app.add_typer(db_app, name="db")
app.add_typer(demo_app, name="demo")
app.add_typer(fitness_app, name="fitness")
app.add_typer(docs_app, name="docs")
app.add_typer(vocab_app, name="vocab")
app.add_typer(scaffold_app, name="scaffold")
app.add_typer(prove_app, name="prove")
app.add_typer(representation_app, name="representation")
app.add_typer(story_app, name="story")
app.add_typer(tenant_app, name="tenant")
app.add_typer(test_app, name="test")
app.add_typer(e2e_app, name="e2e")
app.add_typer(signing_app, name="signing")
app.add_typer(spec_app, name="spec")
app.add_typer(deploy_app, name="deploy")
app.add_typer(pipeline_app, name="pipeline")
app.add_typer(perf_app, name="perf")
app.add_typer(rbac_app, name="rbac")
app.add_typer(mcp_app, name="mcp")
app.add_typer(rhythm_app, name="rhythm")
app.add_typer(qa_app, name="qa")
app.add_typer(sentinel_app, name="sentinel")
app.add_typer(ux_app, name="ux")

from dazzle.cli.inspect import inspect_app  # noqa: E402

# v0.71.23 (#1120): the old `dazzle inspect-api` is renamed to
# `dazzle inspect api` under the new top-level inspect group. The
# inspect group also adds renderers / primitives / routes / oauth-
# providers subcommands. Clean break — no alias is kept for the old
# top-level name per the project's clean-break policy.
#
# v0.71.24 fixup: the previous top-level `dazzle inspect` command
# (project entities/surfaces dumper from `cli/project.py`) is
# rehosted as `dazzle inspect project` to free the `inspect`
# namespace for the new group.
inspect_app.command(name="project")(inspect_command)
app.add_typer(inspect_app, name="inspect")


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
