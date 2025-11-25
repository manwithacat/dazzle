"""
DAZZLE MCP Server

Model Context Protocol server for DAZZLE integration with Claude Code.
Exposes DAZZLE CLI functionality as MCP tools, resources, and prompts.
"""

from .server import DazzleMCPServer

__all__ = ["DazzleMCPServer"]
