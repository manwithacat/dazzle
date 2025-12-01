"""
DAZZLE CLI - Entry point.

This module provides backward compatibility by importing the CLI from dazzle.cli_legacy.
The CLI has been modularized into the dazzle.cli package:

- cli/dnr.py: DNR (Dazzle Native Runtime) commands
- cli/vocab.py: Vocabulary management commands
- cli/testing.py: E2E testing commands
- cli/e2e.py: Docker-based E2E testing
- cli/mcp.py: MCP server commands
- cli/utils.py: Shared utilities

For new code, prefer importing from dazzle.cli (the package).
"""

# Re-export everything from the legacy module for backward compatibility
from dazzle.cli_legacy import (
    # Main app
    app,
    main,
    # Version
    __version__,
    # Utility functions
    get_version,
    version_callback,
    _print_human_diagnostics,
    _print_vscode_diagnostics,
    _print_vscode_parse_error,
    _is_directory_empty,
    # Core commands
    init,
    validate,
    lint,
    inspect,
    build,
    stacks,
    example,
    # Analysis commands
    layout_plan,
    analyze_spec,
    infra,
    # Sub-apps (still defined in legacy for now)
    vocab_app,
    dnr_app,
    test_app,
    e2e_app,
)

# For the package structure
if __name__ == "__main__":
    import sys
    main(sys.argv[1:])
