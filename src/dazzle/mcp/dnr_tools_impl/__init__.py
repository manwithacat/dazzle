"""
DNR (Dazzle Native Runtime) MCP tools.

This package provides tools for interacting with BackendSpec and UISpec through MCP,
based on DNR-MCP-Spec-v1.md specification.

The monolithic dnr_tools.py has been split into focused modules:

- state.py - State management for backend and UI specs
- definitions.py - Tool definitions
- handlers.py - Tool call handlers
- components.py - Built-in component registry
- adapter_examples.py - Adapter implementation examples
"""

from __future__ import annotations

# Re-export public API
from .components import LAYOUT_TYPES, PATTERN_COMPONENTS, PRIMITIVE_COMPONENTS
from .definitions import DNR_TOOL_NAMES, get_dnr_tools
from .handlers import handle_dnr_tool
from .state import (
    get_backend_spec,
    get_or_create_ui_spec,
    get_ui_spec,
    set_backend_spec,
    set_ui_spec,
)

__all__ = [
    # Tool definitions
    "get_dnr_tools",
    "DNR_TOOL_NAMES",
    # Tool handler
    "handle_dnr_tool",
    # State management
    "set_backend_spec",
    "get_backend_spec",
    "set_ui_spec",
    "get_ui_spec",
    "get_or_create_ui_spec",
    # Component constants
    "PRIMITIVE_COMPONENTS",
    "PATTERN_COMPONENTS",
    "LAYOUT_TYPES",
]
