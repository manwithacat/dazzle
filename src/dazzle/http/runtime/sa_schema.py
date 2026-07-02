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

import functools
import logging
from typing import TYPE_CHECKING, Any, cast

from dazzle.db.virtual import is_virtual_entity
from dazzle.http.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType

if TYPE_CHECKING:
    import sqlalchemy

    from dazzle.core.ir import SurfaceSpec

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports — sqlalchemy is an optional dependency (postgres extra)
# ---------------------------------------------------------------------------


@functools.cache
def _ensure_sa() -> Any:
    """Import sqlalchemy on first use and return the module.

    `functools.cache` memoises the successful import (one-time, thread-safe) with no
    module-level `global` — a raised RuntimeError is *not* cached, so a later call
    retries the import once the optional `postgres` extra is installed.
    """
    try:
        import sqlalchemy
    except ImportError as exc:
        raise RuntimeError(
            "sqlalchemy is required for the SA schema bridge.  Install it with:  pip install dazzle"
        ) from exc
    return sqlalchemy


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
        # DECIMAL → exact NUMERIC (#1321); precision/scale applied in
        # _field_type_to_sa where they're available. FLOAT stays IEEE-754.
        ScalarType.DECIMAL: sa.Numeric(),
        ScalarType.FLOAT: sa.Float(),
        ScalarType.BOOL: sa.Boolean(),
        ScalarType.DATE: sa.Date(),
        ScalarType.DATETIME: sa.DateTime(timezone=True),
        ScalarType.UUID: sa.Uuid(),
        ScalarType.EMAIL: sa.Text(),
        ScalarType.URL: sa.Text(),
        ScalarType.SLUG: sa.Text(),
        ScalarType.JSON: sa.JSON(),
    }
    return mapping.get(scalar_type, sa.Text())


def _field_type_to_sa(field_type: FieldType) -> Any:
    """Convert a DSL FieldType to a SQLAlchemy column type instance."""
    sa = _ensure_sa()
    if field_type.kind == "scalar" and field_type.scalar_type:
        # decimal(p,s) → NUMERIC(p,s) for exact arithmetic (#1321). Precision is
        # optional → unconstrained NUMERIC; scale defaults to 0 in Postgres when
        # precision is given without scale, so only pass scale when declared.
        if field_type.scalar_type == ScalarType.DECIMAL and field_type.precision is not None:
            return sa.Numeric(field_type.precision, field_type.scale)
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


_INTERVAL_UNITS = {
    "minutes": "minutes",
    "hours": "hours",
    "days": "days",
    "weeks": "weeks",
    "months": "months",
    "years": "years",
}


def _server_default_sql(default: Any) -> str | None:
    """Render a field default as a PostgreSQL DDL DEFAULT expression.

    Replaces the old ``repr(default)`` emission (#1529), which produced
    Python syntax for anything non-string: dict date-exprs rendered as
    ``DEFAULT {'kind': 'now'}`` (invalid SQL — latent, since nothing in the
    live corpus carried a date-expr default through create_all), and the
    string form ``DEFAULT 'now'`` is PostgreSQL's classic frozen-at-parse-
    time trap. Date-exprs now become real volatile defaults, so the DB-side
    default matches the Python-side ``_create_date_factory`` semantics.

    Returns None for shapes with no sensible DDL form; the Python-side
    default application still covers those rows.
    """
    if isinstance(default, bool):
        return "true" if default else "false"
    if isinstance(default, int | float):
        return str(default)
    if isinstance(default, str):
        escaped = default.replace("'", "''")
        return f"'{escaped}'"
    if isinstance(default, dict) and "kind" in default:
        base = "now()" if default.get("kind") == "now" else "CURRENT_DATE"
        op = default.get("op")
        if not op:
            return base
        unit = _INTERVAL_UNITS.get(default.get("unit", "days"), "days")
        value = default.get("value", 0)
        return f"({base} {op} interval '{value} {unit}')"
    return None


