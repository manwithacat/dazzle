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

from dazzle.back.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType
from dazzle.db.virtual import VIRTUAL_ENTITY_NAMES as _VIRTUAL_ENTITY_NAMES

if TYPE_CHECKING:
    import sqlalchemy

    from dazzle.core.ir import SurfaceSpec

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports — sqlalchemy is an optional dependency (postgres extra)
# ---------------------------------------------------------------------------

_sa_imported = False
_sa: Any = None  # sqlalchemy module


def _ensure_sa() -> Any:
    """Import sqlalchemy on first use and return the module."""
    global _sa_imported, _sa  # noqa: PLW0603  # lazy import for optional sqlalchemy
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
        ScalarType.FLOAT: sa.Float(),
        ScalarType.BOOL: sa.Boolean(),
        ScalarType.DATE: sa.Date(),
        ScalarType.DATETIME: sa.DateTime(timezone=True),
        ScalarType.UUID: sa.Uuid(),
        ScalarType.EMAIL: sa.Text(),
        ScalarType.URL: sa.Text(),
        ScalarType.JSON: sa.JSON(),
    }
    return mapping.get(scalar_type, sa.Text())


def _field_type_to_sa(field_type: FieldType) -> Any:
    """Convert a DSL FieldType to a SQLAlchemy column type instance."""
    sa = _ensure_sa()
    if field_type.kind == "scalar" and field_type.scalar_type:
        return _scalar_type_to_sa(field_type.scalar_type)
    if field_type.kind == "ref":
        return sa.Uuid()
    # enum stored as TEXT
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
        kwargs["nullable"] = not (
            getattr(field, "is_required", None) or getattr(field, "required", False)
        )

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
# List-surface composite index emission (#1202)
# ---------------------------------------------------------------------------


def _extract_scope_column(predicate: Any) -> str | None:
    """Return the first-level scope column from a compiled scope predicate.

    Walks the predicate tree (top-level only — no recursion into nested
    booleans beyond the immediate AND/OR children) and returns the first
    field name encountered on a ``ColumnCheck`` or ``UserAttrCheck`` node.
    Returns ``None`` when the predicate is a logical constant
    (``Tautology`` / ``Contradiction``) or otherwise lacks a column anchor
    we can attach a composite index to.

    The check is structural rather than imported: predicates land here as
    ``ScopePredicate`` instances from :mod:`dazzle.core.ir.predicates` and
    each node type carries a discriminator ``kind`` literal we can pivot on
    without forcing the import (the back runtime stays decoupled from IR).
    """
    if predicate is None:
        return None
    kind = getattr(predicate, "kind", None)
    if kind in ("column_check", "user_attr_check"):
        field = getattr(predicate, "field", None)
        return field if isinstance(field, str) else None
    if kind == "bool_composite":
        # Walk immediate children — pick the first column anchor we find.
        # AND/OR composites where one branch carries the scope column are
        # the common shape (e.g. ``tenant_id = current_user.tenant and
        # status != archived``); the column-anchored branch is the lever.
        for child in getattr(predicate, "children", []) or []:
            anchor = _extract_scope_column(child)
            if anchor is not None:
                return anchor
    return None


