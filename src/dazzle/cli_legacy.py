"""
DAZZLE CLI Legacy Module.

This module provides the main CLI application and registers all commands.
Command implementations are imported from modular CLI modules in dazzle/cli/.

This file will eventually be replaced by a fully modular CLI in dazzle/cli/__init__.py.
"""

import platform
import sys
from pathlib import Path

import typer

# Version fallback - primary source is pyproject.toml via importlib.metadata
__version__ = "0.14.0"


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

        # Check ejection adapters
        ejection_adapters = []
        try:
            from dazzle.eject.adapters import AdapterRegistry

            ejection_adapters = sorted(
                AdapterRegistry.list_backends() + AdapterRegistry.list_frontends()
            )
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
        if ejection_adapters:
            typer.echo("Ejection Adapters:")
            for adapter in ejection_adapters:
                typer.echo(f"  - {adapter}")
        else:
            typer.echo("Ejection Adapters: None")

        raise typer.Exit()


# =============================================================================
# Main Application
# =============================================================================

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


# =============================================================================
# Project Commands (imported from cli.project)
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

# Register project commands with decorators
app.command(name="init")(init_command)
app.command(name="validate")(validate_command)
app.command(name="lint")(lint_command)
app.command(name="inspect")(inspect_command)
app.command(name="layout-plan")(layout_plan_command)
app.command(name="analyze-spec")(analyze_spec_command)
app.command(name="example")(example_command)


# =============================================================================
# Vocabulary Commands (imported from cli.vocab)
# =============================================================================
from dazzle.cli.vocab import vocab_app  # noqa: E402

app.add_typer(vocab_app, name="vocab")


# =============================================================================
# Stubs Commands (imported from cli.stubs)
# =============================================================================
from dazzle.cli.stubs import stubs_app  # noqa: E402

app.add_typer(stubs_app, name="stubs")


# =============================================================================
# MCP Commands (top-level for backward compatibility)
# =============================================================================


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
from dazzle.cli.dnr_impl import dnr_app  # noqa: E402

app.add_typer(dnr_app, name="dnr")


# =============================================================================
# Test Commands (imported from cli.testing)
# =============================================================================
from dazzle.cli.testing import test_app  # noqa: E402

app.add_typer(test_app, name="test")


# =============================================================================
# E2E Commands (imported from cli.e2e)
# =============================================================================
from dazzle.cli.e2e import e2e_app  # noqa: E402

app.add_typer(e2e_app, name="e2e")


# =============================================================================
# Eject Commands (imported from cli.eject)
# =============================================================================
from dazzle.cli.eject import eject_app  # noqa: E402

app.add_typer(eject_app, name="eject")


# =============================================================================
# Events Commands (imported from cli.events)
# =============================================================================
from dazzle.cli.events import dlq_app, events_app, outbox_app  # noqa: E402

app.add_typer(events_app, name="events")
app.add_typer(dlq_app, name="dlq")
app.add_typer(outbox_app, name="outbox")


# =============================================================================
# Main Entry Point
# =============================================================================


def main(argv: list[str] | None = None) -> None:
    import os

    # Set umask to 0o000 so files are created with 666 permissions (rw-rw-rw--)
    os.umask(0o000)
    app(standalone_mode=True)


if __name__ == "__main__":
    main(sys.argv[1:])
