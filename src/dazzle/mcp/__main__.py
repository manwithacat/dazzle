"""
MCP server entry point for DAZZLE.

Run with: python -m dazzle.mcp [--working-dir PATH]
"""

import argparse
import asyncio
import faulthandler
import signal
import sys
from pathlib import Path

from dazzle.mcp.server import run_server

# Enable faulthandler for debugging hung processes (#443).
# kill -SIGUSR1 <pid> dumps a Python traceback to stderr.
faulthandler.enable()
if sys.platform != "win32":
    faulthandler.register(signal.SIGUSR1)


def main() -> None:
    """Run the DAZZLE MCP server."""
    parser = argparse.ArgumentParser(description="DAZZLE MCP Server")
    parser.add_argument(
        "--working-dir",
        type=Path,
        default=Path.cwd(),
        help="Project root directory (default: current working directory)",
    )
    args = parser.parse_args()

    project_root = args.working_dir.resolve()
    asyncio.run(run_server(project_root))


if __name__ == "__main__":
    main()
