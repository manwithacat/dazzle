"""
Semantic index for DAZZLE DSL concepts.

This module is a thin wrapper that imports from the TOML-based
semantics_kb package for backwards compatibility.

The actual concept data is stored in TOML files in semantics_kb/
for better maintainability.
"""

# Re-export everything from semantics_kb for backwards compatibility
from dazzle.mcp.semantics_kb import (
    MCP_SEMANTICS_BUILD,
    MCP_SEMANTICS_VERSION,
    get_dsl_patterns,
    get_mcp_version,
    get_semantic_index,
    lookup_concept,
    reload_cache,
)

__all__ = [
    "get_mcp_version",
    "get_semantic_index",
    "lookup_concept",
    "get_dsl_patterns",
    "reload_cache",
    "MCP_SEMANTICS_VERSION",
    "MCP_SEMANTICS_BUILD",
]