def _column_kwargs(field: FieldSpec, sa: Any, *, suppress_unique: bool) -> dict[str, Any]:
    """Assemble the pk/nullable/unique/server_default kwargs for a Column."""
    kwargs: dict[str, Any] = {}
    if field.name == "id":
        kwargs["primary_key"] = True
    else:
        kwargs["nullable"] = not (
            getattr(field, "is_required", None) or getattr(field, "required", False)
        )
    if not suppress_unique and (
        getattr(field, "is_unique", False) or getattr(field, "unique", False)
    ):
        kwargs["unique"] = True
    if field.default is not None and (server_default := _server_default_sql(field.default)):
        kwargs["server_default"] = sa.text(server_default)
    return kwargs


def _field_to_column(
    field: FieldSpec,
    entity_name: str,
    entity_names: set[str],
    circular_edges: set[tuple[str, str]] | None = None,
    *,
    suppress_fk: bool = False,
    suppress_unique: bool = False,
) -> Any:
    """Convert a single FieldSpec into a SQLAlchemy ``Column``.

    ``suppress_fk`` / ``suppress_unique`` exist for the tenant-scoped path
    (RLS Phase A): when an intra-tenant ref becomes a table-level *composite*
    FK ``(tenant_id, fk) → parent(tenant_id, id)`` the column's own
    single-column FK must not also be emitted, and when an author-unique
    column is rewritten to a tenant-scoped ``UNIQUE(tenant_id, <col>)`` the
    column-level ``unique`` must be dropped. Both default False so the
    non-tenant path is byte-identical to before.
    """
    sa = _ensure_sa()
    col_type = _field_type_to_sa(field.type)
    kwargs = _column_kwargs(field, sa, suppress_unique=suppress_unique)

    # Foreign key for ref fields
    fk_args: list[Any] = []
    if not suppress_fk and field.type.kind == "ref" and field.type.ref_entity:
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
# Tenant-scoped construction rules (RLS Phase A)
# ---------------------------------------------------------------------------


def scoped_entity_names(entities: list[Any], partition_key: str) -> set[str]:
    """Entities carrying the tenant discriminator column (tenant-scoped).

    An entity is tenant-scoped iff it declares a field named ``partition_key``
    (covers both framework-injected and hand-declared discriminators). Takes
    a plain entity list (not an ``AppSpec``) so it is importable without an
    ``AppSpec`` type dependency — pass ``appspec.domain.entities``.
    """
    return {e.name for e in entities if any(f.name == partition_key for f in e.fields)}


def _tenant_composite_ref_fields(
    entity: EntitySpec,
    partition_key: str,
    tenant_scoped: set[str],
) -> list[FieldSpec]:
    """Ref fields on ``entity`` whose target is also tenant-scoped.

    These become table-level composite FKs ``(tenant_id, fk) →
    parent(tenant_id, id)`` (§4.1); the partition-key field itself is
    excluded (it FKs the tenant entity directly, single-column).
    """
    out: list[FieldSpec] = []
    for field in entity.fields:
        if field.name == partition_key:
            continue
        if (
            field.type.kind == "ref"
            and field.type.ref_entity
            and field.type.ref_entity in tenant_scoped
        ):
            out.append(field)
    return out


def _tenant_unique_fields(entity: EntitySpec, partition_key: str) -> list[FieldSpec]:
    """Author-declared unique columns to rewrite as ``UNIQUE(tenant_id, col)``.

    Skips ``id`` (already covered by ``UNIQUE(tenant_id, id)``) and the
    partition key itself.
    """
    out: list[FieldSpec] = []
    for field in entity.fields:
        if field.name in ("id", partition_key):
            continue
        if getattr(field, "is_unique", False) or getattr(field, "unique", False):
            out.append(field)
    return out


