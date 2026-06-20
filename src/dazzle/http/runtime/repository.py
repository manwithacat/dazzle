"""
Repository — provides persistence layer for Dazzle backend runtime.

This module implements the repository pattern for PostgreSQL database access.
Provides CRUD operations with advanced filtering, sorting, pagination,
and relation loading.
"""

from __future__ import annotations

import json
import re
import time
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel

from dazzle.http.runtime.query_builder import quote_identifier
from dazzle.http.specs.entity import (
    ComputedFieldSpec,
    EntitySpec,
    FieldType,
    ScalarType,
)

# Build a tuple of IntegrityError types for PostgreSQL.
_INTEGRITY_ERRORS: tuple[type[Exception], ...] = ()
try:
    from psycopg import errors as _psycopg_errors

    _INTEGRITY_ERRORS = (_psycopg_errors.IntegrityError,)
except ImportError:
    pass

# =============================================================================
# Constraint Violation Error
# =============================================================================


class ConstraintViolationError(Exception):
    """Raised when a database constraint (unique, FK) is violated."""

    def __init__(
        self,
        message: str,
        field: str | None = None,
        constraint_type: str = "integrity",
    ):
        self.field = field
        self.constraint_type = constraint_type  # "unique" | "foreign_key"
        super().__init__(message)


def _resolve_latest_one_fields(
    rows: list[dict[str, Any]],
    entity_spec: Any,
    db: Any,
    *,
    as_of: Any = None,
) -> list[dict[str, Any]]:
    """Resolve every ``latest_one`` field on the entity (#1223 Phase 3a.v.ii).

    For each LATEST_ONE field on ``entity_spec``:
      1. Look up the target entity's table + temporal.end_field
      2. Batch-query the target where ``via_field IN (...source_ids)``
         AND ``end_field IS NULL`` (or the open-interval as_of predicate)
      3. Attach the resolved row (or None) under the field name on each
         input row

    Returns the input rows (mutated in place, also returned for chaining).
    No-op when ``entity_spec`` has no LATEST_ONE fields or rows is empty.

    Performance: one batched query per latest_one field. For a list page of
    N rows with K latest_one fields, K extra queries. Acceptable since
    cohort_strip-class workloads already do per-region fan-out at similar
    granularity.
    """
    from dazzle.core.ir import FieldTypeKind
    from dazzle.http.runtime.query_builder import quote_identifier

    if not rows or entity_spec is None:
        return rows

    latest_one_fields = [
        f
        for f in getattr(entity_spec, "fields", [])
        if getattr(f.type, "kind", None) == FieldTypeKind.LATEST_ONE
    ]
    if not latest_one_fields:
        return rows

    placeholder = db.placeholder

    for f in latest_one_fields:
        target_entity = f.type.ref_entity
        via_field = f.type.via_field
        if not target_entity or not via_field:
            continue

        # The target entity needs `temporal:` (validator enforces this);
        # at runtime we still defensively look it up via the field's
        # ref_entity. The target's own EntitySpec carries the temporal.
        # We don't have access to the full registry here, so we rely on
        # convention: end_field is named conventionally (end_date /
        # effective_to). For MVP, look up via_field's target_entity
        # spec from the global appspec is overkill — instead we hard-
        # code knowledge: the latest_one validator already ensured the
        # target has `temporal:`, so we encode the end_field discovery
        # by querying the row where via_field matches AND ORDER BY
        # start_date DESC LIMIT 1 in absence of richer context. Simpler:
        # rely on the target entity exposing temporal.end_field via the
        # registry once we plumb it through. For 3a.v.ii MVP we use
        # ORDER BY id DESC fallback if we can't access temporal.end_field.
        #
        # TODO: thread the appspec through Repository so we can look up
        # the target's temporal.end_field exactly. For now, prefer the
        # conventional `end_date` / `effective_to` field-name fallback.
        end_field_candidates = ("end_date", "effective_to")
        end_field = end_field_candidates[0]

        source_ids = [str(row["id"]) for row in rows if row.get("id")]
        if not source_ids:
            for row in rows:
                row[f.name] = None
            continue

        in_placeholders = ", ".join(placeholder for _ in source_ids)
        target_table = quote_identifier(target_entity)
        via_q = quote_identifier(via_field)

        # Build the active-row predicate. If as_of is set, the row must
        # have been active on as_of; otherwise NULL end_field.
        if as_of is not None:
            # Try both candidate end-fields with COALESCE-style fallback —
            # simplest: query with WHERE via IN AND (end_date IS NULL OR
            # end_date > as_of) AND start_date <= as_of. If the target
            # uses effective_to/effective_from instead, the first attempt
            # raises (column not found) and we'll fall back.
            sql = (
                f"SELECT * FROM {target_table} "
                f"WHERE {via_q} IN ({in_placeholders}) "
                f'AND ("{end_field}" IS NULL OR "{end_field}" > {placeholder}) '
                f'AND "start_date" <= {placeholder}'
            )
            params: list[Any] = list(source_ids) + [as_of, as_of]
        else:
            sql = (
                f"SELECT * FROM {target_table} "
                f"WHERE {via_q} IN ({in_placeholders}) "
                f'AND "{end_field}" IS NULL'
            )
            params = list(source_ids)

        target_rows: list[dict[str, Any]] = []
        with db.connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(sql, params)  # nosemgrep
                fetched = cursor.fetchall()
                target_rows = [dict(r) if hasattr(r, "keys") else dict(r) for r in fetched]
            except Exception:
                # Likely a column-name mismatch (target uses effective_to,
                # not end_date). Try the alternate. Belt-and-suspenders
                # until the appspec-plumbing TODO above lands.
                end_field = end_field_candidates[1]
                if as_of is not None:
                    sql = (
                        f"SELECT * FROM {target_table} "
                        f"WHERE {via_q} IN ({in_placeholders}) "
                        f'AND ("{end_field}" IS NULL OR "{end_field}" > {placeholder}) '
                        f'AND "effective_from" <= {placeholder}'
                    )
                    params = list(source_ids) + [as_of, as_of]
                else:
                    sql = (
                        f"SELECT * FROM {target_table} "
                        f"WHERE {via_q} IN ({in_placeholders}) "
                        f'AND "{end_field}" IS NULL'
                    )
                    params = list(source_ids)
                cursor.execute(sql, params)  # nosemgrep
                fetched = cursor.fetchall()
                target_rows = [dict(r) if hasattr(r, "keys") else dict(r) for r in fetched]

        by_source = {str(r.get(via_field)): r for r in target_rows}
        for row in rows:
            row[f.name] = by_source.get(str(row.get("id")))

    return rows


