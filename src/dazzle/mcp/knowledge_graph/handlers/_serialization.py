"""Shared serialization helpers for KG handler sub-modules."""

from __future__ import annotations

from typing import Any

from ..models import Entity, Relation


def entity_to_dict(entity: Entity) -> dict[str, Any]:
    """Convert entity to dict for JSON response."""
    return {
        "id": entity.id,
        "type": entity.entity_type,
        "name": entity.name,
        "metadata": entity.metadata,
        "created_at": entity.created_at,
        "updated_at": entity.updated_at,
    }


def relation_to_dict(relation: Relation) -> dict[str, Any]:
    """Convert relation to dict for JSON response."""
    return {
        "source_id": relation.source_id,
        "target_id": relation.target_id,
        "relation_type": relation.relation_type,
        "metadata": relation.metadata,
        "created_at": relation.created_at,
    }
