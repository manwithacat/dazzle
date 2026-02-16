"""
Knowledge Graph MCP Server.

SQLite-backed graph storage for entities and relations with
graph traversal capabilities (paths, neighborhoods, dependencies).

Designed to be low-overhead: auto-populates from codebase and
uses prefixed IDs for type inference (file:, module:, concept:, decision:).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .handlers import KnowledgeGraphHandlers
    from .seed import ensure_seeded
    from .store import KnowledgeGraph

__all__ = ["KnowledgeGraph", "KnowledgeGraphHandlers", "ensure_seeded"]


def __getattr__(name: str) -> Any:  # noqa: ANN001
    """Lazy-load public names to break circular imports between store/handlers/seed."""
    if name == "KnowledgeGraph":
        from .store import KnowledgeGraph

        return KnowledgeGraph
    if name == "KnowledgeGraphHandlers":
        from .handlers import KnowledgeGraphHandlers

        return KnowledgeGraphHandlers
    if name == "ensure_seeded":
        from .seed import ensure_seeded

        return ensure_seeded
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
