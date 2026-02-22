"""
DNR state management for MCP tools.

Stores active AppSpec data and UI specs in memory.
"""

from __future__ import annotations

from typing import Any

# Store active specs (would be persisted in real implementation)
_appspec_data: dict[str, Any] | None = None
_ui_spec: dict[str, Any] | None = None


def set_appspec_data(spec: dict[str, Any]) -> None:
    """Set the active AppSpec data."""
    global _appspec_data
    _appspec_data = spec


def get_appspec_data() -> dict[str, Any] | None:
    """Get the active AppSpec data."""
    return _appspec_data


def set_ui_spec(spec: dict[str, Any]) -> None:
    """Set the active UI spec."""
    global _ui_spec
    _ui_spec = spec


def get_ui_spec() -> dict[str, Any] | None:
    """Get the active UI spec."""
    return _ui_spec


def get_or_create_ui_spec() -> dict[str, Any]:
    """Get the UI spec, creating a default if none exists."""
    global _ui_spec
    if _ui_spec is None:
        _ui_spec = {"name": "unnamed", "components": [], "workspaces": [], "themes": []}
    return _ui_spec
