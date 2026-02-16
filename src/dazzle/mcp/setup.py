"""MCP server setup and configuration utilities."""

import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def get_claude_config_path() -> Path | None:
    """
    Find Claude Code config directory.

    Tries common locations in priority order:
    1. ~/.config/claude-code/mcp_servers.json (Linux/Mac XDG)
    2. ~/.claude/mcp_servers.json (Mac/Unix legacy)
    3. ~/Library/Application Support/Claude Code/mcp_servers.json (Mac app)

    Returns:
        Path to mcp_servers.json (may not exist yet), or None if no suitable location found
    """
    home = Path.home()

    # Try common locations
    candidates = [
        home / ".config" / "claude-code" / "mcp_servers.json",
        home / ".claude" / "mcp_servers.json",
        home / "Library" / "Application Support" / "Claude Code" / "mcp_servers.json",
    ]

    # Return first location where parent directory exists
    for path in candidates:
        if path.parent.exists():
            return path

    # Default to ~/.claude/ (create parent if needed)
    default = home / ".claude" / "mcp_servers.json"
    default.parent.mkdir(parents=True, exist_ok=True)
    return default


def register_mcp_server(force: bool = False) -> bool:
    """
    Register DAZZLE MCP server in Claude Code config.

    Args:
        force: If True, overwrite existing DAZZLE server config

    Returns:
        True if registration successful, False otherwise
    """
    config_path = get_claude_config_path()
    if not config_path:
        return False

    # Detect Python executable
    python_path = sys.executable

    # New MCP server config
    dazzle_config = {
        "command": python_path,
        "args": ["-m", "dazzle.mcp"],
        "env": {},
        "autoStart": True,
    }

    # Load existing config
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text())
        except json.JSONDecodeError:
            existing = {"mcpServers": {}}

        # Check if already registered
        if "dazzle" in existing.get("mcpServers", {}) and not force:
            print(f"DAZZLE MCP server already registered at {config_path}")
            print("Use --force to overwrite")
            return True
    else:
        existing = {"mcpServers": {}}

    # Add/update DAZZLE server
    existing.setdefault("mcpServers", {})["dazzle"] = dazzle_config

    # Write back
    try:
        config_path.write_text(json.dumps(existing, indent=2))
        return True
    except (OSError, PermissionError) as e:
        print(f"Error writing config: {e}", file=sys.stderr)
        return False


def check_mcp_server() -> dict[str, Any]:
    """
    Check MCP server registration and availability.

    Returns:
        Dictionary with status information:
        - status: "not_registered" | "registered" | "error"
        - registered: bool
        - config_path: str | None
        - server_command: str | None
        - tools: list[str] (if available)
    """
    config_path = get_claude_config_path()

    status: dict[str, Any] = {
        "status": "not_registered",
        "registered": False,
        "config_path": str(config_path) if config_path else None,
        "server_command": None,
        "tools": [],
    }

    if not config_path or not config_path.exists():
        return status

    try:
        config = json.loads(config_path.read_text())
    except json.JSONDecodeError:
        status["status"] = "error"
        status["error"] = "Invalid JSON in config file"
        return status

    # Check if DAZZLE server is registered
    mcp_servers = config.get("mcpServers", {})
    if "dazzle" in mcp_servers:
        status["registered"] = True
        status["status"] = "registered"

        server_config = mcp_servers["dazzle"]
        command = server_config.get("command", "")
        args = server_config.get("args", [])
        status["server_command"] = f"{command} {' '.join(args)}"

        # Try to enumerate tools (best effort)
        try:
            status["tools"] = _get_available_tools()
        except Exception:
            logger.debug("Failed to enumerate MCP tools", exc_info=True)

    return status


def _get_available_tools() -> list[str]:
    """
    Get list of available MCP tools.

    Returns:
        List of tool names
    """
    # Import here to avoid circular dependency
    try:
        from dazzle.mcp.server.tools_consolidated import get_all_consolidated_tools

        tools = get_all_consolidated_tools()
        return [tool.name for tool in tools]
    except Exception:
        # Fallback to known tools
        return [
            "validate_dsl",
            "list_modules",
            "inspect_entity",
            "inspect_surface",
            "build",
            "analyze_patterns",
            "lint_project",
            "lookup_concept",
            "find_examples",
        ]
