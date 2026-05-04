"""Safe accessor for the Knowledge Graph singleton.

Centralises the try/except-import pattern so that modules outside
``dazzle.mcp.server`` can reach the KG without hard-depending on the
MCP server being initialised.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def get_kg() -> Any:
    """Return the active :class:`KnowledgeGraph`, or *None* if unavailable."""
    try:
        from dazzle.mcp.server.state import get_knowledge_graph

        return get_knowledge_graph()
    except Exception:
        logger.debug("ignored exception in _graph_access.py:17", exc_info=True)
        return None
