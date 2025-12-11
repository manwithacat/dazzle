#!/usr/bin/env python3
"""
Post-installation script for DAZZLE.

This script registers the DAZZLE MCP server with Claude Code.
It can be run manually after pip installation.

Usage:
    python -m scripts.post_install
    # or
    python scripts/post_install.py
"""

import sys


def main() -> int:
    """Run post-installation tasks."""
    try:
        # Import after ensuring DAZZLE is installed
        from dazzle.mcp.setup import check_mcp_server, register_mcp_server

        print("DAZZLE Post-Installation Setup")
        print("=" * 50)

        # Check current status
        status = check_mcp_server()

        if status.get("registered"):
            print("✅ DAZZLE MCP server is already registered")
            print(f"   Config: {status.get('config_path')}")
            print(f"   Command: {status.get('server_command')}")
            print("\nNo action needed. You're all set!")
            return 0

        print("Setting up DAZZLE MCP server for Claude Code...")
        print()

        # Register MCP server
        if register_mcp_server():
            print("✅ DAZZLE MCP server registered successfully")
            print()
            print("Next steps:")
            print("  1. Restart Claude Code")
            print("  2. Create or open a DAZZLE project:")
            print("     dazzle init my-project")
            print("     cd my-project")
            print('  3. Ask Claude: "What DAZZLE tools do you have access to?"')
            print()
            print("To verify registration:")
            print("  dazzle mcp-check")
            return 0
        else:
            print("❌ Failed to register MCP server")
            print()
            print("You can manually register later with:")
            print("  dazzle mcp-setup")
            return 1

    except ImportError as e:
        print("Error: DAZZLE not found. Is it installed?")
        print(f"Details: {e}")
        print()
        print("Install DAZZLE first:")
        print("  pip install dazzle")
        return 1
    except Exception as e:
        print(f"Error during post-installation: {e}")
        print()
        print("You can manually register the MCP server:")
        print("  dazzle mcp-setup")
        return 1


if __name__ == "__main__":
    sys.exit(main())