def _tenant_table_args(
    entity: EntitySpec,
    partition_key: str,
    tenant_scoped: set[str],
    circular_edges: set[tuple[str, str]] | None = None,
) -> list[Any]:
    """Extra table-level args for a tenant-scoped entity (§1.1, §4.1, §4.2, §5).

    Emits, in order: ``UNIQUE(tenant_id, id)``, one composite FK per
    intra-tenant ref, one ``UNIQUE(tenant_id, <col>)`` per author-unique
    column, and a standalone ``(tenant_id)`` index — ``UNIQUE(tenant_id, id)``
    already provides a covering index, so a ``(tenant_id, id)`` composite would
    be redundant.

    Composite FKs that close a cycle (self-ref or a cycle detected by
    :func:`_find_circular_refs`) are emitted with ``use_alter=True`` so the
    constraint lands as a deferred ``ALTER TABLE`` — exactly as the
    single-column path does for circular refs — keeping
    ``metadata.create_all`` orderable.
    """
    sa = _ensure_sa()
    args: list[Any] = [
        sa.UniqueConstraint(partition_key, "id", name=f"uq_{entity.name}_{partition_key}_id"),
    ]
    for field in _tenant_composite_ref_fields(entity, partition_key, tenant_scoped):
        target = field.type.ref_entity
        is_self_ref = target == entity.name
        is_circular = circular_edges is not None and (entity.name, target) in circular_edges
        needs_alter = is_self_ref or is_circular
        args.append(
            sa.ForeignKeyConstraint(
                [partition_key, field.name],
                [f"{target}.{partition_key}", f"{target}.id"],
                # Name includes the partition key so it matches the migration engine's
                # composite-FK name (schema_render._fk_name joins ALL constrained
                # columns) — so create_all and `db baseline` produce byte-identical
                # constraint names, not just identical structure (#1464). Mismatched
                # names would break an engine downgrade / drop against a create_all DB.
                name=f"fk_{entity.name}_{partition_key}_{field.name}",
                use_alter=needs_alter,
            )
        )
    for field in _tenant_unique_fields(entity, partition_key):
        args.append(
            sa.UniqueConstraint(
                partition_key,
                field.name,
                name=f"uq_{entity.name}_{partition_key}_{field.name}",
            )
        )
    # Standalone (tenant_id) index (§1.1). A (tenant_id, id) composite would
    # duplicate the implicit index from UNIQUE(tenant_id, id) above, so this
    # leads with — and contains only — the partition key.
    args.append(sa.Index(f"ix_{entity.name}_{partition_key}", partition_key))
    return args


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_metadata(
    entities: list[EntitySpec],
    surfaces: list[SurfaceSpec] | None = None,
    *,
    partition_key: str | None = None,
    tenant_scoped: set[str] | None = None,
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
    # Entity-aware (#1454): the governed ProcessRun (has started_by) IS real.
    db_entities = [e for e in entities if not is_virtual_entity(e)]

    entity_names = {e.name for e in db_entities}
    circular_edges = _find_circular_refs(db_entities)

    if circular_edges:
        involved = {a for a, _ in circular_edges} | {b for _, b in circular_edges}
        logger.info(
            "Detected circular FK references between: %s — using deferred constraints",
            ", ".join(sorted(involved)),
        )

    list_indexes = _list_index_specs(db_entities, surfaces)

    # RLS Phase A: the set of entity names carrying the discriminator. Empty
    # set (or partition_key=None) ⇒ every entity takes the byte-identical
    # non-tenant path below.
    scoped_names: set[str] = tenant_scoped or set()

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
            # Table-per-type children carry no tenant_id of their own — they share
            # the base row's id (id is PK+FK to the base) and inherit the base's
            # tenant_id + UNIQUE(tenant_id, id). So they correctly receive no
            # tenant-scoped constraints here. (Subtype-table RLS interaction is a
            # Phase-B concern.)
            continue

        # RLS Phase A: is this entity tenant-scoped? When so, intra-tenant ref
        # FKs become table-level composite FKs (column FK suppressed) and
        # author-unique columns become tenant-scoped UNIQUE (column unique
        # suppressed). Non-scoped entities keep the byte-identical path.
        is_tenant_scoped = bool(partition_key) and entity.name in scoped_names
        if is_tenant_scoped:
            assert partition_key is not None  # narrowed by is_tenant_scoped
            composite_ref_names = {
                f.name for f in _tenant_composite_ref_fields(entity, partition_key, scoped_names)
            }
            unique_field_names = {f.name for f in _tenant_unique_fields(entity, partition_key)}
        else:
            composite_ref_names = set()
            unique_field_names = set()

        columns = []

        # Ensure an 'id' column exists. Canonical implicit-PK type is UUID (#1432):
        # `ref`/FK columns are already `sa.Uuid()` (see _field_type_to_sa), the
        # #1431 snapshot engine and the committed example baselines already emit
        # `sa.Uuid()`, and entity ids are uuid4-generated at insert. Defaulting the
        # implicit id to Text here was the lone outlier — a latent PK/FK type
        # mismatch on the live-boot path.
        has_id = any(f.name == "id" for f in entity.fields)
        if not has_id:
            columns.append(sa.Column("id", sa.Uuid(), primary_key=True))

        for field in entity.fields:
            columns.append(
                _field_to_column(
                    field,
                    entity.name,
                    entity_names,
                    circular_edges,
                    suppress_fk=field.name in composite_ref_names,
                    suppress_unique=field.name in unique_field_names,
                )
            )

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

        # #1357: entity-level `unique a, b` / `index x` constraints from the
        # DSL. Previously dropped at the converter boundary, so they reached
        # neither create_all nor alembic autogenerate. Deterministic names
        # (`uq_<table>_<cols>` / `ix_<table>_<cols>`) keep autogenerate stable.
        constraint_args: list[Any] = []
        for constraint in getattr(entity, "constraints", []) or []:
            if not all(f in column_names for f in constraint.fields):
                # Same soft-skip policy as list indexes above: the validator
                # lints bad field refs; schema build shouldn't crash on them.
                continue
            cols = "_".join(constraint.fields)
            if constraint.kind.value == "unique":
                constraint_args.append(
                    sa.UniqueConstraint(*constraint.fields, name=f"uq_{entity.name}_{cols}")
                )
            else:  # index
                constraint_args.append(sa.Index(f"ix_{entity.name}_{cols}", *constraint.fields))

        tenant_args: list[Any] = []
        if is_tenant_scoped:
            assert partition_key is not None  # narrowed by is_tenant_scoped
            tenant_args = _tenant_table_args(entity, partition_key, scoped_names, circular_edges)
            # auth Plan 1d: the DB fills the injected tenant_id from the bound
            # session GUC on insert, so a scoped create needn't carry it (it's
            # excluded from the create input). The explicit cast is REQUIRED — PG
            # rejects a bare text default on a uuid column. An unset GUC →
            # current_setting(...) NULL → NOT NULL violation (fail-closed). The
            # NULLIF(.., '') wrapper (#1400) routes the pooled empty-string GUC
            # state to the same NOT NULL violation rather than a raising
            # ``''::uuid`` — same fence GUC, same pooled-revert vector.
            from sqlalchemy.dialects import postgresql

            pk_col = next((c for c in columns if c.name == partition_key), None)
            if pk_col is not None:
                pg_type = pk_col.type.compile(dialect=postgresql.dialect())  # type: ignore[no-untyped-call]
                if not pg_type:
                    raise ValueError(
                        f"cannot derive a cast for {entity.name}.{partition_key} "
                        "server_default (empty compiled type)"
                    )
                pk_col.server_default = sa.DefaultClause(
                    sa.text(f"NULLIF(current_setting('dazzle.tenant_id', true), '')::{pg_type}")
                )

        sa.Table(entity.name, metadata, *columns, *index_args, *constraint_args, *tenant_args)

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
