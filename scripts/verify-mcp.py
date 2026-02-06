#!/usr/bin/env python3
"""
Verify MCP server functionality.

This script checks that the DAZZLE MCP server:
1. Can be imported
2. Can start without errors
3. Responds to tool calls

Run before committing to ensure MCP functionality is not broken.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_imports() -> bool:
    """Test that MCP modules can be imported."""
    print("Testing MCP imports...")
    try:
        from dazzle.mcp import (
            server,  # noqa: F401
            setup,  # noqa: F401
            tools,  # noqa: F401
        )
        from dazzle.mcp.server import run_server  # noqa: F401

        print("  ✓ All MCP modules imported successfully")
        return True
    except ImportError as e:
        print(f"  ✗ Import failed: {e}")
        return False


def test_tool_definitions() -> bool:
    """Test that tool definitions are valid."""
    print("Testing tool definitions...")
    try:
        from dazzle.mcp.server.tools import get_all_tools

        tools = get_all_tools()
        if not tools:
            print("  ✗ No tools defined")
            return False

        print(f"  ✓ Found {len(tools)} tools:")
        for tool in tools[:5]:  # Show first 5
            print(f"    - {tool.name}")
        if len(tools) > 5:
            print(f"    ... and {len(tools) - 5} more")

        return True
    except Exception as e:
        print(f"  ✗ Tool definition error: {e}")
        return False


def test_setup_functions() -> bool:
    """Test that setup functions work."""
    print("Testing setup functions...")
    try:
        from dazzle.mcp.setup import check_mcp_server, get_claude_config_path

        config_path = get_claude_config_path()
        print(f"  ✓ Config path: {config_path or 'Not found (OK for CI)'}")

        status = check_mcp_server()
        print(f"  ✓ MCP status: {status['status']}")
        print(f"    Registered: {status['registered']}")

        return True
    except Exception as e:
        print(f"  ✗ Setup function error: {e}")
        return False


async def test_server_initialization() -> bool:
    """Test that the MCP server can be initialized."""
    print("Testing server initialization...")
    try:
        from dazzle.mcp.server import list_tools_handler, server

        if server is None:
            print("  ✗ Server instance is None")
            return False

        # Test that the list_tools_handler works
        tools = await list_tools_handler()
        if not tools:
            print("  ✗ list_tools_handler returned empty list")
            return False

        print(f"  ✓ Server initialized with {len(tools)} tools")
        return True
    except Exception as e:
        print(f"  ✗ Server initialization error: {e}")
        return False


async def test_tool_registration() -> bool:
    """Test that all expected tools are registered and published."""
    print("Testing tool registration...")
    try:
        from dazzle.mcp.server import is_dev_mode, list_tools_handler

        # Get tools from the server handler
        published_tools = await list_tools_handler()
        published_names = {t.name for t in published_tools}

        # Check for consolidated tool names
        expected_consolidated_tools = {
            "dsl",
            "api_pack",
            "story",
            "demo_data",
            "test_design",
            "sitespec",
            "semantics",
            "process",
            "dsl_test",
            "e2e_test",
            "status",
            "knowledge",
        }
        missing = expected_consolidated_tools - published_names
        if missing:
            print(f"  ✗ Missing consolidated tools: {missing}")
            return False
        print(f"  ✓ Consolidated mode: {len(published_names)} tools published")
        print(f"    Consolidated tools: {len(expected_consolidated_tools)} verified")

        # Dev mode tools (only expected when in dev mode)
        dev_mode_tools = {
            "list_projects",
            "select_project",
            "get_active_project",
            "validate_all_projects",
        }

        # Check dev mode tools
        if is_dev_mode():
            missing_dev = dev_mode_tools - published_names
            if missing_dev:
                print(f"  ✗ Missing dev mode tools: {missing_dev}")
                return False
            print(f"  ✓ Dev mode enabled - {len(dev_mode_tools)} dev tools present")

        return True

    except Exception as e:
        print(f"  ✗ Tool registration error: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_cli_entry_point() -> bool:
    """Test that the CLI entry point works."""
    print("Testing CLI entry point...")
    try:
        from dazzle.mcp.__main__ import main  # noqa: F401

        print("  ✓ CLI entry point importable")
        return True
    except Exception as e:
        print(f"  ✗ CLI entry point error: {e}")
        return False


def main() -> int:
    """Run all MCP verification tests."""
    print("=" * 60)
    print("DAZZLE MCP Server Verification")
    print("=" * 60)
    print()

    results = []

    # Run tests
    results.append(("Imports", test_imports()))
    results.append(("Tool definitions", test_tool_definitions()))
    results.append(("Setup functions", test_setup_functions()))
    results.append(("Server initialization", asyncio.run(test_server_initialization())))
    results.append(("Tool registration", asyncio.run(test_tool_registration())))
    results.append(("CLI entry point", test_cli_entry_point()))

    # Summary
    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for name, success in results:
        status = "✓" if success else "✗"
        print(f"  {status} {name}")

    print()
    print(f"Passed: {passed}/{total}")

    if passed == total:
        print("\n✓ All MCP verification tests passed!")
        print("\nThe MCP server is ready for Claude Code integration.")
        return 0
    else:
        print("\n✗ Some MCP verification tests failed!")
        print("\nPlease fix the errors before committing.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
