"""
MCP (Model Context Protocol) CLI commands.

Commands for running and managing the DAZZLE MCP server.

Note: These are top-level commands (mcp, mcp-setup, mcp-check) not a subgroup.
They are exported as individual command functions and added directly to the main app.
"""

import asyncio
from pathlib import Path

import typer

# Create a Typer app for grouping purposes, but commands will be added
# to main app directly since they're top-level commands
mcp_app = typer.Typer(
    help="MCP (Model Context Protocol) server commands.",
    no_args_is_help=True,
)


@mcp_app.command("run")
def mcp_run(
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


@mcp_app.command("setup")
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


@mcp_app.command("check")
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
