"""Scope-aware GROUP BY aggregations for charts and reports.

Strategy C of the bar_chart fix series (#847/#848/#849/#850/#851) plus
the multi-dimension extension that lays the foundation for Layer 3 of
the aggregate stack (cycle 25).

Replaces the N+1 enumerate-then-per-bucket-count pipeline with a single
``SELECT <dims>, <measures> FROM src [LEFT JOIN ...]
WHERE <scope> GROUP BY <dims>`` SQL statement. One query, one scope
evaluation — the bug class where enumeration and per-bucket counts
diverge cannot exist.

Used by ``Repository.aggregate``; exposed as a separate module so the
SQL-builder logic can be unit-tested without spinning up a repo.

Surface area for v2 (cycle 25):
- **Multi-dimension** ``GROUP BY`` (cross-tab tables, pivot rendering).
  Each dimension is either scalar or FK; FK dims auto-LEFT JOIN the
  target and pull a display field.
- Measures: ``count`` (always), ``sum:<col>``, ``avg:<col>``,
  ``min:<col>``, ``max:<col>``. Correlated subqueries (``count(child
  where ...)``) go through the existing ``_compute_aggregate_metrics``
  path on workspace_rendering.

Scope contract (aggregate-safe scopes):
- The ``__scope_predicate`` SQL produced by the predicate compiler
  must reference only the source table's columns (or correlated
  subqueries on related tables). Compatible with every scope shape
  currently emitted by ``_resolve_predicate_filters``: direct field
  equality, FK-path subqueries, EXISTS / NOT EXISTS junction
  lookups, and boolean compositions of those. Multi-dimension does
  not change this contract — the FK joins added for label resolution
  use a distinct alias and don't shadow the source table name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from dazzle.http.runtime.query_builder import QueryBuilder, quote_identifier

# Probe order for FK display fields. Mirrors `_bucket_key_label` in
# workspace_rendering.py — same priorities, same fallback to id.
_FK_DISPLAY_FIELDS: tuple[str, ...] = ("display_name", "name", "title", "label", "code")

# Aggregate measures that don't need a column argument.
_NULLARY_MEASURES: dict[str, str] = {"count": "COUNT(*)"}

# Aggregate measures of the form `<op>:<column>`.
_UNARY_MEASURES: frozenset[str] = frozenset({"sum", "avg", "min", "max"})

# Time-bucket granularities. Whitelist — NEVER interpolate user input into
# the date_trunc unit string; PostgreSQL treats the unit as a literal but
# the typing below also blocks any other value reaching build_aggregate_sql.
TruncateUnit = Literal["day", "week", "month", "quarter", "year"]
_VALID_TRUNCATE_UNITS: frozenset[str] = frozenset({"day", "week", "month", "quarter", "year"})

# PG type names a time-bucket column may be cast to before ``date_trunc``.
# date/datetime DSL fields are stored as TEXT, and ``date_trunc(unknown, text)``
# does not exist — the cast makes Postgres resolve the timestamptz/date overload
# (#1514). Casting an already-typed timestamp column is a harmless no-op. The
# value is whitelist-validated so it is never untrusted interpolation.
_VALID_BUCKET_CASTS: frozenset[str] = frozenset({"date", "timestamp", "timestamptz"})


@dataclass(frozen=True)
class Dimension:
    """A single GROUP BY dimension on an aggregate query.

    Attributes:
        name: Column name on the source entity to bucket by.
        fk_table: Target entity name when ``name`` is a foreign key.
            Triggers a LEFT JOIN so the bucket label resolves to a
            human-readable column on the target. ``None`` for scalar /
            enum / state dimensions.
        fk_display_field: Column on the target table to use as the
            bucket label. Caller resolves via :func:`resolve_fk_display_field`
            against the target's EntitySpec. Required when ``fk_table``
            is set.
        truncate: When set, applies ``date_trunc('<unit>', col)`` — the
            dimension buckets by calendar unit rather than distinct
            value. Mutually exclusive with ``fk_table`` (an FK column
            isn't a timestamp). Time dims render in chronological ASC
            order, not alphabetical. Unit is validated on construction.
        bucket_cast: PG type name (``date`` / ``timestamp`` / ``timestamptz``)
            to cast the bucketed column to before ``date_trunc``. Required when
            the date/datetime field is TEXT-stored (the Dazzle convention), as
            ``date_trunc(unknown, text)`` has no overload (#1514). Whitelist-
            validated; ``None`` emits the cast-free expression (unchanged).
    """

    name: str
    fk_table: str | None = None
    fk_display_field: str | None = None
    truncate: TruncateUnit | None = None
    bucket_cast: str | None = None

    def __post_init__(self) -> None:
        if self.bucket_cast is not None and self.bucket_cast not in _VALID_BUCKET_CASTS:
            raise ValueError(
                f"Invalid bucket cast {self.bucket_cast!r}; "
                f"expected one of {sorted(_VALID_BUCKET_CASTS)}"
            )
        if self.truncate is not None:
            if self.truncate not in _VALID_TRUNCATE_UNITS:
                raise ValueError(
                    f"Invalid truncate unit {self.truncate!r}; "
                    f"expected one of {sorted(_VALID_TRUNCATE_UNITS)}"
                )
            if self.fk_table is not None:
                raise ValueError(
                    "Dimension cannot combine truncate (time bucket) "
                    "with fk_table (FK join) — a timestamp column is "
                    "not a foreign key."
                )

    @property
    def has_fk_join(self) -> bool:
        return bool(self.fk_table and self.fk_display_field)

    @property
    def is_time_bucket(self) -> bool:
        return self.truncate is not None


@dataclass
class AggregateBucket:
    """One row of an aggregate result.

    Attributes:
        dimensions: GROUP BY values, keyed by dimension name. For FK
            dimensions the dict carries both ``<name>`` (the FK id) and
            ``<name>_label`` (the resolved display field).
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
        ``"distinct_count:foo"`` → ``None``  (not supported in v2)
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
    dimensions: list[Dimension],
    measures: dict[str, str],
    filters: dict[str, Any] | None,
    limit: int = 200,
    measure_expressions: dict[str, tuple[str, list[Any]]] | None = None,
) -> tuple[str, list[Any]]:
    """Compose the multi-dimension GROUP BY SELECT statement.

    The source table is referenced by its bare name (no alias) so the
    scope predicate emitted by ``_resolve_predicate_filters`` — which
    qualifies columns as ``<table>.<col>`` — resolves cleanly. Each FK
    dimension uses an indexed alias (``fk_0``, ``fk_1``, ...) so two
    FK dimensions referencing the same target table don't collide.

    Returns ``(sql, params)`` ready for ``cursor.execute``. Empty SQL
    when no measures resolved.

    Two shapes supported:
      - **With dimensions**: standard GROUP BY query — one row per
        bucket combination, with measures aggregated per group.
      - **Without dimensions** (#904): scalar aggregate over the whole
        table — one row, no GROUP BY. ``rows_to_buckets`` produces a
        single bucket with empty `dimensions` and the measure values.
        This is the path `_fetch_scalar_metric` uses for region-level
        ``avg/sum/min/max`` summary tiles.

    L3 expressions (#1152): ``measure_expressions`` carries precompiled
    measure SQL fragments produced by
    :func:`dazzle.http.runtime.aggregate_expression.compile_aggregate_expression`
    for each L3 measure. The fragment is the inner argument to the SQL
    aggregate (``AVG(<fragment>)``); the ``measures`` mapping carries
    the outer function name as ``"<func>:__expr__"`` so the inner SQL
    can be picked up by key. Parameters for the inner expression are
    placed in the SELECT-clause position of the final param list, ahead
    of the WHERE-clause parameters.
    """
    from dazzle.perf.tracer import dazzle_span

    with dazzle_span(
        "aggregate.build_sql",
        table_name=table_name,
        dimension_count=len(dimensions),
        measure_count=len(measures),
    ):
        return _build_aggregate_sql_impl(
            table_name=table_name,
            placeholder_style=placeholder_style,
            dimensions=dimensions,
            measures=measures,
            filters=filters,
            limit=limit,
            measure_expressions=measure_expressions,
        )


def _build_aggregate_sql_impl(
    *,
    table_name: str,
    placeholder_style: str,
    dimensions: list[Dimension],
    measures: dict[str, str],
    filters: dict[str, Any] | None,
    limit: int = 200,
    measure_expressions: dict[str, tuple[str, list[Any]]] | None = None,
) -> tuple[str, list[Any]]:
    src = quote_identifier(table_name)

    # WHERE via QueryBuilder so __scope_predicate + standard filters
    # parse the same way the repository.list path uses them.
    builder = QueryBuilder(table_name=table_name, placeholder_style=placeholder_style)
    if filters:
        builder.add_filters(filters)
    where_sql, where_params = builder.build_where_clause()

    # Measure SELECT clauses. Skip unsupported measures silently
    # (caller will see a missing key in AggregateBucket.measures).
    measure_sql_parts: list[str] = []
    measure_params: list[Any] = []
    measure_expressions = measure_expressions or {}
    for metric_name, expr in measures.items():
        if metric_name in measure_expressions:
            # L3: outer function name + precompiled inner SQL fragment.
            # ``expr`` here carries the aggregate function (``avg`` /
            # ``sum`` / ``min`` / ``max``) as a bare keyword — caller
            # constructs ``measures[name] = ref.func`` for L3 entries.
            func = expr.lower()
            if func in _UNARY_MEASURES:
                inner_sql, inner_params = measure_expressions[metric_name]
                measure_sql_parts.append(
                    f"{func.upper()}({inner_sql}) AS {quote_identifier(metric_name)}"
                )
                measure_params.extend(inner_params)
                continue
            # Fall through — unrecognised L3 outer func is silently dropped,
            # mirroring the legacy measure_to_sql behaviour.
            continue
        sql = measure_to_sql(expr)
        if sql is None:
            continue
        measure_sql_parts.append(f"{sql} AS {quote_identifier(metric_name)}")
    if not measure_sql_parts:
        return "", []

    # Scalar aggregate path — no dimensions, no GROUP BY (#904). One
    # row containing the measure values for the whole filtered table.
    if not dimensions:
        sql_parts = [
            f"SELECT {', '.join(measure_sql_parts)}",
            f"FROM {src}",
        ]
        if where_sql:
            sql_parts.append(where_sql)
        sql_parts.append(f"LIMIT {int(limit)}")
        return " ".join(sql_parts), measure_params + where_params

    # Per-dimension SELECT + GROUP BY + ORDER BY parts. Indexed aliases
    # for FK joins guard against duplicate-target collisions.
    select_parts: list[str] = []
    join_parts: list[str] = []
    group_parts: list[str] = []
    order_parts: list[str] = []
    for i, dim in enumerate(dimensions):
        col_q = quote_identifier(dim.name)
        id_alias = quote_identifier(f"dim_{i}_id")
        if dim.is_time_bucket:
            # `truncate` and `bucket_cast` are both whitelist-validated in
            # Dimension.__post_init__, so inlining them here is safe. The cast
            # makes date_trunc resolve for TEXT-stored date columns (#1514);
            # it's a no-op on an already-typed timestamp.
            cast_suffix = f"::{dim.bucket_cast}" if dim.bucket_cast else ""
            bucket_expr = f"date_trunc('{dim.truncate}', {src}.{col_q}{cast_suffix})"
            select_parts.append(f"{bucket_expr} AS {id_alias}")
            group_parts.append(bucket_expr)
            # Chronological order — ASC so earliest bucket first.
            order_parts.append(f"{bucket_expr} ASC NULLS LAST")
        elif dim.has_fk_join:
            select_parts.append(f"{src}.{col_q} AS {id_alias}")
            group_parts.append(f"{src}.{col_q}")
            fk_alias = f"fk_{i}"
            fk_t = quote_identifier(dim.fk_table or "")
            fk_disp_q = quote_identifier(dim.fk_display_field or "")
            label_alias = quote_identifier(f"dim_{i}_label")
            select_parts.append(f"{fk_alias}.{fk_disp_q} AS {label_alias}")
            join_parts.append(
                f"LEFT JOIN {fk_t} {fk_alias} "
                f"ON {src}.{col_q} = {fk_alias}.{quote_identifier('id')}"
            )
            group_parts.append(f"{fk_alias}.{fk_disp_q}")
            # Order by label when joined — easier to read in chart/table.
            order_parts.append(f"{fk_alias}.{fk_disp_q} NULLS LAST")
        else:
            select_parts.append(f"{src}.{col_q} AS {id_alias}")
            group_parts.append(f"{src}.{col_q}")
            order_parts.append(f"{src}.{col_q} NULLS LAST")

    select_parts.extend(measure_sql_parts)

    from_clause = f"FROM {src}"
    if join_parts:
        from_clause += " " + " ".join(join_parts)

    sql_parts = [f"SELECT {', '.join(select_parts)}", from_clause]
    if where_sql:
        sql_parts.append(where_sql)
    sql_parts.append("GROUP BY " + ", ".join(group_parts))
    sql_parts.append("ORDER BY " + ", ".join(order_parts))
    sql_parts.append(f"LIMIT {int(limit)}")

    return " ".join(sql_parts), measure_params + where_params


def rows_to_buckets(
    rows: list[Any],
    *,
    dimensions: list[Dimension],
    measures: dict[str, str],
    measure_expressions: dict[str, tuple[str, list[Any]]] | None = None,
) -> list[AggregateBucket]:
    """Convert raw cursor rows into typed :class:`AggregateBucket` records.

    Rows are expected to be dict-like (psycopg row factory) — falls back
    to positional access for tuple rows. Measures with unsupported
    specs (per :func:`measure_to_sql`) are silently skipped — same
    contract as ``build_aggregate_sql``.

    ``measure_expressions`` mirrors the same dict passed to
    :func:`build_aggregate_sql` — its keys are also valid measure-result
    columns and survive the unsupported-measure filter.
    """
    measure_expressions = measure_expressions or {}
    measure_keys = [
        k for k, v in measures.items() if k in measure_expressions or measure_to_sql(v) is not None
    ]

    # Reconstruct the column ordering the SQL emits when row is a tuple.
    positional_keys: list[str] = []
    for i, dim in enumerate(dimensions):
        positional_keys.append(f"dim_{i}_id")
        if dim.has_fk_join:
            positional_keys.append(f"dim_{i}_label")
    positional_keys.extend(measure_keys)

    out: list[AggregateBucket] = []
    for row in rows:
        if hasattr(row, "keys"):
            row_dict: dict[str, Any] = dict(row)
        else:
            row_dict = dict(zip(positional_keys, row, strict=False))

        dims: dict[str, Any] = {}
        for i, dim in enumerate(dimensions):
            bucket_id = row_dict.get(f"dim_{i}_id")
            dims[dim.name] = bucket_id
            if dim.has_fk_join:
                label = row_dict.get(f"dim_{i}_label")
                dims[f"{dim.name}_label"] = label if label is not None else bucket_id

        meas: dict[str, int | float] = {}
        for k in measure_keys:
            v = row_dict.get(k, 0)
            # `avg(int_col)` in Postgres returns Decimal which is neither
            # int nor float. Casting to int truncates fractional means
            # like 6.8 → 6 (and 0.8 → 0 — the symptom in #904).
            # Decimal → float preserves the value for the renderer (which
            # JSON-serialises) without losing precision in the typical
            # display range.
            if isinstance(v, int | float):
                meas[k] = v
            elif v is None:
                meas[k] = 0
            else:
                # Decimal, str, or any other numeric — go through float()
                # so fractional means render correctly.
                try:
                    meas[k] = float(v)
                except (TypeError, ValueError):
                    meas[k] = 0

        out.append(AggregateBucket(dimensions=dims, measures=meas))
    return out