def _list_index_specs(
    entities: list[EntitySpec],
    surfaces: list[SurfaceSpec] | None,
) -> dict[str, list[tuple[str, str, str]]]:
    """Compute composite (scope, default-sort) indexes per entity.

    Walks every ``list``-mode surface, pairs it with the entity referenced
    by ``surface.entity_ref``, extracts (a) the first-level scope column
    from the entity's compiled scope predicate, (b) the first ``SortSpec``
    field from ``surface.ux.sort``, and (c) a deterministic index name
    ``ix_list_<entity>_<scope>_<sort>``.

    Returns a mapping from entity name to a list of
    ``(index_name, scope_column, sort_column)`` tuples. De-duplicates by
    index name within the same entity. Silently skips:

    - Surfaces whose mode is not ``list``.
    - Surfaces missing ``entity_ref`` or pointing at an unknown entity.
    - Surfaces without a ``ux.sort`` declared.
    - Entities with no compiled scope predicate (or only logical constants).
    - Duplicate (scope, sort) pairs that would emit the same index name.
    """
    if not surfaces:
        return {}

    entity_by_name = {e.name: e for e in entities}
    by_entity: dict[str, list[tuple[str, str, str]]] = {}
    seen_names: dict[str, set[str]] = {}

    for surface in surfaces:
        # Mode check — SurfaceMode.LIST has value "list".
        mode_value = getattr(surface.mode, "value", surface.mode)
        if mode_value != "list":
            continue

        entity_name = surface.entity_ref
        if not entity_name:
            continue
        entity = entity_by_name.get(entity_name)
        if entity is None:
            continue

        ux = surface.ux
        if ux is None or not ux.sort:
            continue
        sort_col = ux.sort[0].field
        if not sort_col:
            continue

        access = entity.access
        if access is None or not access.scopes:
            continue

        scope_col: str | None = None
        for scope_rule in access.scopes:
            scope_col = _extract_scope_column(scope_rule.predicate)
            if scope_col is not None:
                break
        if scope_col is None:
            continue
        if scope_col == sort_col:
            # A composite over (X, X) is degenerate — skip rather than
            # emit a single-column index that the benchmark already
            # demonstrated does not move the numbers.
            continue

        index_name = f"ix_list_{entity_name}_{scope_col}_{sort_col}"
        names = seen_names.setdefault(entity_name, set())
        if index_name in names:
            continue
        names.add(index_name)
        by_entity.setdefault(entity_name, []).append((index_name, scope_col, sort_col))

    return by_entity


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_metadata(
    entities: list[EntitySpec],
    surfaces: list[SurfaceSpec] | None = None,
) -> sqlalchemy.MetaData:
    """Convert a list of EntitySpec into a SQLAlchemy ``MetaData``.

    Each entity becomes a ``Table`` with columns derived from its fields.
    Foreign-key relationships are expressed via ``ForeignKey`` so that
    ``metadata.sorted_tables`` returns tables in dependency order and
    ``metadata.create_all()`` emits DDL in the correct order.

    Circular FK references (e.g. Department ↔ User) are detected and
    marked with ``use_alter=True`` so that the constraint is emitted as
    a separate ``ALTER TABLE`` statement after all tables are created.

    Virtual entities (backed by Redis/in-memory) are excluded — they have
    no PostgreSQL table.

    When ``surfaces`` is provided, the schema builder also emits one
    composite ``(scope-column, default-sort-column)`` b-tree index per
    ``list``-mode surface that declares a ``ux.sort`` (#1202). The
    indexes are attached to the ``sa.Table`` via ``sa.Index`` so Alembic
    autogenerate picks them up. Passing ``surfaces=None`` (the default)
    preserves the prior behaviour — no list indexes are emitted.

    Args:
        entities: DSL entity specifications.
        surfaces: Optional list of surface specifications. When provided,
            composite list-path indexes are attached to the relevant
            tables. Pass ``appspec.surfaces`` from the calling site.

    Returns:
        A populated ``sqlalchemy.MetaData`` instance.
    """
    sa = _ensure_sa()
    metadata: sqlalchemy.MetaData = cast("sqlalchemy.MetaData", sa.MetaData())

    # Filter out virtual entities — no PostgreSQL table for these.
    db_entities = [e for e in entities if e.name not in _VIRTUAL_ENTITY_NAMES]

    entity_names = {e.name for e in db_entities}
    circular_edges = _find_circular_refs(db_entities)

    if circular_edges:
        involved = {a for a, _ in circular_edges} | {b for _, b in circular_edges}
        logger.info(
            "Detected circular FK references between: %s — using deferred constraints",
            ", ".join(sorted(involved)),
        )

    list_indexes = _list_index_specs(db_entities, surfaces)

    for entity in db_entities:
        # #1217 Phase 3(e): table-per-type child. Only emit subtype-specific
        # columns; the shared identifier comes from the base's id via a FK,
        # so the child's `id` is BOTH primary key AND foreign key with
        # ON DELETE CASCADE. Base-owned fields (including the synthesised
        # `kind`) stay on the base table.
        if entity.subtype_of is not None:
            base_name = entity.subtype_of
            base_entity = next((e for e in db_entities if e.name == base_name), None)
            if base_entity is None:
                # Defensive — linker should have rejected this, but skip
                # rather than crash if it slips through (e.g. virtual base).
                continue
            base_id_field = next(f for f in base_entity.fields if f.name == "id")
            base_id_type = _field_type_to_sa(base_id_field.type)
            tpt_columns: list[Any] = [
                sa.Column(
                    "id",
                    base_id_type,
                    sa.ForeignKey(f"{base_name}.id", ondelete="CASCADE"),
                    primary_key=True,
                ),
            ]
            base_field_names = {f.name for f in base_entity.fields}
            for field in entity.fields:
                if field.name == "id" or field.name in base_field_names:
                    continue
                tpt_columns.append(
                    _field_to_column(field, entity.name, entity_names, circular_edges)
                )
            sa.Table(entity.name, metadata, *tpt_columns)
            continue

        columns = []

        # Ensure an 'id' column exists
        has_id = any(f.name == "id" for f in entity.fields)
        if not has_id:
            columns.append(sa.Column("id", sa.Text(), primary_key=True))

        for field in entity.fields:
            columns.append(_field_to_column(field, entity.name, entity_names, circular_edges))

        # Build composite list-path indexes that target this entity. Index
        # objects bound to a Table flow into the table's `.indexes` set
        # automatically so Alembic autogenerate emits them as `CREATE
        # INDEX` statements (#1202).
        index_args: list[Any] = []
        column_names = {c.name for c in columns}
        for index_name, scope_col, sort_col in list_indexes.get(entity.name, []):
            if scope_col not in column_names or sort_col not in column_names:
                # Skip silently when the columns referenced by the surface
                # do not exist on the entity (e.g. computed fields, or a
                # surface authored ahead of the schema). The validator
                # already lints these — we don't want to crash schema
                # build over a soft inconsistency.
                continue
            index_args.append(sa.Index(index_name, scope_col, sort_col))

        sa.Table(entity.name, metadata, *columns, *index_args)

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
