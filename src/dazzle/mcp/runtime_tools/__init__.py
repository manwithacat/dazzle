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

# Re-export public API
from .components import LAYOUT_TYPES, PATTERN_COMPONENTS, PRIMITIVE_COMPONENTS
from .definitions import RUNTIME_TOOL_NAMES, get_runtime_tools
from .handlers import handle_runtime_tool

__all__ = [
    # Tool definitions
    "get_runtime_tools",
    "RUNTIME_TOOL_NAMES",
    # Tool handler
    "handle_runtime_tool",
    # Component constants
    "PRIMITIVE_COMPONENTS",
    "PATTERN_COMPONENTS",
    "LAYOUT_TYPES",
]
