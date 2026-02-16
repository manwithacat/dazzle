"""Entity CRUD handlers for the Knowledge Graph."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._serialization import entity_to_dict

if TYPE_CHECKING:
    from ..store import KnowledgeGraph


class EntityHandlers:
    """Handles entity create, get, list, and delete operations."""

    def __init__(self, graph: KnowledgeGraph):
        self._graph = graph

    def handle_create_entity(
        self,
        entity_id: str,
        name: str,
        entity_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create or update an entity."""
        entity = self._graph.create_entity(
            entity_id=entity_id,
            name=name,
            entity_type=entity_type,
            metadata=metadata,
        )
        return entity_to_dict(entity)

    def handle_get_entity(self, entity_id: str) -> dict[str, Any]:
        """Get an entity by ID."""
        entity = self._graph.get_entity(entity_id)
        if not entity:
            return {"error": f"Entity not found: {entity_id}"}
        return entity_to_dict(entity)

    def handle_delete_entity(self, entity_id: str) -> dict[str, Any]:
        """Delete an entity."""
        deleted = self._graph.delete_entity(entity_id)
        return {"deleted": deleted, "entity_id": entity_id}

    def handle_list_entities(
        self,
        entity_type: str | None = None,
        name_pattern: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List entities with filtering."""
        entities = self._graph.list_entities(
            entity_type=entity_type,
            name_pattern=name_pattern,
            limit=limit,
            offset=offset,
        )
        return {
            "entities": [entity_to_dict(e) for e in entities],
            "count": len(entities),
        }
