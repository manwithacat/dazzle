"""
Knowledge Graph MCP Server.

SQLite-backed graph storage for entities and relations with
graph traversal capabilities (paths, neighborhoods, dependencies).

Designed to be low-overhead: auto-populates from codebase and
uses prefixed IDs for type inference (file:, module:, concept:, decision:).
"""

from __future__ import annotations

from .handlers import KnowledgeGraphHandlers
from .seed import ensure_seeded
from .store import KnowledgeGraph

__all__ = ["KnowledgeGraph", "KnowledgeGraphHandlers", "ensure_seeded"]
