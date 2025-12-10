"""
DNR state management for MCP tools.

Stores active backend and UI specs in memory.
"""

from __future__ import annotations

from typing import Any

# Store active specs (would be persisted in real implementation)
_backend_spec: dict[str, Any] | None = None
_ui_spec: dict[str, Any] | None = None


def set_backend_spec(spec: dict[str, Any]) -> None:
    """Set the active backend spec."""
    global _backend_spec
    _backend_spec = spec


def get_backend_spec() -> dict[str, Any] | None:
    """Get the active backend spec."""
    return _backend_spec


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