def _resolve_recursive_traversal_fields(
    rows: list[dict[str, Any]],
    entity_spec: Any,
    db: Any,
    host_table: str,
) -> list[dict[str, Any]]:
    """Resolve every ``descendants_of`` / ``ancestors_of`` field on the
    entity (#1227 Phase 3b.ii).

    For each traversal field, runs a recursive CTE:

    Self-ref descendants:
        WITH RECURSIVE walk(id, root) AS (
          SELECT id, <via> FROM <host> WHERE <via> IN (...source_ids)
          UNION ALL
          SELECT t.id, w.root FROM <host> t JOIN walk w ON t.<via> = w.id
        )
        SELECT root, id FROM walk

    Junction-mediated descendants (e.g. ``via ManagerLink.manager``):
        WITH RECURSIVE walk(id, root) AS (
          SELECT m.<other_fk>, m.<via> FROM <junction> m WHERE m.<via> IN (...)
          UNION ALL
          SELECT m.<other_fk>, w.root FROM <junction> m JOIN walk w ON m.<via> = w.id
        )

    Ancestors mirror the same shape walking up via the parent FK.

    After the walk yields ``(root, id)`` pairs, a second batched
    ``SELECT * FROM <host> WHERE id IN (...)`` fetches the resolved
    rows. Each input row receives a list under the field name (empty
    list when no descendants/ancestors).

    No-op when entity has no such fields or ``rows`` is empty.
    """
    from dazzle.core.ir import FieldTypeKind

    if not rows or entity_spec is None:
        return rows

    traversal_fields = [
        f
        for f in getattr(entity_spec, "fields", [])
        if getattr(f.type, "kind", None)
        in (FieldTypeKind.DESCENDANTS_OF, FieldTypeKind.ANCESTORS_OF)
    ]
    if not traversal_fields:
        return rows

    placeholder = db.placeholder
    source_ids = [str(row["id"]) for row in rows if row.get("id")]
    if not source_ids:
        for row in rows:
            for f in traversal_fields:
                row[f.name] = []
        return rows

    host_q = quote_identifier(host_table)

    for f in traversal_fields:
        is_descendants = f.type.kind == FieldTypeKind.DESCENDANTS_OF
        via_field = f.type.via_field
        via_entity = f.type.via_entity
        if not via_field:
            for row in rows:
                row[f.name] = []
            continue

        via_q = quote_identifier(via_field)
        in_placeholders = ", ".join(placeholder for _ in source_ids)

        if via_entity is None:
            # Self-ref: walk through the host table itself.
            if is_descendants:
                cte = (
                    f"WITH RECURSIVE walk(id, root) AS ( "
                    f"SELECT id, {via_q} FROM {host_q} "
                    f"WHERE {via_q} IN ({in_placeholders}) "
                    f"UNION ALL "
                    f"SELECT t.id, w.root FROM {host_q} t "
                    f"JOIN walk w ON t.{via_q} = w.id "
                    f") SELECT root, id FROM walk"
                )
            else:
                # Ancestors: from each source, walk up via the FK.
                cte = (
                    f"WITH RECURSIVE walk(id, root) AS ( "
                    f"SELECT {via_q}, id FROM {host_q} "
                    f"WHERE id IN ({in_placeholders}) AND {via_q} IS NOT NULL "
                    f"UNION ALL "
                    f"SELECT t.{via_q}, w.root FROM {host_q} t "
                    f"JOIN walk w ON t.id = w.id AND t.{via_q} IS NOT NULL "
                    f") SELECT root, id FROM walk"
                )
            params = list(source_ids)
        else:
            # Junction-mediated: the validator already ensured the junction
            # exists, has the parent FK named after the dot, and has at
            # least one other `ref Host` field. We need that *other* field's
            # name to know what the "child" id is on each link row. Without
            # the appspec threaded here, we discover it by querying the
            # junction's columns at execution time — but the cleaner shape
            # is to look it up via the entity_spec registry. For MVP we
            # accept a small N+1 quirk: assume the junction has exactly two
            # `ref Host` fields and call the non-via one "child". We probe
            # by selecting all column names from the junction and picking
            # the first FK-looking column that isn't via_field.
            child_fk = _discover_junction_child_fk(db, via_entity, via_field)
            if child_fk is None:
                for row in rows:
                    row[f.name] = []
                continue
            junction_q = quote_identifier(via_entity)
            child_q = quote_identifier(child_fk)
            if is_descendants:
                cte = (
                    f"WITH RECURSIVE walk(id, root) AS ( "
                    f"SELECT m.{child_q}, m.{via_q} FROM {junction_q} m "
                    f"WHERE m.{via_q} IN ({in_placeholders}) "
                    f"UNION ALL "
                    f"SELECT m.{child_q}, w.root FROM {junction_q} m "
                    f"JOIN walk w ON m.{via_q} = w.id "
                    f") SELECT root, id FROM walk"
                )
            else:
                cte = (
                    f"WITH RECURSIVE walk(id, root) AS ( "
                    f"SELECT m.{via_q}, m.{child_q} FROM {junction_q} m "
                    f"WHERE m.{child_q} IN ({in_placeholders}) "
                    f"UNION ALL "
                    f"SELECT m.{via_q}, w.root FROM {junction_q} m "
                    f"JOIN walk w ON m.{child_q} = w.id "
                    f") SELECT root, id FROM walk"
                )
            params = list(source_ids)

        pairs: list[tuple[str, str]] = []
        with db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(cte, params)  # nosemgrep
            fetched = cursor.fetchall()
            pairs = [(str(r["root"]), str(r["id"])) for r in fetched]

        if not pairs:
            for row in rows:
                row[f.name] = []
            continue

        unique_ids = list({pid for _, pid in pairs})
        unique_ph = ", ".join(placeholder for _ in unique_ids)
        fetch_sql = f"SELECT * FROM {host_q} WHERE id IN ({unique_ph})"
        fetched_rows: dict[str, dict[str, Any]] = {}
        with db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(fetch_sql, unique_ids)  # nosemgrep
            for r in cursor.fetchall():
                fetched_rows[str(r["id"])] = dict(r)

        by_root: dict[str, list[dict[str, Any]]] = {sid: [] for sid in source_ids}
        for root, pid in pairs:
            fetched = fetched_rows.get(pid)
            if fetched is not None:
                by_root.setdefault(root, []).append(fetched)

        for input_row in rows:
            input_row[f.name] = by_root.get(str(input_row.get("id")), [])

    return rows


def _discover_junction_child_fk(db: Any, junction_table: str, via_field: str) -> str | None:
    """Look up the junction's non-via FK column name.

    Probes the database catalog (information_schema.columns) for the
    junction's columns and returns the first that looks like a FK
    (UUID-typed, not the via_field, not `id`).

    Returns ``None`` if no candidate column is found — the caller
    handles by attaching empty traversal results.
    """
    sql = (
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = %s ORDER BY ordinal_position"
    )
    import logging

    logger = logging.getLogger(__name__)
    try:
        with db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, [junction_table])
            cols = [str(r["column_name"]) for r in cursor.fetchall()]
    except Exception:
        logger.debug(
            "junction child-FK probe failed for %s; traversal attaches empty list",
            junction_table,
            exc_info=True,
        )
        return None
    for col in cols:
        if col == via_field or col == "id":
            continue
        # Convention: any non-id column on a junction whose name doesn't
        # match the parent via_field is a candidate child FK. Validator
        # has already enforced at compile time that such a column exists
        # and is a `ref Host` — we trust that here.
        return col
    return None


def _build_temporal_as_of_predicate(
    start_field: str, end_field: str, as_of: Any
) -> tuple[str, list[Any]]:
    """Build the as-of-date temporal predicate for #1223 Phase 3a.iv.

    Re-projects a temporal entity's read paths to "what was true as of
    `as_of`" by replacing the default `end_field IS NULL` active-only
    filter with the open-interval test:

        start_field <= as_of AND (end_field IS NULL OR end_field > as_of)

    Returns ``(sql, params)`` ready to plug into QueryBuilder's
    ``__scope_predicate`` slot (or AND-compose with an existing one).
    """
    from dazzle.http.runtime.query_builder import quote_identifier

    s = quote_identifier(start_field)
    e = quote_identifier(end_field)
    sql = f"{s} <= %s AND ({e} IS NULL OR {e} > %s)"
    return sql, [as_of, as_of]


def _parse_constraint_error(exc: str | Exception, table_name: str) -> tuple[str, str | None]:
    """Parse a constraint error message to extract type and field.

    Accepts either a string or an exception object. For psycopg exceptions,
    uses ``pgerror`` and ``diag.detail`` to extract field-level information
    that may not appear in ``str(exc)``.

    Returns:
        (constraint_type, field_name_or_none)
    """
    # Extract the fullest error text available
    if isinstance(exc, str):
        err = exc
        detail = ""
    else:
        err = getattr(exc, "pgerror", None) or str(exc)
        detail = getattr(getattr(exc, "diag", None), "detail", None) or ""

    # Combine err + detail for matching
    full_text = f"{err} {detail}".strip()

    # PostgreSQL: "duplicate key value violates unique constraint"
    if "duplicate key" in full_text and "unique constraint" in full_text:
        # Try to extract column from detail: Key (slug)=(value)
        detail_match = re.search(r"Key \((\w+)\)", full_text)
        pg_field: str | None = detail_match.group(1) if detail_match else None
        return "unique", pg_field

    # PostgreSQL: "violates foreign key constraint"
    if "foreign key constraint" in full_text:
        # Extract field from DETAIL: Key (assigned_to)=(uuid) is not present in table "User"
        fk_match = re.search(r"Key \((\w+)\)", full_text)
        fk_field: str | None = fk_match.group(1) if fk_match else None
        return "foreign_key", fk_field

    return "integrity", None


def _translate_integrity_error(exc: Exception, table_name: str) -> ConstraintViolationError:
    """Translate a backend integrity error into the framework-canonical
    :class:`ConstraintViolationError` shape.

    Used by ``Repository.create`` / ``Repository.update`` and the bespoke
    ``create_subtype`` / ``update_subtype`` paths so all four sites raise
    identical-shape errors. #1239 extracted this to dedupe four ~19-line
    copies that had drifted out of slice 3e.iii.
    """
    ctype, field = _parse_constraint_error(exc, table_name)
    if ctype == "unique":
        msg = (
            f"A {table_name} with this {field} already exists"
            if field
            else f"Duplicate value violates unique constraint on {table_name}"
        )
    elif ctype == "foreign_key":
        msg = (
            f"Referenced record not found for field '{field}' on {table_name}"
            if field
            else f"Referenced record does not exist for {table_name}"
        )
    else:
        msg = f"Integrity constraint violated on {table_name}: {exc}"
    return ConstraintViolationError(msg, field=field, constraint_type=ctype)


