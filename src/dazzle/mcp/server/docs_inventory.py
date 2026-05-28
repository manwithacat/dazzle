"""MCP-tools doc inventory generator.

Registers the ``mcp_tools`` auto-source into ``dazzle.core.docs_gen`` so the
core doc generator can render the live MCP tool inventory without importing
``dazzle.mcp`` (preserves the core→mcp isolation boundary; smells check 1.3).

Importing this module is enough to register the generator — the CLI docs
command and the docs tests import it before calling ``generate_reference_docs``.
"""

from dazzle.core.docs_gen import register_auto_source, render_mcp_tools_inventory


def generate_mcp_tools_inventory() -> str:
    """Fetch the live MCP tool registry and render the inventory page."""
    from dazzle.mcp.server.tools_consolidated import get_all_consolidated_tools

    return render_mcp_tools_inventory(get_all_consolidated_tools())


register_auto_source("mcp_tools", generate_mcp_tools_inventory)
