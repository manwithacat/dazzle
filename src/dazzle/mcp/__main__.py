"""
MCP server entry point for DAZZLE.

Run with: python -m dazzle.mcp.server
"""

import asyncio
import logging
import sys
from pathlib import Path

from dazzle.mcp.server import DazzleMCPServer

# Log to stderr to avoid interfering with JSON-RPC on stdout
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format='[%(asctime)s] %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Run the DAZZLE MCP server."""
    # Get project root from command line args or use cwd
    if len(sys.argv) > 1:
        project_root = Path(sys.argv[1]).resolve()
    else:
        project_root = Path.cwd()

    logger.info(f"Starting DAZZLE MCP server in {project_root}")

    try:
        server = DazzleMCPServer(project_root=project_root)
        await server.run()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
