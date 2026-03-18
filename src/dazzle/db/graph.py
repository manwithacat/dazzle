"""Entity dependency graph utilities.

Computes FK dependency ordering from AppSpec entities.
Used by reset (leaf-first truncation) and cleanup (orphan detection).
"""

from __future__ import annotations

import logging
from graphlib import TopologicalSorter
from typing import Any

logger = logging.getLogger(__name__)

# Only these FieldTypeKind values create FK columns on the entity.
# has_many, has_one, embeds store FKs on the *other* entity.
_FK_KINDS = frozenset({"ref", "belongs_to"})


def build_dependency_graph(entities: list[Any]) -> dict[str, set[str]]:
    """Build {entity_name: set_of_dependency_names} from ref fields.

    Only includes REF/BELONGS_TO fields (which create FK columns).
    Refs to entities not in the list and self-references are excluded.
    """
    entity_names = {e.name for e in entities}
    graph: dict[str, set[str]] = {}

    for entity in entities:
        deps: set[str] = set()
        for f in entity.fields:
            if (
                f.type
                and f.type.kind in _FK_KINDS
                and f.type.ref_entity
                and f.type.ref_entity in entity_names
                and f.type.ref_entity != entity.name
            ):
                deps.add(f.type.ref_entity)
        graph[entity.name] = deps

    return graph


def parents_first(entities: list[Any]) -> list[str]:
    """Return entity names in parent-first order (for schema creation / data loading).

    Falls back to alphabetical on circular references.
    """
    graph = build_dependency_graph(entities)
    sorter = TopologicalSorter(graph)
    try:
        return list(sorter.static_order())
    except Exception:
        logger.warning("Circular FK references detected, falling back to alphabetical order")
        return sorted(graph.keys())


def leaves_first(entities: list[Any]) -> list[str]:
    """Return entity names in leaf-first order (for truncation / deletion).

    This is the reverse of parents_first.
    """
    return list(reversed(parents_first(entities)))


def get_ref_fields(entity: Any) -> list[Any]:
    """Return only fields that create FK columns (ref, belongs_to)."""
    return [f for f in entity.fields if f.type and f.type.kind in _FK_KINDS and f.type.ref_entity]
