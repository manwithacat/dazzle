"""
Dazzle Runtime MCP tools.

This package provides tools for interacting with AppSpec and UISpec through MCP,
based on Runtime-MCP-Spec-v1.md specification.

Split into focused modules:

- definitions.py - Tool definitions
- handlers.py - Tool call handlers
- components.py - Built-in component registry
- adapter_examples.py - Adapter implementation examples
"""

from dazzle.mcp.server.state import get_state as _get_state

# Re-export public API
from .components import LAYOUT_TYPES, PATTERN_COMPONENTS, PRIMITIVE_COMPONENTS
from .definitions import RUNTIME_TOOL_NAMES, get_runtime_tools
from .handlers import handle_runtime_tool


# Backward-compatible shims — delegate to ServerState singleton.
def set_appspec_data(spec: dict) -> None:  # type: ignore[type-arg]
    _get_state().appspec_data = spec


def get_appspec_data() -> dict | None:  # type: ignore[type-arg]
    return _get_state().appspec_data


def set_ui_spec(spec: dict) -> None:  # type: ignore[type-arg]
    _get_state().ui_spec = spec


def get_ui_spec() -> dict | None:  # type: ignore[type-arg]
    return _get_state().ui_spec


def get_or_create_ui_spec() -> dict:  # type: ignore[type-arg]
    return _get_state().get_or_create_ui_spec()


__all__ = [
    # Tool definitions
    "get_runtime_tools",
    "RUNTIME_TOOL_NAMES",
    # Tool handler
    "handle_runtime_tool",
    # State management
    "set_appspec_data",
    "get_appspec_data",
    "set_ui_spec",
    "get_ui_spec",
    "get_or_create_ui_spec",
    # Component constants
    "PRIMITIVE_COMPONENTS",
    "PATTERN_COMPONENTS",
    "LAYOUT_TYPES",
]