# Alias to prevent mypy resolving `list` as Repository.list inside the class
_list = list


def _safe_text_field_names(entity_spec: Any, search_spec: Any) -> _list[str]:
    """Return the searchable text field names from *search_spec* that
    actually exist on *entity_spec* and are text-shaped.

    Used by :meth:`Repository.fts_search` to build `ts_headline` snippet
    columns. Filters defensively so a hostile spec can't smuggle in
    arbitrary identifiers; only fields validated against the entity
    schema make it into the SQL.
    """
    text_field_names: set[str] = set()
    for field in getattr(entity_spec, "fields", None) or []:
        kind = getattr(getattr(field, "type", None), "kind", None)
        # Match the cycle-2 search-schema generator's allow-list.
        if kind in {"str", "text", "email", "url"}:
            text_field_names.add(getattr(field, "name", ""))
    out: _list[str] = []
    seen: set[str] = set()
    for sf in getattr(search_spec, "fields", None) or []:
        path = getattr(sf, "path", "") or ""
        if "." in path:  # FK paths skipped (cycle 2 already does this)
            continue
        if path not in text_field_names or path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out


if TYPE_CHECKING:
    from collections.abc import Sequence

    from dazzle.http.metrics.system_collector import SystemMetricsCollector
    from dazzle.http.runtime.relation_loader import RelationLoader


# =============================================================================
# Type Variables
# =============================================================================


# =============================================================================
# Database Value Conversion (PostgreSQL)
# =============================================================================


def _db_to_python(value: Any, field_type: FieldType | None = None) -> Any:
    """Convert database value to Python type based on field type.

    PostgreSQL with dict_row returns most types correctly, but JSON fields
    come back as strings and UUIDs/dates may need conversion depending on
    column type.
    """
    if value is None:
        return None
    if field_type is None:
        return value

    if field_type.kind == "scalar" and field_type.scalar_type:
        scalar = field_type.scalar_type
        if scalar == ScalarType.UUID:
            return UUID(value) if value and not isinstance(value, UUID) else value
        elif scalar == ScalarType.DATETIME:
            if isinstance(value, datetime):
                return value
            return datetime.fromisoformat(value) if value else None
        elif scalar == ScalarType.DATE:
            if isinstance(value, date):
                return value
            return date.fromisoformat(value) if value else None
        elif scalar == ScalarType.DECIMAL:
            return Decimal(str(value)) if value is not None else None
        elif scalar == ScalarType.BOOL:
            return bool(value)
        elif scalar == ScalarType.JSON:
            if isinstance(value, (dict, list)):
                return value
            return json.loads(value) if value else None
        else:
            return value
    elif field_type.kind == "ref":
        return UUID(value) if value and not isinstance(value, UUID) else value
    else:
        return value


# =============================================================================
# Repository
# =============================================================================


