"""
SQLAlchemy MetaData bridge for EntitySpec.

Converts DSL EntitySpec objects into SQLAlchemy Table objects on a shared
MetaData instance.  This gives us:

* Topologically-sorted DDL via ``metadata.create_all()``
* Automatic cycle handling for circular FKs (``use_alter=True``)
* A single source of truth that Alembic can diff against a live database

The module deliberately uses **SQLAlchemy Core only** — no ORM, no Session.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from dazzle_back.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType

if TYPE_CHECKING:
    import sqlalchemy

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports — sqlalchemy is an optional dependency (postgres extra)
# ---------------------------------------------------------------------------

_sa_imported = False
_sa: Any = None  # sqlalchemy module


def _ensure_sa() -> Any:
    """Import sqlalchemy on first use and return the module."""
    global _sa_imported, _sa
    if not _sa_imported:
        try:
            import sqlalchemy

            _sa = sqlalchemy
        except ImportError as exc:
            raise RuntimeError(
                "sqlalchemy is required for the SA schema bridge.  "
                "Install it with:  pip install dazzle"
            ) from exc
        _sa_imported = True
    return _sa


# ---------------------------------------------------------------------------
# Type mapping  (mirrors pg_backend._scalar_type_to_postgres)
# ---------------------------------------------------------------------------


def _scalar_type_to_sa(scalar_type: ScalarType) -> Any:
    """Map a DSL ScalarType to a SQLAlchemy column type instance."""
    sa = _ensure_sa()
    mapping: dict[ScalarType, Any] = {
        ScalarType.STR: sa.Text(),
        ScalarType.TEXT: sa.Text(),
        ScalarType.INT: sa.Integer(),
        ScalarType.DECIMAL: sa.Float(),
        ScalarType.BOOL: sa.Boolean(),
        ScalarType.DATE: sa.Text(),
        ScalarType.DATETIME: sa.Text(),
        ScalarType.UUID: sa.Text(),
        ScalarType.EMAIL: sa.Text(),
        ScalarType.URL: sa.Text(),
        ScalarType.JSON: sa.Text(),
    }
    return mapping.get(scalar_type, sa.Text())


def _field_type_to_sa(field_type: FieldType) -> Any:
    """Convert a DSL FieldType to a SQLAlchemy column type instance."""
    sa = _ensure_sa()
    if field_type.kind == "scalar" and field_type.scalar_type:
        return _scalar_type_to_sa(field_type.scalar_type)
    # enum and ref both store as TEXT in the current implementation
    return sa.Text()


# ---------------------------------------------------------------------------
# Column builder
# ---------------------------------------------------------------------------


def _find_circular_refs(entities: list[EntitySpec]) -> set[tuple[str, str]]:
    """Find entity pairs involved in circular FK references.

    Returns a set of (entity_name, ref_entity) edges that participate in
    cycles.  For a cycle A→B→A, both (A, B) and (B, A) are returned.
    """
    # Build adjacency list: entity → set of entities it references
    graph: dict[str, set[str]] = {}
    entity_names = {e.name for e in entities}
    for entity in entities:
        refs: set[str] = set()
        for field in entity.fields:
            if field.type.kind == "ref" and field.type.ref_entity:
                ref = field.type.ref_entity
                if ref in entity_names and ref != entity.name:  # skip self-refs
                    refs.add(ref)
        graph[entity.name] = refs

    # Find all edges that participate in any cycle via DFS
    cycle_edges: set[tuple[str, str]] = set()
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = dict.fromkeys(graph, WHITE)
    path: list[str] = []

    def dfs(node: str) -> None:
        color[node] = GRAY
        path.append(node)
        for neighbor in graph.get(node, set()):
            if color[neighbor] == GRAY:
                # Found a cycle — collect all edges in the cycle
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:]
                for k in range(len(cycle)):
                    cycle_edges.add((cycle[k], cycle[(k + 1) % len(cycle)]))
            elif color[neighbor] == WHITE:
                dfs(neighbor)
        path.pop()
        color[node] = BLACK

    for name in graph:
        if color[name] == WHITE:
            dfs(name)

    return cycle_edges


def _field_to_column(
    field: FieldSpec,
    entity_name: str,
    entity_names: set[str],
    circular_edges: set[tuple[str, str]] | None = None,
) -> Any:
    """Convert a single FieldSpec into a SQLAlchemy ``Column``."""
    sa = _ensure_sa()
    col_type = _field_type_to_sa(field.type)

    kwargs: dict[str, Any] = {}

    # Primary key
    if field.name == "id":
        kwargs["primary_key"] = True

    # Nullable / required
    if field.name != "id":
        kwargs["nullable"] = not field.required

    # Unique
    if getattr(field, "is_unique", False) or getattr(field, "unique", False):
        kwargs["unique"] = True

    # Default
    if field.default is not None:
        kwargs["server_default"] = sa.text(repr(field.default))

    # Foreign key for ref fields
    fk_args: list[Any] = []
    if field.type.kind == "ref" and field.type.ref_entity:
        ref_entity = field.type.ref_entity
        if ref_entity in entity_names:
            # use_alter=True defers FK to ALTER TABLE, breaking circular DDL deps
            is_self_ref = ref_entity == entity_name
            is_circular = circular_edges is not None and (entity_name, ref_entity) in circular_edges
            needs_alter = is_self_ref or is_circular
            fk_name = f"fk_{entity_name}_{field.name}_{ref_entity}" if needs_alter else None
            fk_args.append(
                sa.ForeignKey(
                    f"{ref_entity}.id",
                    use_alter=needs_alter,
                    name=fk_name,
                )
            )

    return sa.Column(field.name, col_type, *fk_args, **kwargs)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_metadata(entities: list[EntitySpec]) -> sqlalchemy.MetaData:
    """Convert a list of EntitySpec into a SQLAlchemy ``MetaData``.

    Each entity becomes a ``Table`` with columns derived from its fields.
    Foreign-key relationships are expressed via ``ForeignKey`` so that
    ``metadata.sorted_tables`` returns tables in dependency order and
    ``metadata.create_all()`` emits DDL in the correct order.

    Circular FK references (e.g. Department ↔ User) are detected and
    marked with ``use_alter=True`` so that the constraint is emitted as
    a separate ``ALTER TABLE`` statement after all tables are created.

    Args:
        entities: DSL entity specifications.

    Returns:
        A populated ``sqlalchemy.MetaData`` instance.
    """
    sa = _ensure_sa()
    metadata: sqlalchemy.MetaData = cast("sqlalchemy.MetaData", sa.MetaData())
    entity_names = {e.name for e in entities}
    circular_edges = _find_circular_refs(entities)

    if circular_edges:
        involved = {a for a, _ in circular_edges} | {b for _, b in circular_edges}
        logger.info(
            "Detected circular FK references between: %s — using deferred constraints",
            ", ".join(sorted(involved)),
        )

    for entity in entities:
        columns = []

        # Ensure an 'id' column exists
        has_id = any(f.name == "id" for f in entity.fields)
        if not has_id:
            columns.append(sa.Column("id", sa.Text(), primary_key=True))

        for field in entity.fields:
            columns.append(_field_to_column(field, entity.name, entity_names, circular_edges))

        sa.Table(entity.name, metadata, *columns)

    return metadata


def get_sorted_table_names(entities: list[EntitySpec]) -> list[str]:
    """Return entity/table names in topological (FK-dependency) order.

    Tables that are depended upon come first.

    Args:
        entities: DSL entity specifications.

    Returns:
        List of table names sorted so that referenced tables precede
        referencing tables.
    """
    metadata = build_metadata(entities)
    return [t.name for t in metadata.sorted_tables]


def get_circular_ref_edges(entities: list[EntitySpec]) -> set[tuple[str, str]]:
    """Return the set of (entity, ref_entity) edges involved in FK cycles.

    Used by the migration planner to emit deferred ALTER TABLE ADD CONSTRAINT
    statements for circular references.
    """
    return _find_circular_refs(entities)
