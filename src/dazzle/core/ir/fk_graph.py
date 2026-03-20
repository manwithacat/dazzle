"""FK graph for scope path validation in predicate algebra.

Builds a directed graph of foreign-key relationships between entities so that
dotted scope paths (e.g. ``manuscript.teacher.department.school_id``) can be
validated and resolved at compile time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .domain import EntitySpec


@dataclass(frozen=True)
class FKEdge:
    """A single directed FK edge in the entity graph.

    Attributes:
        from_entity: The entity that holds the FK column.
        fk_field: The FK column name (e.g. ``teacher_id``).
        to_entity: The referenced entity name.
    """

    from_entity: str
    fk_field: str
    to_entity: str


@dataclass(frozen=True)
class PathStep:
    """One resolved hop in a scope path traversal.

    Attributes:
        from_entity: Entity we are traversing *from*.
        fk_field: The FK column used for this hop.
        target_entity: Entity we land on after the hop.
        terminal_field: Set only on the last step — the field name that is the
            actual comparison target (may equal ``fk_field``).
    """

    from_entity: str
    fk_field: str
    target_entity: str
    terminal_field: str | None = None


@dataclass
class FKGraph:
    """Directed FK relationship graph built from a list of :class:`EntitySpec`.

    Internal state:
        _edges: ``{entity_name: {fk_field: to_entity}}``
        _fields: ``{entity_name: {field_name}}`` — *all* fields, not just FKs.
    """

    _edges: dict[str, dict[str, str]] = field(default_factory=dict)
    _fields: dict[str, set[str]] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_entities(cls, entities: list[EntitySpec]) -> FKGraph:
        """Build an :class:`FKGraph` from a list of entity specifications."""
        graph = cls()

        for entity in entities:
            name = entity.name
            graph._edges.setdefault(name, {})
            graph._fields.setdefault(name, set())

            for f in entity.fields:
                graph._fields[name].add(f.name)

                kind = f.type.kind
                kind_val: str = kind.value if hasattr(kind, "value") else str(kind)

                if kind_val in ("ref", "belongs_to") and f.type.ref_entity:
                    graph._edges[name][f.name] = f.type.ref_entity

        return graph

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def entity_names(self) -> set[str]:
        """Return the set of entity names known to this graph."""
        return set(self._fields.keys())

    def has_edge(self, entity: str, fk_field: str) -> bool:
        """Return *True* if *entity* has a FK column named *fk_field*."""
        return fk_field in self._edges.get(entity, {})

    def resolve_target(self, entity: str, fk_field: str) -> str | None:
        """Return the target entity name for *fk_field* on *entity*, or *None*."""
        return self._edges.get(entity, {}).get(fk_field)

    def field_exists(self, entity: str, field_name: str) -> bool:
        """Return *True* if *field_name* is a known field on *entity*."""
        return field_name in self._fields.get(entity, set())

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------

    def resolve_segment(self, entity: str, segment: str) -> tuple[str, str]:
        """Resolve one path segment to ``(fk_field, target_entity)``.

        Tries two strategies in order:

        1. **Exact match** — *segment* is itself the FK field name
           (e.g. ``teacher_id``).
        2. **Relation name** — *segment* + ``_id`` is the FK field name
           (e.g. ``teacher`` → ``teacher_id``).

        Raises:
            ValueError: If no matching FK edge is found.
        """
        edges = self._edges.get(entity, {})

        # 1. Exact FK field name
        if segment in edges:
            return segment, edges[segment]

        # 2. Relation name → append _id
        candidate = f"{segment}_id"
        if candidate in edges:
            return candidate, edges[candidate]

        raise ValueError(
            f"Entity '{entity}' has no FK for segment '{segment}' "
            f"(tried '{segment}' and '{candidate}'). "
            f"Available FKs: {sorted(edges.keys()) or 'none'}"
        )

    def resolve_path(self, start_entity: str, path: list[str]) -> list[PathStep]:
        """Validate and resolve a full dotted FK path to a list of :class:`PathStep`.

        The last segment is treated as the terminal field (the column being
        compared in the scope predicate).  All preceding segments must be
        resolvable FK hops.

        Args:
            start_entity: The root entity for the path (e.g. ``"Manuscript"``).
            path: Ordered list of segment names parsed from the dotted path
                  (e.g. ``["teacher", "department", "school_id"]``).

        Returns:
            A list of :class:`PathStep` objects, one per segment.

        Raises:
            ValueError: If *path* is empty or any segment cannot be resolved.
        """
        if not path:
            raise ValueError("Path must not be empty.")

        steps: list[PathStep] = []
        current_entity = start_entity

        for idx, segment in enumerate(path):
            is_last = idx == len(path) - 1

            fk_field, target_entity = self.resolve_segment(current_entity, segment)

            steps.append(
                PathStep(
                    from_entity=current_entity,
                    fk_field=fk_field,
                    target_entity=target_entity,
                    terminal_field=fk_field if is_last else None,
                )
            )
            current_entity = target_entity

        return steps
