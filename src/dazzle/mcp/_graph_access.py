"""Safe accessor for the Knowledge Graph singleton.

Centralises the try/except-import pattern so that modules outside
``dazzle.mcp.server`` can reach the KG without hard-depending on the
MCP server being initialised.
"""

from __future__ import annotations

from typing import Any


def get_kg() -> Any:
    """Return the active :class:`KnowledgeGraph`, or *None* if unavailable."""
    try:
        from dazzle.mcp.server.state import get_knowledge_graph

        return get_knowledge_graph()
    except Exception:
        return None
