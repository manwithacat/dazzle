"""
DNR (Dazzle Native Runtime) MCP tools.

This module re-exports the modular DNR tools from the dnr_tools_impl package.
The implementation has been split into smaller, focused modules for better
maintainability and LLM context handling.

For implementation details, see the dnr_tools_impl/ package:
- dnr_tools_impl/state.py - State management for backend and UI specs
- dnr_tools_impl/definitions.py - Tool definitions
- dnr_tools_impl/handlers.py - Tool call handlers
- dnr_tools_impl/components.py - Built-in component registry
- dnr_tools_impl/adapter_examples.py - Adapter implementation examples
"""

# Re-export everything from the dnr_tools_impl package for backwards compatibility
from .dnr_tools_impl import (
    DNR_TOOL_NAMES,
    LAYOUT_TYPES,
    PATTERN_COMPONENTS,
    PRIMITIVE_COMPONENTS,
    get_backend_spec,
    get_dnr_tools,
    get_or_create_ui_spec,
    get_ui_spec,
    handle_dnr_tool,
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