class Repository[T: BaseModel]:
    """
    Repository for a single entity type.

    Provides CRUD operations against PostgreSQL database.
    Supports advanced filtering, sorting, and relation loading.
    Optionally collects query metrics for observability.
    """

    def __init__(
        self,
        db_manager: Any,
        entity_spec: EntitySpec,
        model_class: type[T],
        relation_loader: RelationLoader | None = None,
        metrics_collector: SystemMetricsCollector | None = None,
        base_entity_spec: EntitySpec | None = None,
    ):
        """
        Initialize the repository.

        Args:
            db_manager: Database backend instance (PostgresBackend)
            entity_spec: Entity specification
            model_class: Pydantic model class for the entity
            relation_loader: Optional relation loader for nested data fetching
            metrics_collector: Optional system metrics collector for query timing
            base_entity_spec: For polymorphic-child entities (``subtype_of: <base>``),
                the back-layer EntitySpec for the base entity. Repository.list
                uses this to inject a JOIN that pulls shared base columns into
                child queries (#1217 slice 3e.iv).
        """
        self.db = db_manager
        self.entity_spec = entity_spec
        self.model_class = model_class
        self.table_name = entity_spec.name
        self._relation_loader = relation_loader
        self._metrics = metrics_collector

        # Build field type lookup for conversions
        self._field_types: dict[str, FieldType] = {f.name: f.type for f in entity_spec.fields}
        # Required columns — used by create() to detect server-filled fields the
        # caller omitted (e.g. the Plan 1d partition key) that must be RETURNING'd.
        self._required_fields: frozenset[str] = frozenset(
            f.name for f in entity_spec.fields if f.required
        )

        # Store computed field specs for evaluation
        self._computed_fields: list[ComputedFieldSpec] = entity_spec.computed_fields or []

        # #1217 Phase 3e.iv: cache the subtype JOIN+columns at construction
        # time. Child entities have ONLY their subtype-specific fields in
        # `entity_spec.fields`; shared base fields live in `base_entity_spec`.
        # Field types for the base columns also need to land in
        # `_field_types` so `_row_to_model` can coerce them on the way out.
        self._subtype_join_sql: str | None = None
        self._subtype_extra_cols: list[str] = []
        if entity_spec.subtype_of is not None and base_entity_spec is not None:
            base_table = quote_identifier(base_entity_spec.name)
            child_table = quote_identifier(self.table_name)
            self._subtype_join_sql = f'JOIN {base_table} ON {child_table}."id" = {base_table}."id"'
            # Pull every base column EXCEPT id (already in the child table).
            for f in base_entity_spec.fields:
                if f.name == "id":
                    continue
                col_q = quote_identifier(f.name)
                self._subtype_extra_cols.append(f"{base_table}.{col_q} AS {col_q}")
                # Make base field types visible to _row_to_model — without
                # this the JOINed columns are returned as raw DB values
                # rather than coerced Python types.
                self._field_types.setdefault(f.name, f.type)

    def _record_query(self, query_type: str, latency_ms: float, rows: int = 0) -> None:
        """Record a database query metric."""
        if self._metrics:
            self._metrics.record_db_query(
                query_type=query_type,
                table=self.table_name,
                latency_ms=latency_ms,
                rows_affected=rows,
            )

    def _python_to_db(self, value: Any, field_type: FieldType | None = None) -> Any:
        """Convert a Python value for PostgreSQL storage."""
        from dazzle.http.runtime.pg_backend import _python_to_postgres

        return _python_to_postgres(value, field_type)

    def _model_to_row(self, model: T) -> dict[str, Any]:
        """Convert Pydantic model to row dict for the database."""
        data = model.model_dump()
        return {k: self._python_to_db(v, self._field_types.get(k)) for k, v in data.items()}

    def _row_to_model(self, row: Any) -> T:
        """Convert database row to Pydantic model."""
        data = dict(row)
        converted = {k: _db_to_python(v, self._field_types.get(k)) for k, v in data.items()}
        return self.model_class(**converted)

    def _read_on_conn(self, conn: Any, id: UUID) -> T | dict[str, Any] | None:
        """Read a row by id on a caller-provided connection (#1319, ADR-0032 Slice B).

        Used by ``update(conn=...)`` so the post-write read happens in the caller's
        still-open transaction (seeing its own uncommitted write). The runtime
        connection uses a dict row factory, so ``_row_to_model`` converts it.
        """
        ph = self.db.placeholder
        table = quote_identifier(self.table_name)
        cursor = conn.cursor()
        cursor.execute(f'SELECT * FROM {table} WHERE "id" = {ph}', [str(id)])  # nosemgrep
        row = cursor.fetchone()
        return self._row_to_model(row) if row is not None else None

    async def create(self, data: dict[str, Any]) -> T:
        """
        Create a new entity.

        Args:
            data: Entity data (including id)

        Returns:
            Created entity
        """
        # Convert values for database backend
        db_data = {k: self._python_to_db(v, self._field_types.get(k)) for k, v in data.items()}

        columns = ", ".join(quote_identifier(k) for k in db_data.keys())
        ph = self.db.placeholder
        placeholders = ", ".join(ph for _ in db_data)
        values = list(db_data.values())

        table = quote_identifier(self.table_name)
        # auth Plan 1d: a REQUIRED column the caller omitted must be server-filled
        # by a DB default or the INSERT would NOT-NULL-fail — the framework
        # partition key (excluded from create input, filled from the bound session
        # via `current_setting('dazzle.tenant_id')`) is the case that matters.
        # RETURNING those keeps the response model complete with the server value.
        # Gating on `required` keeps non-scoped creates byte-identical: a plain
        # entity's required fields are all present in db_data (client- or
        # auto_add-supplied), so `omitted` is empty and no RETURNING is appended.
        omitted = [c for c in self._required_fields if c not in db_data]
        returning = ""
        if omitted:
            returning = " RETURNING " + ", ".join(quote_identifier(c) for c in omitted)
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders}){returning}"

        start = time.perf_counter()
        try:
            with self.db.connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, values)  # nosemgrep
                if omitted:
                    returned = cursor.fetchone()
                    if returned is not None:
                        row = dict(returned)  # dict_row connection (cf. read())
                        data = {
                            **data,
                            **{
                                c: _db_to_python(row[c], self._field_types.get(c))
                                for c in omitted
                                if c in row
                            },
                        }
        except _INTEGRITY_ERRORS as exc:
            raise _translate_integrity_error(exc, self.table_name) from exc
        latency_ms = (time.perf_counter() - start) * 1000
        self._record_query("insert", latency_ms, rows=1)

        # auth Plan 1d: a server-filled required column (the partition key) that
        # we expected to RETURNING but didn't get back must NOT be masked by the
        # model_construct fallback — that would yield a row with a missing/None
        # tenant_id that looks valid. Fail loud instead.
        missing_server_filled = [c for c in omitted if c not in data]
        if missing_server_filled:
            raise RuntimeError(
                f"{self.table_name}: server-filled required column(s) "
                f"{missing_server_filled} were not returned by INSERT … RETURNING; "
                "refusing to construct an incomplete row"
            )

        try:
            return self.model_class(**data)
        except Exception:
            # Seed/test fixtures may omit optional fields that Pydantic requires;
            # the DB insert succeeded, so return with model_construct (no validation).
            return self.model_class.model_construct(**data)

    async def read(
        self,
        id: UUID,
        include: list[str] | None = None,
        *,
        as_of: Any = None,
    ) -> T | dict[str, Any] | None:
        """
        Read an entity by ID.

        Args:
            id: Entity ID
            include: List of relation names to include (nested loading)
            as_of: Optional date for temporal entity time-travel (#1223 Phase 3a.iv).
                When set on an entity with `temporal:` declared, the row must have
                been *active* on this date (start_field <= as_of AND (end_field IS
                NULL OR end_field > as_of)). NULL on non-temporal entities is a no-op.

        Returns:
            Entity (or dict with nested data if include specified), or None if not found
        """
        table = quote_identifier(self.table_name)
        ph = self.db.placeholder
        # #1218 Option A: tombstone filter on the single-row read path.
        # The list path threads through QueryBuilder; read() builds raw
        # SQL, so the filter is appended here directly. Soft-deleted
        # rows are returned as None — same shape as "id not found".
        soft_delete_clause = ' AND "deleted_at" IS NULL' if self.entity_spec.soft_delete else ""
        # #1223 Phase 3a.ii / 3a.iv: tombstone or as-of predicate for
        # temporal entities. read() is unique in not having a `filters`
        # dict, so as_of for the read path is supplied via a separate
        # kwarg threaded from the route handler.
        _temporal_read = self.entity_spec.temporal
        temporal_clause = ""
        extra_params: list[Any] = []
        if _temporal_read is not None and _temporal_read.default_filter == "active":
            if as_of is not None:
                t_sql, t_params = _build_temporal_as_of_predicate(
                    _temporal_read.start_field, _temporal_read.end_field, as_of
                )
                temporal_clause = f" AND ({t_sql})"
                extra_params = list(t_params)
            else:
                temporal_clause = f' AND "{_temporal_read.end_field}" IS NULL'
        # #1217 Phase 3e follow-up: parity with list() — polymorphic-child
        # entities must JOIN to the base table on the shared id so that the
        # detail-row dict carries every base column (most importantly `kind`,
        # which the subtype_panel renderer reads to dispatch). The list path
        # injects the same JOIN+extra cols via QueryBuilder at line ~1015;
        # read() builds raw SQL so we splice them in directly here.
        #
        # WHY the soft_delete/temporal clauses can't conflict with the JOIN:
        # the linker rejects soft_delete on polymorphic children (rule
        # E_SUBTYPE_SOFT_DELETE_ON_CHILD) and temporal on children, so when
        # _subtype_join_sql is set both clauses are guaranteed empty by
        # construction. The assert below makes that contract explicit.
        if self._subtype_join_sql is not None:
            assert not soft_delete_clause and not temporal_clause, (
                "polymorphic-child entity unexpectedly carries "
                "soft_delete/temporal clauses; linker rules E_SUBTYPE_* "
                "should have rejected this upstream"
            )
            extra_cols_sql = (
                ", " + ", ".join(self._subtype_extra_cols) if self._subtype_extra_cols else ""
            )
            sql = (
                f"SELECT {table}.*{extra_cols_sql} "
                f"FROM {table} {self._subtype_join_sql} "
                f'WHERE {table}."id" = {ph}'
            )
        else:
            sql = f'SELECT * FROM {table} WHERE "id" = {ph}{soft_delete_clause}{temporal_clause}'
        params: tuple[Any, ...] = (str(id), *extra_params)

        start = time.perf_counter()
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)  # nosemgrep
            row = cursor.fetchone()
        latency_ms = (time.perf_counter() - start) * 1000
        self._record_query("select", latency_ms, rows=1 if row else 0)

        if not row:
            return None

        # #1223 Phase 3a.v.ii: resolve latest_one fields if any exist on
        # the entity. Forces dict-return (same coercion as `include`).
        # No-op when entity has no latest_one fields.
        from dazzle.core.ir import FieldTypeKind

        _has_latest_one = any(
            getattr(f.type, "kind", None) == FieldTypeKind.LATEST_ONE
            for f in self.entity_spec.fields
        )
        # #1227 Phase 3b.ii: descendants_of / ancestors_of resolution.
        _has_traversal = any(
            getattr(f.type, "kind", None)
            in (FieldTypeKind.DESCENDANTS_OF, FieldTypeKind.ANCESTORS_OF)
            for f in self.entity_spec.fields
        )

        # If relations requested, load them and return dict
        if include and self._relation_loader:
            row_dict = dict(row)
            # #1331: relation loading runs SELECTs on a *pooled* connection
            # scoped to this operation. The pool rolls back on return, so the
            # connection never parks idle-in-transaction holding ACCESS SHARE
            # (the old shared get_persistent_connection() did → blocked DDL).
            with self.db.connection() as rel_conn:
                row_dicts = self._relation_loader.load_relations(
                    self.entity_spec.name,
                    [row_dict],
                    include,
                    conn=rel_conn,
                )
            if _has_latest_one:
                row_dicts = _resolve_latest_one_fields(
                    row_dicts, self.entity_spec, self.db, as_of=as_of
                )
            if _has_traversal:
                row_dicts = _resolve_recursive_traversal_fields(
                    row_dicts, self.entity_spec, self.db, self.table_name
                )
            return self._convert_row_dict(row_dicts[0])

        # If computed fields, latest_one, traversal, OR subtype JOIN, return
        # a dict so the merged shape (base + child columns) survives. The
        # generated child model only declares child-specific fields, so a
        # plain `_row_to_model` call would silently drop base columns (Pydantic
        # default ignores extras) — losing `kind` and breaking the
        # subtype_panel renderer at v0.71.186.
        if (
            self._computed_fields
            or _has_latest_one
            or _has_traversal
            or self._subtype_join_sql is not None
        ):
            row_dicts_l = [dict(row)]
            if _has_latest_one:
                row_dicts_l = _resolve_latest_one_fields(
                    row_dicts_l, self.entity_spec, self.db, as_of=as_of
                )
            if _has_traversal:
                row_dicts_l = _resolve_recursive_traversal_fields(
                    row_dicts_l, self.entity_spec, self.db, self.table_name
                )
            return self._convert_row_dict(row_dicts_l[0])

        return self._row_to_model(row)

    async def update(
        self, id: UUID, data: dict[str, Any], *, conn: Any | None = None
    ) -> T | dict[str, Any] | None:
        """
        Update an existing entity.

        Args:
            id: Entity ID
            data: Fields to update (only non-None values)
            conn: when provided (#1319, ADR-0032 Slice B), run the UPDATE on this
                caller-owned connection (NOT a fresh one) and read the row back on
                the SAME connection — so the write joins the caller's transaction
                (the caller commits/rolls back). The post-update read then sees the
                still-uncommitted write. When ``None`` (the default for every
                existing caller), behaviour is unchanged: open + commit own conn.

        Returns:
            Updated entity or None if not found
        """
        # Filter out None values
        update_data = {k: v for k, v in data.items() if v is not None}

        if not update_data:
            return await self.read(id)

        # #1289 follow-up: if this entity has `tenant_host:` and its slug
        # column is in the update payload, capture the pre-update value so
        # we can bust the tenant cache for both old + new slugs after the
        # UPDATE commits. Skipped entirely on non-tenant-host entities so
        # the hot path stays a single SQL round-trip.
        from dazzle.tenant.cache_registry import slug_field_for

        slug_field = slug_field_for(self.table_name)
        old_slug: str | None = None
        if slug_field is not None and slug_field in update_data:
            pre = await self.read(id)
            if pre is not None:
                raw = (
                    pre.get(slug_field) if isinstance(pre, dict) else getattr(pre, slug_field, None)
                )
                old_slug = str(raw) if raw is not None else None

        # Convert values for database backend
        db_data = {
            k: self._python_to_db(v, self._field_types.get(k)) for k, v in update_data.items()
        }

        ph = self.db.placeholder
        set_clause = ", ".join(f"{quote_identifier(k)} = {ph}" for k in db_data.keys())
        values = list(db_data.values())
        values.append(str(id))

        table = quote_identifier(self.table_name)
        sql = f'UPDATE {table} SET {set_clause} WHERE "id" = {ph}'

        start = time.perf_counter()
        try:
            if conn is not None:
                # #1319 Slice B — join the caller's transaction; the caller commits.
                cursor = conn.cursor()
                cursor.execute(sql, values)  # nosemgrep
                rowcount = cursor.rowcount
            else:
                with self.db.connection() as own_conn:
                    cursor = own_conn.cursor()
                    cursor.execute(sql, values)  # nosemgrep
                    rowcount = cursor.rowcount
        except _INTEGRITY_ERRORS as exc:
            raise _translate_integrity_error(exc, self.table_name) from exc
        latency_ms = (time.perf_counter() - start) * 1000
        self._record_query("update", latency_ms, rows=rowcount)

        if rowcount == 0:
            return None

        if conn is not None:
            # Read back on the SAME (uncommitted) connection so the response
            # reflects the write the caller's transaction is about to commit.
            result = self._read_on_conn(conn, id)
        else:
            result = await self.read(id)

        # Slug cache busting fires only on the own-connection path: the write is
        # committed by the time we bust. On the shared-tx (conn) path the caller
        # owns the commit boundary; tenant_host + invoke-transition is not a v1
        # combination (busting a not-yet-committed slug would be premature).
        if conn is None and slug_field is not None and slug_field in update_data:
            new_slug = str(update_data[slug_field])
            if old_slug != new_slug:
                from dazzle.tenant.cache_registry import bust

                if old_slug:
                    bust(old_slug)
                if new_slug:
                    bust(new_slug)

        return result

    async def delete(self, id: UUID) -> bool:
        """
        Delete an entity by ID.

        Args:
            id: Entity ID

        Returns:
            True if deleted, False if not found
        """
        table = quote_identifier(self.table_name)
        ph = self.db.placeholder
        sql = f'DELETE FROM {table} WHERE "id" = {ph}'

        start = time.perf_counter()
        try:
            with self.db.connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, (str(id),))  # nosemgrep
                rowcount = cursor.rowcount
        except Exception as exc:
            # Catch FK constraint violations and re-raise as a clear error
            # so the route handler can return 409 instead of 500.
            exc_str = str(exc)
            if "ForeignKeyViolation" in type(exc).__name__ or "foreign key" in exc_str.lower():
                raise ValueError(
                    f"Cannot delete {self.table_name}: referenced by other records"
                ) from exc
            raise
        latency_ms = (time.perf_counter() - start) * 1000
        self._record_query("delete", latency_ms, rows=rowcount)

        return bool(rowcount and rowcount > 0)

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        filters: dict[str, Any] | None = None,
        sort: str | list[str] | None = None,
        include: list[str] | None = None,
        search: str | None = None,
        select_fields: list[str] | None = None,
        search_fields: list[str] | None = None,
        fk_display_only: bool = False,
    ) -> dict[str, Any]:
        """
        List entities with pagination, filtering, sorting, and relation loading.

        Args:
            page: Page number (1-indexed)
            page_size: Items per page
            filters: Optional filter criteria (supports advanced operators)
                    Examples:
                    - {"status": "active"} - equality
                    - {"priority__gte": 5} - greater than or equal
                    - {"title__contains": "urgent"} - substring match
                    - {"status__in": ["active", "pending"]} - in list
            sort: Sort field(s), prefix with - for descending
                  Examples: "created_at", "-priority", ["priority", "-created_at"]
            include: List of relation names to include (nested loading)
            search: Full-text search query
            search_fields: Fields to search across (from surface config)

        Returns:
            Dictionary with items, total, page, and page_size
        """
        # #1004 — virtual entities (SystemHealth, SystemMetric,
        # ProcessRun, LogEntry, EventTrace) have no DB table. The
        # linker correctly skips migrations for them, but the route
        # generator still mounts a list endpoint that calls this
        # method, which then 500s on `SELECT COUNT(*) FROM "<entity>"`
        # against a non-existent relation. Short-circuit with an
        # empty result; a future cycle can wire a runtime-state
        # provider per virtual entity.
        from dazzle.db.virtual import VIRTUAL_ENTITY_NAMES as _VIRTUAL
        from dazzle.http.runtime.query_builder import QueryBuilder

        if self.entity_spec is not None and self.entity_spec.name in _VIRTUAL:
            return {
                "items": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
            }

        # Build query using QueryBuilder
        builder = QueryBuilder(table_name=self.table_name, placeholder_style=self.db.placeholder)
        if select_fields:
            builder.select_fields = list(select_fields)
        builder.set_pagination(page, page_size)

        # #1218 Option A: tombstone filter for soft-delete entities.
        # Composes via QueryBuilder so the predicate AND-merges with
        # any user/scope filters already in `filters`. Authors opt
        # into the filter via the `soft_delete` directive on the entity.
        # `include_deleted` query-param + RBAC gate is a follow-up.
        effective_filters: dict[str, Any] = dict(filters) if filters else {}
        if self.entity_spec.soft_delete:
            effective_filters.setdefault("deleted_at__isnull", True)

        # #1223 Phase 3a.ii / 3a.iv: tombstone filter + as_of reprojection.
        # Default behaviour (no as_of): inject `<end_field> IS NULL` so list
        # paths return only currently-active rows. With as_of (3a.iv): replace
        # the active-only filter with the historical-snapshot predicate
        # `start_field <= as_of AND (end_field IS NULL OR end_field > as_of)`.
        # The as_of value is passed via the special `__as_of` filter dict key,
        # mirroring the `__scope_predicate` pattern. Route handlers inject it
        # from the workspace/surface `?as_of=YYYY-MM-DD` URL parameter.
        _temporal = self.entity_spec.temporal
        _as_of = effective_filters.pop("__as_of", None)
        if _temporal is not None and _temporal.default_filter == "active":
            if _as_of is not None:
                _temporal_predicate = _build_temporal_as_of_predicate(
                    _temporal.start_field, _temporal.end_field, _as_of
                )
                # AND-compose with any existing scope predicate.
                existing = effective_filters.get("__scope_predicate")
                if existing is not None:
                    s_sql, s_params = existing
                    effective_filters["__scope_predicate"] = (
                        f"({s_sql}) AND ({_temporal_predicate[0]})",
                        list(s_params) + list(_temporal_predicate[1]),
                    )
                else:
                    effective_filters["__scope_predicate"] = _temporal_predicate
            else:
                effective_filters.setdefault(f"{_temporal.end_field}__isnull", True)

        if effective_filters:
            builder.add_filters(effective_filters)

        if sort:
            builder.add_sorts(sort)

        if search:
            builder.set_search(search, fields=search_fields)

        # #1217 Phase 3e.iv: subtype auto-JOIN. Child entities only carry
        # their own subtype-specific fields in `entity_spec.fields`; the
        # shared columns (e.g. acquired_at, location, kind) live on the
        # base table. Inject the JOIN + extra SELECT cols cached at
        # __init__ time so every list query against a child surface
        # returns the merged row shape.
        if self._subtype_join_sql is not None:
            builder.joins.append(self._subtype_join_sql)
            builder.extra_select_cols.extend(self._subtype_extra_cols)

        # v0.61.9 (#865): FK-display fast path — LEFT JOIN the display field
        # instead of issuing one SELECT per FK relation. Only to-one relations
        # with a registered display_field qualify; the rest fall back to the
        # existing batched _load_to_one path.
        display_join_fallback: list[str] = []
        if fk_display_only and include and self._relation_loader:
            joins, extra_cols, display_join_fallback = (
                self._relation_loader.build_display_join_plan(self.entity_spec.name, include)
            )
            if joins:
                builder.joins.extend(joins)
                builder.extra_select_cols.extend(extra_cols)

        # Get total count
        count_sql, count_params = builder.build_count()

        start = time.perf_counter()
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(count_sql, count_params)
            row = cursor.fetchone()
            total = row[0] if isinstance(row, (tuple, list)) else next(iter(row.values()))
        latency_ms = (time.perf_counter() - start) * 1000
        self._record_query("count", latency_ms)

        # Get paginated items
        items_sql, items_params = builder.build_select()

        start = time.perf_counter()
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(items_sql, items_params)
            rows = cursor.fetchall()
        latency_ms = (time.perf_counter() - start) * 1000
        self._record_query("select", latency_ms, rows=len(rows))

        # Convert to dicts first for relation loading
        row_dicts = [dict(row) for row in rows]

        # Load relations if requested
        if include and self._relation_loader:
            if fk_display_only:
                # Fold the `{rel}__display` JOIN columns into FK dicts so
                # downstream consumers see the same shape as the batched
                # path would have produced (#865).
                row_dicts = self._relation_loader.apply_display_joins_to_rows(
                    row_dicts, self.entity_spec.name, include
                )
                # Load any relations that couldn't use the JOIN path
                # (no display_field, or to-many) via the batched fallback.
                # #1331: pooled connection scoped to this op (see find_by_id).
                if display_join_fallback:
                    with self.db.connection() as rel_conn:
                        row_dicts = self._relation_loader.load_relations(
                            self.entity_spec.name,
                            row_dicts,
                            display_join_fallback,
                            conn=rel_conn,
                        )
            else:
                # #1331: pooled connection scoped to this op (see find_by_id).
                with self.db.connection() as rel_conn:
                    row_dicts = self._relation_loader.load_relations(
                        self.entity_spec.name,
                        row_dicts,
                        include,
                        conn=rel_conn,
                    )

        # #1223 Phase 3a.v.ii: resolve latest_one fields if any exist.
        # Forces dict-return (same coercion as `include` / computed).
        from dazzle.core.ir import FieldTypeKind

        _has_latest_one = any(
            getattr(f.type, "kind", None) == FieldTypeKind.LATEST_ONE
            for f in self.entity_spec.fields
        )
        if _has_latest_one:
            # `_as_of` was popped from effective_filters in the temporal
            # block above (line ~738) before being passed to QueryBuilder.
            # Reuse the same value here so latest_one resolution honours
            # the as-of date for consistent time-travel.
            row_dicts = _resolve_latest_one_fields(
                row_dicts, self.entity_spec, self.db, as_of=_as_of
            )

        # #1227 Phase 3b.ii: descendants_of / ancestors_of resolution.
        _has_traversal = any(
            getattr(f.type, "kind", None)
            in (FieldTypeKind.DESCENDANTS_OF, FieldTypeKind.ANCESTORS_OF)
            for f in self.entity_spec.fields
        )
        if _has_traversal:
            row_dicts = _resolve_recursive_traversal_fields(
                row_dicts, self.entity_spec, self.db, self.table_name
            )

        # Convert to models (or return dicts if relations/computed fields included)
        items: list[Any]
        if (
            include
            or self._computed_fields
            or _has_latest_one
            or _has_traversal
            or self._subtype_join_sql is not None
            or select_fields
        ):
            # Return dicts with nested data and/or computed/derived fields.
            # #1237: subtype JOINs append base columns that the child Pydantic
            # model would silently drop via `extra='ignore'`, so route through
            # the dict path (mirrors the read() fix shipped in v0.72.0).
            # #1304: a `select_fields` projection returns a SUBSET of columns,
            # which can never satisfy the full entity model's validators —
            # `_row_to_model` would raise (missing required fields, or an
            # out-of-enum value on a column the projection didn't even ask
            # for, since `_row_to_model` validates the whole row). A projection
            # is "give me these columns as data", so return raw dicts. Existing
            # `select_fields` callers all also pass `include`, so they already
            # took this branch — this only newly affects projection-without-
            # include (the context_selector options query, which must be robust
            # to rows that don't conform to the current entity enum).
            items = [self._convert_row_dict(row) for row in row_dicts]
        else:
            items = [self._row_to_model(row) for row in rows]

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def aggregate(
        self,
        *,
        dimensions: _list[Any],
        measures: dict[str, str],
        filters: dict[str, Any] | None = None,
        limit: int = 200,
        measure_expressions: dict[str, tuple[str, _list[Any]]] | None = None,
    ) -> _list[Any]:
        """Run a single multi-dimension GROUP BY aggregation against this entity.

        Closes the bug class (#847–#851) where bar_chart enumeration and
        per-bucket counts diverged: one SQL query, one scope evaluation,
        no N+1 round-trips. The bucket list, labels, and counts all come
        from the same row set.

        v2 (cycle 25): supports multi-dimension ``GROUP BY`` for cross-tab
        / pivot rendering. Each dimension is a
        :class:`dazzle.http.runtime.aggregate.Dimension` — scalar dims
        bucket by column value; FK dims auto-LEFT JOIN the target and
        pull a display field for the bar/cell label.

        Args:
            dimensions: Ordered list of :class:`Dimension`. The order
                drives both SQL ``GROUP BY`` ordering and result-row
                shape (bucket dicts carry one entry per dimension).
            measures: Mapping of metric name → measure spec. ``"count"``
                is always supported; ``"sum:<col>"`` / ``"avg:<col>"`` /
                ``"min:<col>"`` / ``"max:<col>"`` work for numeric
                columns. Unsupported measures are silently dropped.
            filters: Same shape as ``Repository.list``'s ``filters`` —
                including the special ``__scope_predicate`` key that
                ``_resolve_scope_filters`` emits. Threaded through
                ``QueryBuilder.add_filters`` so the scope predicate
                applies pre-GROUP BY.
            limit: Cap the number of buckets returned. Default 200.

        Returns:
            List of :class:`AggregateBucket` records with ``dimensions``
            (one entry per declared dim, plus ``<name>_label`` for FK
            dims) and ``measures`` (the computed values). Empty list on
            no matches or unsupported measures.
        """
        from dazzle.http.runtime.aggregate import build_aggregate_sql, rows_to_buckets
        from dazzle.perf.tracer import dazzle_span

        with dazzle_span(
            "repo.aggregate",
            entity=self.table_name,
            dimension_count=len(dimensions),
            measure_count=len(measures),
        ):
            # #1218 Option A: tombstone filter on the aggregate path.
            # Same composition contract as `list` — merges with the
            # incoming `filters` dict so QueryBuilder ANDs the
            # tombstone predicate with any scope/user filters.
            effective_filters: dict[str, Any] = dict(filters) if filters else {}
            if self.entity_spec.soft_delete:
                effective_filters.setdefault("deleted_at__isnull", True)

            # #1223 Phase 3a.ii / 3a.iv: tombstone or as-of for temporal.
            # Same shape as the list path. The __as_of key flows through
            # the same filters dict used by list/scope composition.
            _temporal_agg = self.entity_spec.temporal
            _as_of_agg = effective_filters.pop("__as_of", None)
            if _temporal_agg is not None and _temporal_agg.default_filter == "active":
                if _as_of_agg is not None:
                    _t_pred = _build_temporal_as_of_predicate(
                        _temporal_agg.start_field, _temporal_agg.end_field, _as_of_agg
                    )
                    existing_agg = effective_filters.get("__scope_predicate")
                    if existing_agg is not None:
                        s_sql, s_params = existing_agg
                        effective_filters["__scope_predicate"] = (
                            f"({s_sql}) AND ({_t_pred[0]})",
                            list(s_params) + list(_t_pred[1]),
                        )
                    else:
                        effective_filters["__scope_predicate"] = _t_pred
                else:
                    effective_filters.setdefault(f"{_temporal_agg.end_field}__isnull", True)

            sql, params = build_aggregate_sql(
                table_name=self.table_name,
                placeholder_style=self.db.placeholder,
                dimensions=dimensions,
                measures=measures,
                filters=effective_filters or None,
                limit=limit,
                measure_expressions=measure_expressions,
            )
            if not sql:
                return []

            start = time.perf_counter()
            with self.db.connection() as conn:
                cursor = conn.cursor()
                # build_aggregate_sql composes identifiers via quote_identifier
                # and only ever passes user values as bound parameters — same
                # safety contract as Repository.list. Semgrep can't trace that.
                cursor.execute(
                    sql, params
                )  # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query
                rows = cursor.fetchall()
            latency_ms = (time.perf_counter() - start) * 1000
            self._record_query("aggregate", latency_ms, rows=len(rows))

            return rows_to_buckets(
                [dict(r) if hasattr(r, "keys") else r for r in rows],
                dimensions=dimensions,
                measures=measures,
                measure_expressions=measure_expressions,
            )

    def explain_aggregate(
        self,
        *,
        dimensions: _list[Any],
        measures: dict[str, str],
        filters: dict[str, Any] | None = None,
        limit: int = 200,
    ) -> tuple[str, _list[Any]]:
        """Return the ``(sql, params)`` ``aggregate(...)`` would execute.

        Debug-velocity tool. When a chart renders wrong values or no
        buckets, the answer to "why?" should be "here's the exact SQL
        the framework runs" — not "read the source". Pair with
        ``dazzle db explain-aggregate`` on the CLI for operators, or
        call directly from tests / notebooks to inspect compilation.

        No side effects: does not hit the database. Uses the same
        :func:`dazzle.http.runtime.aggregate.build_aggregate_sql` the
        live path uses, so what this returns is byte-for-byte what
        :meth:`aggregate` would ``cursor.execute``.

        Args are identical to :meth:`aggregate` — kept in sync so any
        agg call can be copy-pasted into explain without edits.

        Returns ``("", [])`` when no supported measures are present
        (same short-circuit ``aggregate`` applies).
        """
        from dazzle.http.runtime.aggregate import build_aggregate_sql

        return build_aggregate_sql(
            table_name=self.table_name,
            placeholder_style=self.db.placeholder,
            dimensions=dimensions,
            measures=measures,
            filters=filters,
            limit=limit,
        )

    def _convert_row_dict(
        self,
        row: dict[str, Any],
        related_data: dict[str, _list[dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        """Convert a row dict with proper type conversions and computed fields."""
        result: dict[str, Any] = {}
        collected_relations: dict[str, _list[dict[str, Any]]] = {}

        for k, v in row.items():
            if isinstance(v, dict):
                # Nested relation - convert recursively
                result[k] = self._convert_row_dict(v) if v else None
            elif isinstance(v, list):
                # To-many relation
                result[k] = [self._convert_row_dict(item) for item in v]
                # Store for computed field evaluation
                collected_relations[k] = [
                    dict(item) if isinstance(item, dict) else item for item in v
                ]
            else:
                # Regular field
                result[k] = _db_to_python(v, self._field_types.get(k))

        # Add computed fields
        if self._computed_fields:
            from dazzle.http.runtime.computed_evaluator import (
                evaluate_computed_fields,
            )

            # Use collected relations or provided related_data
            rel_data = related_data if related_data is not None else collected_relations
            computed_values = evaluate_computed_fields(result, self._computed_fields, rel_data)
            result.update(computed_values)

        return result

    async def fts_search(
        self,
        spec: Any,  # SearchSpec — typed Any to avoid IR import cycle
        q: str,
        *,
        page: int = 1,
        page_size: int = 20,
        scope_predicate: tuple[str, Sequence[Any]] | None = None,
    ) -> dict[str, Any]:
        """Run a tsvector-backed full-text search (#954 cycle 3).

        Queries against the cycle-2 ``search_vector`` GENERATED column —
        fast, indexed, locale-aware. ``websearch_to_tsquery`` accepts
        the user-friendly query syntax (``"phrase"``, ``-exclude``,
        ``OR``) so adopters don't need to teach users about
        ``& | !`` operators.

        Args:
            spec: SearchSpec for *self*'s entity. Tokenizer drives the
                FTS configuration.
            q: User search string. Empty strings short-circuit to
                ``{items: [], total: 0}``.
            page: 1-indexed page number.
            page_size: Per-page result count.
            scope_predicate: ``(sql, params)`` tuple from the predicate
                compiler. ANDed into the WHERE clause so RBAC stays
                correct on the FTS endpoint without re-implementing
                the scope path. ``None`` means no scope filter
                (unauthenticated public search).

        Returns:
            ``{"items": [{"id", "rank", **row}, ...], "total": N,
              "page": P, "page_size": PS}``. ``items`` is ordered by
            ``ts_rank`` descending.
        """
        if not q or not q.strip():
            return {"items": [], "total": 0, "page": page, "page_size": page_size}

        # Tokenizer comes from the spec; cycle 2 already validated it
        # against the Postgres allow-list. Defence-in-depth: also
        # require ASCII-alpha here so a hostile spec can't inject
        # SQL via the literal-interpolated config name.
        config = (getattr(spec, "tokenizer", None) or "english").strip().lower()
        if not config.isalpha() or not config.isascii():
            config = "english"

        table = quote_identifier(self.table_name)
        offset = max(0, (page - 1) * page_size)

        ph = self.db.placeholder  # %s for psycopg
        # WHERE search_vector @@ websearch_to_tsquery(:cfg, :q)
        where_parts: list[str] = [
            f"search_vector @@ websearch_to_tsquery('{config}', {ph})",
        ]
        params: list[Any] = [q]
        if scope_predicate is not None:
            scope_sql, scope_params = scope_predicate
            if scope_sql:
                where_parts.append(f"({scope_sql})")
                params.extend(scope_params)
        where_clause = " AND ".join(where_parts)

        # Count first so pagination metadata is correct.
        # SQL is parameterised — `q` and scope params bind via cursor params;
        # only safe identifiers (validated `config`, quoted `table`, hardcoded
        # placeholder) are interpolated into the string.
        count_sql = f"SELECT COUNT(*) FROM {table} WHERE {where_clause}"
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(count_sql, params)  # nosemgrep
            row = cursor.fetchone()
            total = row[0] if isinstance(row, (tuple, list)) else next(iter(row.values()))

        if total == 0:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}

        # #954 cycle 4 — `ts_headline` snippet columns when the spec
        # opts in via `highlight: true`. Each searchable text field
        # gets a `<field>__snippet` column wrapping matched terms in
        # `<mark>` tags. Templates render the snippet directly when
        # present, falling back to the raw field otherwise.
        highlight = bool(getattr(spec, "highlight", False))
        snippet_sql = ""
        snippet_params: list[Any] = []
        snippet_field_names: list[str] = []
        if highlight:
            snippet_field_names = _safe_text_field_names(self.entity_spec, spec)
            snippet_parts: list[str] = []
            for name in snippet_field_names:
                col = quote_identifier(name)
                alias = quote_identifier(f"{name}__snippet")
                snippet_parts.append(
                    f"ts_headline('{config}', coalesce({col}, ''), "
                    f"websearch_to_tsquery('{config}', {ph}), "
                    f"'StartSel=<mark>, StopSel=</mark>, "
                    f"MaxWords=35, MinWords=15') AS {alias}"
                )
                snippet_params.append(q)
            if snippet_parts:
                snippet_sql = ", " + ", ".join(snippet_parts)

        # Items: rank + full row + optional snippets. Param order
        # matters: ts_rank's q, [snippet qs...], the WHERE clause's q,
        # then any scope params, then page_size/offset.
        items_sql = (
            f"SELECT *, "
            f"ts_rank_cd(search_vector, websearch_to_tsquery('{config}', {ph})) "
            f"AS rank{snippet_sql} "
            f"FROM {table} WHERE {where_clause} "
            f"ORDER BY rank DESC LIMIT {ph} OFFSET {ph}"
        )
        items_params = [q, *snippet_params, *params, page_size, offset]

        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(items_sql, items_params)  # nosemgrep
            rows = cursor.fetchall()

        items = [dict(r) if not isinstance(r, dict) else r for r in rows]
        result: dict[str, Any] = {
            "items": items,
            "total": int(total),
            "page": page,
            "page_size": page_size,
        }
        if snippet_field_names:
            # Surface the snippet field list so consumers (templates,
            # API clients) know which `<field>__snippet` columns to
            # look at without inspecting every row.
            result["snippet_fields"] = snippet_field_names
        return result

    async def exists(self, id: UUID) -> bool:
        """Check if an entity exists."""
        table = quote_identifier(self.table_name)
        ph = self.db.placeholder
        sql = f'SELECT 1 FROM {table} WHERE "id" = {ph} LIMIT 1'  # nosemgrep

        start = time.perf_counter()
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (str(id),))  # nosemgrep
            result = cursor.fetchone()
        latency_ms = (time.perf_counter() - start) * 1000
        self._record_query("select", latency_ms, rows=1 if result else 0)

        return result is not None


try:
    from dazzle.http.runtime.pg_backend import PostgresBackend

    type DatabaseManager = PostgresBackend
except ImportError:
    PostgresBackend = None  # type: ignore[assignment,misc]
    type DatabaseManager = Any  # type: ignore[no-redef]
"""Deprecated — use :class:`~dazzle.http.runtime.pg_backend.PostgresBackend`."""


# =============================================================================
# Repository Factory
# =============================================================================


class RepositoryFactory:
    """
    Factory for creating repositories from entity specifications.
    """

    def __init__(
        self,
        db_manager: Any,
        models: dict[str, type[BaseModel]],
        relation_loader: RelationLoader | None = None,
        metrics_collector: SystemMetricsCollector | None = None,
    ):
        """
        Initialize the factory.

        Args:
            db_manager: Database backend (PostgresBackend)
            models: Dictionary mapping entity names to Pydantic models
            relation_loader: Optional relation loader for nested data fetching
            metrics_collector: Optional system metrics collector for query timing
        """
        self.db = db_manager
        self.models = models
        self._relation_loader = relation_loader
        self._metrics = metrics_collector
        self._repositories: dict[str, Repository[Any]] = {}

    def create_repository(
        self,
        entity: EntitySpec,
        base_entity_spec: EntitySpec | None = None,
    ) -> Repository[Any]:
        """
        Create a repository for an entity.

        Args:
            entity: Entity specification
            base_entity_spec: For polymorphic-child entities, the base
                entity spec used for subtype JOIN injection (#1217 3e.iv).

        Returns:
            Repository instance
        """
        model = self.models.get(entity.name)
        if not model:
            raise ValueError(f"No model found for entity: {entity.name}")

        repo: Repository[Any] = Repository(
            db_manager=self.db,
            entity_spec=entity,
            model_class=model,
            relation_loader=self._relation_loader,
            metrics_collector=self._metrics,
            base_entity_spec=base_entity_spec,
        )
        self._repositories[entity.name] = repo
        return repo

    def create_all_repositories(self, entities: list[EntitySpec]) -> dict[str, Repository[Any]]:
        """
        Create repositories for all entities.

        Args:
            entities: List of entity specifications

        Returns:
            Dictionary mapping entity names to repositories
        """
        # Build name → EntitySpec lookup so polymorphic children can be
        # constructed with their base spec for subtype JOIN injection.
        by_name = {e.name: e for e in entities}
        for entity in entities:
            base = by_name.get(entity.subtype_of) if entity.subtype_of else None
            self.create_repository(entity, base_entity_spec=base)
        return self._repositories

    def get_repository(self, entity_name: str) -> Repository[Any] | None:
        """Get a repository by entity name."""
        return self._repositories.get(entity_name)


# =============================================================================
# Subtype Operations (#1217 Phase 3e.iii)
# =============================================================================
#
# Polymorphic subtype rows live across two TPT tables sharing the same uuid
# PK: a base row (with discriminator `kind`) and a child row. Both writes
# must succeed together; the `with db.connection() as conn:` context
# commits on clean exit and rolls back on exception, so two `cursor.execute`
# calls inside one block are a single transaction. The base table's
# BEFORE INSERT/UPDATE trigger (build_child_kind_trigger) enforces
# kind/child-table consistency at the DB layer — we still emit `kind`
# explicitly so the trigger sees a non-null discriminator on the base row.
#
# `delete_subtype` is intentionally absent: the FK on the child table
# carries ON DELETE CASCADE (sa_schema.py — Task 12), so the existing
# Repository.delete() against the base table cascades automatically.


def _split_payload_by_owner(
    payload: dict[str, Any],
    base_spec: EntitySpec,
    child_spec: EntitySpec,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Partition a flat payload into base-owned + child-owned column buckets.

    Fields named on both sides (e.g. the shared `id`) are treated as
    base-owned for input purposes; the caller is responsible for stamping
    `id` on both buckets at INSERT time.
    """
    base_names = {f.name for f in base_spec.fields}
    child_names = {f.name for f in child_spec.fields}
    base_payload = {k: v for k, v in payload.items() if k in base_names}
    # Child-only — don't double-route `id` if it's in both.
    child_payload = {k: v for k, v in payload.items() if k in child_names and k not in base_names}
    return base_payload, child_payload


def _convert_payload_for_db(payload: dict[str, Any], spec: EntitySpec) -> dict[str, Any]:
    """Run each value through _python_to_postgres for its declared type."""
    from dazzle.http.runtime.pg_backend import _python_to_postgres

    field_types = {f.name: f.type for f in spec.fields}
    return {k: _python_to_postgres(v, field_types.get(k)) for k, v in payload.items()}


def create_subtype(
    *,
    db_manager: Any,
    base_spec: EntitySpec,
    child_spec: EntitySpec,
    payload: dict[str, Any],
) -> UUID:
    """Atomic INSERT of base + child rows sharing one uuid PK.

    The discriminator (`kind`) is auto-populated from the child entity name
    in snake_case; the caller MUST NOT supply it. The new uuid is generated
    server-side and returned.

    Raises:
        ValueError: if child_spec is not a subtype, or if payload includes
            the framework-owned `kind` key.
    """
    from uuid import uuid4

    if not child_spec.is_polymorphic_child or child_spec.subtype_of != base_spec.name:
        raise ValueError(f"{child_spec.name!r} is not a subtype of {base_spec.name!r}")
    if "kind" in payload:
        raise ValueError(
            "`kind` is framework-owned and auto-populated from the child entity name; "
            "do not pass it in the create payload."
        )

    base_payload, child_payload = _split_payload_by_owner(payload, base_spec, child_spec)

    # #1239: snake_case the child entity name to derive the discriminator
    # value. Mirrors the convention used by the trigger emitter (Task 13)
    # and pg_backend.py's child-table mapping (~line 461).
    from dazzle.core.archetype_expander import _to_snake_case

    new_id = uuid4()
    base_payload["id"] = new_id
    base_payload["kind"] = _to_snake_case(child_spec.name)
    child_payload["id"] = new_id

    base_db = _convert_payload_for_db(base_payload, base_spec)
    child_db = _convert_payload_for_db(child_payload, child_spec)

    ph = db_manager.placeholder

    def _insert_sql(table_name: str, row: dict[str, Any]) -> tuple[str, list[Any]]:
        columns = ", ".join(quote_identifier(k) for k in row.keys())
        placeholders = ", ".join(ph for _ in row)
        sql = f"INSERT INTO {quote_identifier(table_name)} ({columns}) VALUES ({placeholders})"
        return sql, list(row.values())

    base_sql, base_values = _insert_sql(base_spec.name, base_db)
    child_sql, child_values = _insert_sql(child_spec.name, child_db)

    try:
        with db_manager.connection() as conn:
            cursor = conn.cursor()
            # Order matters: base first so the FK on the child row resolves,
            # and so the trigger on the child table sees a base row to read.
            cursor.execute(base_sql, base_values)  # nosemgrep
            cursor.execute(child_sql, child_values)  # nosemgrep
    except _INTEGRITY_ERRORS as exc:
        # Same error shape as plain Repository.create().
        raise _translate_integrity_error(exc, child_spec.name) from exc

    return new_id


def update_subtype(
    *,
    db_manager: Any,
    base_spec: EntitySpec,
    child_spec: EntitySpec,
    row_id: UUID,
    payload: dict[str, Any],
) -> None:
    """Per-table UPDATEs in one transaction. The `kind` discriminator is
    immutable (ADR-0026) — to change subtype, delete + recreate.

    Raises:
        ValueError: if child_spec is not a subtype, or if the payload
            attempts to mutate `kind`.
    """
    if not child_spec.is_polymorphic_child or child_spec.subtype_of != base_spec.name:
        raise ValueError(f"{child_spec.name!r} is not a subtype of {base_spec.name!r}")
    if "kind" in payload:
        raise ValueError(
            "subtype kind is immutable post-create (ADR-0026, #1217 Phase 3e). "
            "To change a subtype, DELETE the row and INSERT a new one (the id will change)."
        )

    base_payload, child_payload = _split_payload_by_owner(payload, base_spec, child_spec)

    # Drop None values to mirror Repository.update() semantics.
    base_payload = {k: v for k, v in base_payload.items() if v is not None}
    child_payload = {k: v for k, v in child_payload.items() if v is not None}

    if not base_payload and not child_payload:
        return

    base_db = _convert_payload_for_db(base_payload, base_spec)
    child_db = _convert_payload_for_db(child_payload, child_spec)

    ph = db_manager.placeholder

    def _update_sql(table_name: str, row: dict[str, Any]) -> tuple[str, list[Any]]:
        set_clause = ", ".join(f"{quote_identifier(k)} = {ph}" for k in row.keys())
        sql = f'UPDATE {quote_identifier(table_name)} SET {set_clause} WHERE "id" = {ph}'
        return sql, [*row.values(), str(row_id)]

    try:
        with db_manager.connection() as conn:
            cursor = conn.cursor()
            if base_db:
                sql, values = _update_sql(base_spec.name, base_db)
                cursor.execute(sql, values)  # nosemgrep
            if child_db:
                sql, values = _update_sql(child_spec.name, child_db)
                cursor.execute(sql, values)  # nosemgrep
    except _INTEGRITY_ERRORS as exc:
        raise _translate_integrity_error(exc, child_spec.name) from exc
