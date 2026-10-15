"""
Knowledge Graph population handlers.

The MCP server populates the knowledge graph at startup and on project switch:
from code files (``handle_auto_populate``) and from the project's DSL
(``handle_populate_from_appspec``). Agents read the graph through the
``knowledge`` MCP tool; the ``kg_*`` tool facade went with the ``graph`` tool
(flense ship I, its residue in ship AI).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .population_handlers import PopulationHandlers

if TYPE_CHECKING:
    from ..store import KnowledgeGraph

__all__ = ["KnowledgeGraphHandlers"]


class KnowledgeGraphHandlers:
    """Populates the knowledge graph from code files and the project AppSpec."""

    def __init__(self, graph: KnowledgeGraph):
        self._graph = graph
        self._population = PopulationHandlers(graph)

    def handle_auto_populate(
        self,
        root_path: str,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        max_files: int = 500,
    ) -> dict[str, Any]:
        """Auto-populate the knowledge graph from code files."""
        return self._population.handle_auto_populate(
            root_path, include_patterns, exclude_patterns, max_files
        )

    def handle_populate_from_appspec(
        self,
        project_path: str,
    ) -> dict[str, Any]:
        """Populate the knowledge graph from the project's DSL AppSpec."""
        return self._population.handle_populate_from_appspec(project_path)
