"""Scope-aware GROUP BY aggregations for charts and reports.

Strategy C of the bar_chart fix series (#847/#848/#849/#850/#851 → this).
Replaces the N+1 enumerate-then-per-bucket-count pipeline with a single
``SELECT <dim>, COUNT(*) FROM src WHERE <scope> GROUP BY <dim>`` SQL
statement. One query, one scope evaluation — the bug class where
enumeration and per-bucket counts diverge cannot exist.

Used by ``Repository.aggregate``; exposed as a separate module so the
SQL-builder logic can be unit-tested without spinning up a repo.

Surface area is intentionally small for v1:
- Single-dimension ``group_by`` (multi-dim deferred to v2).
- Measures: ``count`` (always), ``sum:<col>``, ``avg:<col>``, ``min:<col>``,
  ``max:<col>``. Correlated subqueries (``count(child where ...)``) go
  through the existing ``_compute_aggregate_metrics`` path.
- FK ``group_by`` joins the target entity once and pulls the display
  field — no per-bucket round-trip.

Scope contract (aggregate-safe scopes):
- The ``__scope_predicate`` SQL produced by the predicate compiler must
  reference only the source table's columns (or correlated subqueries
  on related tables). Compatible with every scope shape currently
  emitted by ``_resolve_predicate_filters``: direct field equality,
  FK-path subqueries, EXISTS / NOT EXISTS junction lookups, and
  boolean compositions of those.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dazzle_back.runtime.query_builder import QueryBuilder, quote_identifier

# Probe order for FK display fields. Mirrors `_bucket_key_label` in
# workspace_rendering.py — same priorities, same fallback to id.
_FK_DISPLAY_FIELDS: tuple[str, ...] = ("display_name", "name", "title", "label", "code")

# Aggregate measures that don't need a column argument.
_NULLARY_MEASURES: dict[str, str] = {"count": "COUNT(*)"}

# Aggregate measures of the form `<op>:<column>`.
_UNARY_MEASURES: frozenset[str] = frozenset({"sum", "avg", "min", "max"})


@dataclass
class AggregateBucket:
    """One row of an aggregate result.

    Attributes:
        dimensions: GROUP BY values, keyed by column name. For FK
            dimensions the dict carries both ``<col>`` (the FK id) and
            ``<col>_label`` (the resolved display field).
        measures: Computed measures, keyed by metric name as supplied
            in the ``measures`` argument.
    """

    dimensions: dict[str, Any] = field(default_factory=dict)
    measures: dict[str, int | float] = field(default_factory=dict)


def resolve_fk_display_field(target_entity_spec: Any) -> str | None:
    """Pick the first probe-order field present on the target entity.

    Returns None when no probe field matches — caller should render the
    bucket id as the label in that case.
    """
    if not target_entity_spec:
        return None
    field_names = {f.name for f in getattr(target_entity_spec, "fields", [])}
    for candidate in _FK_DISPLAY_FIELDS:
        if candidate in field_names:
            return candidate
    return None


def measure_to_sql(measure: str) -> str | None:
    """Convert a measure spec to its SQL aggregate, or None when unsupported.

    Examples:
        ``"count"`` → ``"COUNT(*)"``
        ``"sum:score"`` → ``"SUM(\"score\")"``
        ``"avg:total_minor"`` → ``"AVG(\"total_minor\")"``
        ``"distinct_count:foo"`` → ``None``  (not supported in v1)
    """
    if measure in _NULLARY_MEASURES:
        return _NULLARY_MEASURES[measure]
    if ":" in measure:
        op, _, col = measure.partition(":")
        if op in _UNARY_MEASURES and col:
            return f"{op.upper()}({quote_identifier(col)})"
    return None


def build_aggregate_sql(
    *,
    table_name: str,
    placeholder_style: str,
    group_by: str,
    measures: dict[str, str],
    fk_table: str | None,
    fk_display_field: str | None,
    filters: dict[str, Any] | None,
    limit: int = 200,
) -> tuple[str, list[Any]]:
    """Compose the GROUP BY SELECT statement.

    The source table is referenced by its bare name (no alias) so the
    scope predicate emitted by ``_resolve_predicate_filters`` — which
    qualifies columns as ``<table>.<col>`` — resolves cleanly. The FK
    target uses the alias ``fk`` to avoid column-name collisions.

    Returns ``(sql, params)`` ready for ``cursor.execute``. Empty SQL
    when no measures resolved.
    """
    src = quote_identifier(table_name)
    group_col_q = quote_identifier(group_by)

    # WHERE via QueryBuilder so __scope_predicate + standard filters
    # parse the same way the repository.list path uses them.
    builder = QueryBuilder(table_name=table_name, placeholder_style=placeholder_style)
    if filters:
        builder.add_filters(filters)
    where_sql, where_params = builder.build_where_clause()

    # Measure SELECT clauses. Skip unsupported measures silently (caller
    # will see a missing key in AggregateBucket.measures).
    measure_sql_parts: list[str] = []
    for metric_name, expr in measures.items():
        sql = measure_to_sql(expr)
        if sql is None:
            continue
        measure_sql_parts.append(f"{sql} AS {quote_identifier(metric_name)}")
    if not measure_sql_parts:
        return "", []

    has_fk_join = bool(fk_table and fk_display_field)
    fk_disp_q = quote_identifier(fk_display_field) if fk_display_field else None
    fk_table_q = quote_identifier(fk_table) if fk_table else None

    # SELECT columns: dimension id, optional FK display, then measures.
    select_parts: list[str] = [f"{src}.{group_col_q} AS bucket_id"]
    if has_fk_join:
        select_parts.append(f"fk.{fk_disp_q} AS bucket_label")
    select_parts.extend(measure_sql_parts)

    # FROM (+ optional LEFT JOIN to the FK target).
    from_clause = f"FROM {src}"
    if has_fk_join:
        from_clause += (
            f" LEFT JOIN {fk_table_q} fk ON {src}.{group_col_q} = fk.{quote_identifier('id')}"
        )

    # GROUP BY mirrors the non-measure SELECT columns.
    group_parts = [f"{src}.{group_col_q}"]
    if has_fk_join:
        group_parts.append(f"fk.{fk_disp_q}")
    group_clause = "GROUP BY " + ", ".join(group_parts)

    # ORDER BY label when joined (more useful for charts), else by id.
    if has_fk_join:
        order_clause = f"ORDER BY fk.{fk_disp_q} NULLS LAST"
    else:
        order_clause = f"ORDER BY {src}.{group_col_q} NULLS LAST"

    sql_parts = [f"SELECT {', '.join(select_parts)}", from_clause]
    if where_sql:
        sql_parts.append(where_sql)
    sql_parts.append(group_clause)
    sql_parts.append(order_clause)
    sql_parts.append(f"LIMIT {int(limit)}")

    return " ".join(sql_parts), where_params


def rows_to_buckets(
    rows: list[Any],
    *,
    group_by: str,
    measures: dict[str, str],
    has_fk_join: bool,
) -> list[AggregateBucket]:
    """Convert raw cursor rows into typed :class:`AggregateBucket` records.

    Rows are expected to be dict-like (psycopg row factory) — falls back
    to positional access for tuple rows.
    """
    measure_keys = [k for k, v in measures.items() if measure_to_sql(v) is not None]
    out: list[AggregateBucket] = []
    for row in rows:
        if hasattr(row, "keys"):
            row_dict: dict[str, Any] = dict(row)
        else:
            keys = ["bucket_id"]
            if has_fk_join:
                keys.append("bucket_label")
            keys.extend(measure_keys)
            row_dict = dict(zip(keys, row, strict=False))

        bucket_id = row_dict.get("bucket_id")
        dims: dict[str, Any] = {group_by: bucket_id}
        if has_fk_join:
            label = row_dict.get("bucket_label")
            dims[f"{group_by}_label"] = label if label is not None else bucket_id

        meas: dict[str, int | float] = {}
        for k in measure_keys:
            v = row_dict.get(k, 0)
            meas[k] = v if isinstance(v, int | float) else int(v or 0)

        out.append(AggregateBucket(dimensions=dims, measures=meas))
    return out
