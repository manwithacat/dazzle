"""
Port allocation for Dazzle serve.

Provides deterministic port assignment based on project name to prevent
collisions when running multiple Dazzle instances in parallel.

Strategy:
- Hash the project name to get a deterministic offset
- UI port: 3000 + offset (range: 3000-3999)
- API port: 8000 + offset (range: 8000-8999)

This allows multiple agents/developers to work on different projects
without port conflicts, while keeping ports predictable per project.
"""

from __future__ import annotations

import hashlib
import json
import socket
from pathlib import Path
from typing import NamedTuple


class PortAllocation(NamedTuple):
    """Allocated ports for a Dazzle instance."""

    ui_port: int
    api_port: int
    project_name: str


# Port ranges
UI_PORT_BASE = 3000
UI_PORT_RANGE = 1000  # 3000-3999
API_PORT_BASE = 8000
API_PORT_RANGE = 1000  # 8000-8999

# Runtime state file
RUNTIME_FILE = ".dazzle/runtime.json"


def hash_project_name(project_name: str) -> int:
    """
    Generate a deterministic hash offset from project name.

    Args:
        project_name: Project identifier (from manifest or directory name)

    Returns:
        Integer offset in range [0, 999]
    """
    # Use MD5 for speed (not security-sensitive)
    h = hashlib.md5(project_name.encode(), usedforsecurity=False).hexdigest()
    # Take first 8 hex chars and mod by range
    return int(h[:8], 16) % UI_PORT_RANGE


def allocate_ports(
    project_name: str,
    ui_port: int | None = None,
    api_port: int | None = None,
) -> PortAllocation:
    """
    Allocate ports for a Dazzle instance.

    If explicit ports are provided, use those. Otherwise, compute
    deterministic ports based on project name.

    Args:
        project_name: Project identifier
        ui_port: Explicit UI port (overrides auto-allocation)
        api_port: Explicit API port (overrides auto-allocation)

    Returns:
        PortAllocation with ui_port, api_port, and project_name
    """
    offset = hash_project_name(project_name)

    return PortAllocation(
        ui_port=ui_port if ui_port is not None else UI_PORT_BASE + offset,
        api_port=api_port if api_port is not None else API_PORT_BASE + offset,
        project_name=project_name,
    )


def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """
    Check if a port is available for binding.

    Args:
        port: Port number to check
        host: Host to check on

    Returns:
        True if port is available, False if in use
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def find_available_ports(
    project_name: str,
    ui_port: int | None = None,
    api_port: int | None = None,
    host: str = "127.0.0.1",
) -> PortAllocation:
    """
    Find available ports, falling back to alternatives if needed.

    First tries the deterministic ports based on project name.
    If those are in use, searches for the next available ports.

    Args:
        project_name: Project identifier
        ui_port: Explicit UI port preference
        api_port: Explicit API port preference
        host: Host to bind to

    Returns:
        PortAllocation with available ports
    """
    # Start with allocated ports
    alloc = allocate_ports(project_name, ui_port, api_port)

    # Check if preferred ports are available
    final_ui = alloc.ui_port
    final_api = alloc.api_port

    # If UI port is taken, find next available
    if not is_port_available(final_ui, host):
        for offset in range(1, UI_PORT_RANGE):
            candidate = UI_PORT_BASE + ((alloc.ui_port - UI_PORT_BASE + offset) % UI_PORT_RANGE)
            if is_port_available(candidate, host):
                final_ui = candidate
                break

    # If API port is taken, find next available
    if not is_port_available(final_api, host):
        for offset in range(1, API_PORT_RANGE):
            candidate = API_PORT_BASE + ((alloc.api_port - API_PORT_BASE + offset) % API_PORT_RANGE)
            if is_port_available(candidate, host):
                final_api = candidate
                break

    return PortAllocation(
        ui_port=final_ui,
        api_port=final_api,
        project_name=project_name,
    )


def write_runtime_file(project_root: Path, allocation: PortAllocation) -> Path:
    """
    Write runtime state file with current port allocation.

    This file can be read by E2E tests and other tools to discover
    the ports for a running Dazzle instance.

    Args:
        project_root: Project root directory
        allocation: Current port allocation

    Returns:
        Path to the runtime file
    """
    runtime_dir = project_root / ".dazzle"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    runtime_file = runtime_dir / "runtime.json"
    runtime_data = {
        "project_name": allocation.project_name,
        "ui_port": allocation.ui_port,
        "api_port": allocation.api_port,
        "ui_url": f"http://localhost:{allocation.ui_port}",
        "api_url": f"http://localhost:{allocation.api_port}",
    }

    runtime_file.write_text(json.dumps(runtime_data, indent=2))
    return runtime_file


def read_runtime_file(project_root: Path) -> PortAllocation | None:
    """
    Read runtime state file to get current port allocation.

    Args:
        project_root: Project root directory

    Returns:
        PortAllocation if file exists, None otherwise
    """
    runtime_file = project_root / ".dazzle" / "runtime.json"
    if not runtime_file.exists():
        return None

    try:
        data = json.loads(runtime_file.read_text())
        return PortAllocation(
            ui_port=data["ui_port"],
            api_port=data["api_port"],
            project_name=data["project_name"],
        )
    except (json.JSONDecodeError, KeyError):
        return None


def clear_runtime_file(project_root: Path) -> None:
    """
    Remove runtime state file when server stops.

    Args:
        project_root: Project root directory
    """
    runtime_file = project_root / ".dazzle" / "runtime.json"
    if runtime_file.exists():
        runtime_file.unlink()
