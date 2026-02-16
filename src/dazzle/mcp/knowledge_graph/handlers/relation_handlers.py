"""Relation management handlers for the Knowledge Graph."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._serialization import relation_to_dict

if TYPE_CHECKING:
    from ..store import KnowledgeGraph


class RelationHandlers:
    """Handles relation create, delete, and get operations."""

    def __init__(self, graph: KnowledgeGraph):
        self._graph = graph

    def handle_create_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a relation between entities."""
        relation = self._graph.create_relation(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            metadata=metadata,
        )
        return relation_to_dict(relation)

    def handle_delete_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
    ) -> dict[str, Any]:
        """Delete a relation."""
        deleted = self._graph.delete_relation(source_id, target_id, relation_type)
        return {
            "deleted": deleted,
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": relation_type,
        }

    def handle_get_relations(
        self,
        entity_id: str | None = None,
        relation_type: str | None = None,
        direction: str = "both",
    ) -> dict[str, Any]:
        """Get relations for an entity."""
        relations = self._graph.get_relations(
            entity_id=entity_id,
            relation_type=relation_type,
            direction=direction,
        )
        return {
            "relations": [relation_to_dict(r) for r in relations],
            "count": len(relations),
        }
