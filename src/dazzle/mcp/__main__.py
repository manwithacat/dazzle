"""
MCP server entry point for DAZZLE.

Run with: python -m dazzle.mcp
"""

import asyncio
import sys
from pathlib import Path

from dazzle.mcp.server import run_server


def main() -> None:
    """Run the DAZZLE MCP server."""
    # Get project root from command line args or use cwd
    if len(sys.argv) > 1:
        project_root = Path(sys.argv[1]).resolve()
    else:
        project_root = Path.cwd()

    asyncio.run(run_server(project_root))


if __name__ == "__main__":
    main()
