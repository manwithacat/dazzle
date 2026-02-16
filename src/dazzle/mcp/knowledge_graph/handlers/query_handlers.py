"""Graph query and traversal handlers for the Knowledge Graph."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._serialization import entity_to_dict, relation_to_dict

if TYPE_CHECKING:
    from ..store import KnowledgeGraph


class QueryHandlers:
    """Handles graph traversal, search, adjacency, and capability map operations."""

    def __init__(self, graph: KnowledgeGraph):
        self._graph = graph

    # =========================================================================
    # Graph Traversal
    # =========================================================================

    def handle_find_paths(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 5,
        relation_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """Find paths between two entities."""
        paths = self._graph.find_paths(
            source_id=source_id,
            target_id=target_id,
            max_depth=max_depth,
            relation_types=relation_types,
        )
        return {
            "source": source_id,
            "target": target_id,
            "paths": [
                {
                    "path": p.path,
                    "relations": p.relations,
                    "length": p.length,
                }
                for p in paths
            ],
            "count": len(paths),
        }

    def handle_get_neighbourhood(
        self,
        entity_id: str,
        depth: int = 1,
        relation_types: list[str] | None = None,
        direction: str = "both",
    ) -> dict[str, Any]:
        """Get neighborhood of an entity."""
        result = self._graph.get_neighbourhood(
            entity_id=entity_id,
            depth=depth,
            relation_types=relation_types,
            direction=direction,
        )
        return {
            "center": result["center"],
            "entities": [entity_to_dict(e) for e in result["entities"]],
            "relations": [relation_to_dict(r) for r in result["relations"]],
            "entity_count": len(result["entities"]),
            "relation_count": len(result["relations"]),
        }

    def handle_get_dependents(
        self,
        entity_id: str,
        relation_types: list[str] | None = None,
        transitive: bool = False,
        max_depth: int = 5,
    ) -> dict[str, Any]:
        """Get entities that depend on this entity."""
        entities = self._graph.get_dependents(
            entity_id=entity_id,
            relation_types=relation_types,
            transitive=transitive,
            max_depth=max_depth,
        )
        return {
            "entity_id": entity_id,
            "dependents": [entity_to_dict(e) for e in entities],
            "count": len(entities),
            "transitive": transitive,
        }

    def handle_get_dependencies(
        self,
        entity_id: str,
        relation_types: list[str] | None = None,
        transitive: bool = False,
        max_depth: int = 5,
    ) -> dict[str, Any]:
        """Get entities this entity depends on."""
        entities = self._graph.get_dependencies(
            entity_id=entity_id,
            relation_types=relation_types,
            transitive=transitive,
            max_depth=max_depth,
        )
        return {
            "entity_id": entity_id,
            "dependencies": [entity_to_dict(e) for e in entities],
            "count": len(entities),
            "transitive": transitive,
        }

    # =========================================================================
    # Search / SQL
    # =========================================================================

    def handle_query(
        self,
        text: str,
        entity_types: list[str] | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search entities by text."""
        entities = self._graph.query(
            text=text,
            entity_types=entity_types,
            limit=limit,
        )
        return {
            "query": text,
            "entities": [entity_to_dict(e) for e in entities],
            "count": len(entities),
        }

    def handle_query_sql(
        self,
        sql: str,
        params: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Execute raw SQL query."""
        try:
            results = self._graph.query_sql(sql, params)
            return {"results": results, "count": len(results)}
        except ValueError as e:
            return {"error": str(e)}

    def handle_get_stats(self) -> dict[str, Any]:
        """Get graph statistics."""
        return self._graph.get_stats()

    # =========================================================================
    # Adjacency & Capability Map
    # =========================================================================

    def handle_compute_adjacency(
        self,
        node_a: str,
        node_b: str,
        max_distance: int = 2,
    ) -> dict[str, Any]:
        """Compute shortest distance between two graph nodes."""
        distance = self._graph.compute_adjacency(node_a, node_b, max_distance)
        return {
            "node_a": node_a,
            "node_b": node_b,
            "distance": distance,
            "within_boundary": 0 <= distance <= max_distance,
        }

    def handle_persona_capability_map(
        self,
        persona_id: str,
    ) -> dict[str, Any]:
        """Get capability map for a persona (reachable workspaces, surfaces, entities)."""
        if not persona_id.startswith("persona:"):
            persona_id = f"persona:{persona_id}"

        cap_map = self._graph.persona_capability_map(persona_id)
        return {
            "persona_id": persona_id,
            "workspaces": [entity_to_dict(e) for e in cap_map["workspaces"]],
            "surfaces": [entity_to_dict(e) for e in cap_map["surfaces"]],
            "entities": [entity_to_dict(e) for e in cap_map["entities"]],
            "stories": [entity_to_dict(e) for e in cap_map["stories"]],
            "workspace_count": len(cap_map["workspaces"]),
            "surface_count": len(cap_map["surfaces"]),
            "entity_count": len(cap_map["entities"]),
            "story_count": len(cap_map["stories"]),
        }
