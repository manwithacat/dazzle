"""
DAZZLE CLI Package.

This package contains modularized CLI components:

- dnr.py: DNR (Dazzle Native Runtime) commands
- vocab.py: Vocabulary management commands
- testing.py: E2E testing commands
- e2e.py: Docker-based E2E testing
- mcp.py: MCP server commands
- utils.py: Shared utilities

The main CLI entry point is in dazzle.cli_legacy (originally cli.py).
This package provides the modular structure for future migration.
"""

# Re-export the main app and entry point from cli_legacy
# Export the modular sub-apps (duplicates exist in cli_legacy for now)
from dazzle.cli.dnr import dnr_app
from dazzle.cli.e2e import e2e_app
from dazzle.cli.mcp import mcp, mcp_check, mcp_setup
from dazzle.cli.testing import test_app
from dazzle.cli.utils import get_version, version_callback
from dazzle.cli.vocab import vocab_app
from dazzle.cli_legacy import __version__, app, main

__all__ = [
    "__version__",
    "app",
    "main",
    # Sub-apps
    "dnr_app",
    "vocab_app",
    "test_app",
    "e2e_app",
    # MCP commands
    "mcp",
    "mcp_setup",
    "mcp_check",
    # Utilities
    "get_version",
    "version_callback",
]
