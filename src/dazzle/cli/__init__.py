"""
DAZZLE CLI Package.

This package contains the main CLI application and modularized sub-commands:

- dnr_impl.py: DNR (Dazzle Native Runtime) commands
- project.py: Project commands (init, validate, lint, etc.)
- vocab.py: Vocabulary management commands
- testing.py: Test commands
- e2e.py: Docker-based E2E testing
- mcp.py: MCP server commands
- eject.py: Ejection commands
- deploy.py: Deploy commands
- stubs.py: Stub generation commands
- story.py: Story commands
- events.py: Event system commands
- migrate.py: Migration commands
- pitch.py: Pitch deck commands
- utils.py: Shared utilities
"""

import os
import sys

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
  - Runtime: dnr serve
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


# =============================================================================
# Sub-apps
# =============================================================================
from dazzle.cli.deploy import deploy_app  # noqa: E402
from dazzle.cli.dnr_impl import dnr_app  # noqa: E402
from dazzle.cli.e2e import e2e_app  # noqa: E402
from dazzle.cli.eject import eject_app  # noqa: E402
from dazzle.cli.events import dlq_app, events_app, outbox_app  # noqa: E402
from dazzle.cli.mcp import mcp_app  # noqa: E402
from dazzle.cli.migrate import migrate_app  # noqa: E402
from dazzle.cli.pitch import pitch_app  # noqa: E402
from dazzle.cli.story import story_app  # noqa: E402
from dazzle.cli.stubs import stubs_app  # noqa: E402
from dazzle.cli.testing import test_app  # noqa: E402
from dazzle.cli.vocab import vocab_app  # noqa: E402

app.add_typer(dnr_app, name="dnr")
app.add_typer(vocab_app, name="vocab")
app.add_typer(stubs_app, name="stubs")
app.add_typer(story_app, name="story")
app.add_typer(test_app, name="test")
app.add_typer(e2e_app, name="e2e")
app.add_typer(eject_app, name="eject")
app.add_typer(deploy_app, name="deploy")
app.add_typer(events_app, name="events")
app.add_typer(dlq_app, name="dlq")
app.add_typer(outbox_app, name="outbox")
app.add_typer(migrate_app, name="migrate")
app.add_typer(pitch_app, name="pitch")
app.add_typer(mcp_app, name="mcp")


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
