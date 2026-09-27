"""MCP server setup and configuration utilities."""

import json
import logging
import sys
from hashlib import sha256
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


def _valid_registration_root(project_root: Path | None) -> bool:
    if project_root is None:
        return True
    is_project = (project_root / "dazzle.toml").is_file()
    is_framework = (project_root / "src" / "dazzle").is_dir() and (
        project_root / "examples"
    ).is_dir()
    if is_project or is_framework:
        return True
    logger.error("Not a Dazzle project or framework checkout: %s", project_root)
    return False


def _registration_server_name(project_root: Path | None, name: str | None) -> str | None:
    if name is not None:
        if not name or not all(c.isalnum() or c in "-_" for c in name):
            logger.error("Invalid MCP server name: %r", name)
            return None
        return name
    if project_root is None:
        return "dazzle"
    suffix = sha256(str(project_root).encode()).hexdigest()[:8]
    return f"dazzle-{project_root.name}-{suffix}"


def register_mcp_server(
    force: bool = False,
    working_dir: Path | None = None,
    name: str | None = None,
) -> bool:
    """
    Register DAZZLE MCP server in Claude Code config.

    Args:
        force: If True, overwrite existing DAZZLE server config
        working_dir: Optional project root. Registers a distinct, pinned server.
        name: Override the generated server name (for replacing an existing entry).

    Returns:
        True if registration successful, False otherwise
    """
    config_path = get_claude_config_path()
    if not config_path:
        return False

    project_root = working_dir.resolve() if working_dir is not None else None
    if not _valid_registration_root(project_root):
        return False

    # Detect Python executable
    python_path = sys.executable

    # New MCP server config
    dazzle_config: dict[str, Any] = {
        "command": python_path,
        "args": ["-m", "dazzle.mcp"],
        "env": {},
        "autoStart": True,
    }
    if project_root is not None:
        dazzle_config["args"].extend(["--working-dir", str(project_root)])
    server_name = _registration_server_name(project_root, name)
    if server_name is None:
        return False

    # Load existing config
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {"mcpServers": {}}

        # Check if already registered
        if server_name in existing.get("mcpServers", {}) and not force:
            print(f"DAZZLE MCP server {server_name} already registered at {config_path}")
            print("Use --force to overwrite")
            return True
    else:
        existing = {"mcpServers": {}}

    # Add/update DAZZLE server
    existing.setdefault("mcpServers", {})[server_name] = dazzle_config

    # Write back
    try:
        config_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
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
        config = json.loads(config_path.read_text(encoding="utf-8"))
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
