"""Aggregate-metric machinery: bucketed counts, pivots, histograms.

Extracted from workspace_rendering.py in #1057 cut 4 (v0.67.103).
Owns the SQL aggregation path used by chart, pivot, histogram,
box-plot, KPI, and bucketed bar/line region types. All callers
go through `_compute_aggregate_metrics` (single-bucket scalar
counts) or `_compute_bucketed_aggregates` (group_by ladders).

The module is scope-aware: scope filters are merged into every
aggregate query so RBAC pre-aggregation can never leak across
tenants.

Per ADR-0024 the top-level entry points (``_compute_aggregate_metrics``,
``_compute_bucketed_aggregates``, ``_compute_pivot_buckets``) accept
``dict[str, AggregateRef]`` and dispatch on the typed IR fields
directly — no regex. The where-clause is still stringified at the
boundary to the existing ``_fetch_*`` helpers (Slice 2 retires that
string round-trip by folding ``parse_aggregate_where`` into the main
predicate parser).

Contents:
- `_format_bucket_label`: human label for a date_trunc bucket value.
- `_build_aggregate_filters`: merge scope + WHERE filters for a query.
- `_fetch_count_metric`, `_fetch_scalar_metric`: single-metric paths.
- `_resolve_fk_target_spec`: FK → target entity lookup for joins.
- `_compute_pivot_buckets`, `_aggregate_via_groupby`: GROUP BY paths.
- `_enumerate_distinct_buckets`: pivot-axis cardinality probe.
- `_compute_box_plot_stats`, `_compute_histogram_bins`: distribution shapes.
- `_compute_bucketed_aggregates`: top-level bucketed dispatcher.
- `_bucket_key_label`: shared key/label tuple for a bucket value.
- `_compute_aggregate_metrics`: top-level scalar dispatcher.
- `_parse_simple_where`: legacy WHERE parser (still used by fast path).
"""

import asyncio
import datetime as _dt
import logging
from typing import Any

from dazzle.render.display_names import _resolve_display_name

logger = logging.getLogger(__name__)


def _condition_references_current_bucket(expr: Any) -> bool:
    """Detect whether a :class:`ConditionExpr` references the
    ``current_bucket`` sentinel used by bar_chart's per-bucket
    aggregate path. Walks compound conditions recursively.

    Used by the pivot fast-path gate (which only handles aggregates
    that don't substitute per-bucket values).

    Reads the typed :attr:`ConditionValue.current_bucket` flag (#1154);
    falls back to the legacy literal-string detection for ConditionExpr
    instances that haven't been re-parsed since the flag landed
    (e.g. unit fixtures constructed by hand).
    """
    from dazzle.core.ir import ConditionExpr

    if not isinstance(expr, ConditionExpr):
        return False
    if expr.is_compound:
        return _condition_references_current_bucket(
            expr.left
        ) or _condition_references_current_bucket(expr.right)
    cmp = expr.comparison
    if cmp is None:
        return False
    val = cmp.value
    if val.current_bucket:
        return True
    if val.is_list and val.values is not None:
        return any(v == "current_bucket" for v in val.values)
    return val.literal == "current_bucket"


def _substitute_current_bucket(expr: Any, bucket_key: str) -> Any:
    """Return a copy of ``expr`` with every ``current_bucket`` sentinel
    replaced by a typed literal ``ConditionValue(literal=bucket_key)``.

    The IR is frozen, so substitution rebuilds nodes via ``model_copy``.
    Walks compound conditions recursively. Used by the bar_chart
    bucketed-aggregate slow path (#1154) to evaluate each bucket's
    where-clause with a typed ConditionExpr rather than a stringified
    one.

    Non-sentinel values pass through unchanged. ``ConditionExpr``
    inputs that aren't a comparison/compound (role_check / grant_check
    / via_condition) also pass through — those shapes can't legally
    contain the sentinel.
    """
    from dazzle.core.ir import ConditionExpr, ConditionValue

    if not isinstance(expr, ConditionExpr):
        return expr
    if expr.is_compound:
        return expr.model_copy(
            update={
                "left": _substitute_current_bucket(expr.left, bucket_key),
                "right": _substitute_current_bucket(expr.right, bucket_key),
            }
        )
    cmp = expr.comparison
    if cmp is None:
        return expr
    val = cmp.value
    if val.current_bucket:
        new_val = ConditionValue(literal=bucket_key)
        new_cmp = cmp.model_copy(update={"value": new_val})
        return expr.model_copy(update={"comparison": new_cmp})
    if val.is_list and val.values is not None and any(v == "current_bucket" for v in val.values):
        new_values: list[str | int | float | bool] = [
            bucket_key if v == "current_bucket" else v for v in val.values
        ]
        new_val = ConditionValue(values=new_values)
        new_cmp = cmp.model_copy(update={"value": new_val})
        return expr.model_copy(update={"comparison": new_cmp})
    return expr


def _format_bucket_label(value: Any, unit: str) -> str:
    """Render a time-bucket SQL value as a human-readable string.

    ``date_trunc`` returns a datetime object (or tz-aware datetime on
    timestamptz columns). We emit a stable, locale-free label per unit
    so templates, snapshot tests, and charts all agree.

        day     → ``2026-04-23``
        week    → ``2026-W17``    (ISO week — Monday start)
        month   → ``Apr 2026``
        quarter → ``Q2 2026``
        year    → ``2026``

    Non-datetime / None values pass through as ``str(value)`` — the caller
    is responsible for deciding whether a null time bucket deserves a
    placeholder or should be filtered out.
    """
    if value is None:
        return ""
    if not isinstance(value, _dt.datetime | _dt.date):
        return str(value)
    # date (from date_trunc on a date column) vs datetime — both have
    # the strftime hooks we need.
    if unit == "day":
        return value.strftime("%Y-%m-%d")
    if unit == "week":
        # ISO week format — `%G` is ISO year, `%V` is ISO week number.
        return value.strftime("%G-W%V")
    if unit == "month":
        return value.strftime("%b %Y")
    if unit == "quarter":
        month = value.month
        quarter = (month - 1) // 3 + 1
        return f"Q{quarter} {value.year}"
    if unit == "year":
        return str(value.year)
    return str(value)


def _build_aggregate_filters(
    where: Any,  # ConditionExpr | str | None — strings retire when current_bucket migrates
    scope_filters: dict[str, Any] | None,
    agg_repo: Any,
    source_entity: str,
) -> dict[str, Any] | None:
    """Compose aggregate where-clause + scope into a filter dict for
    ``Repository.list`` / ``Repository.aggregate``.

    Per ADR-0024 / Slice 2 of the aggregate migration, ``where`` is
    typed as :class:`ConditionExpr` (translated to ``ScopePredicate``
    via :func:`condition_expr_to_scope_predicate`, then compiled to
    SQL via :func:`compile_predicate`). The string path remains as a
    deprecated fallback for the bar_chart fast-path which substitutes
    a ``current_bucket`` sentinel into the where-clause text before
    re-parsing — that consumer migrates separately when the sentinel
    moves to an IR-level marker.

    When ``scope_filters`` already carries a ``__scope_predicate``
    (from the route generator's RBAC compiler or upstream callers),
    the two SQL fragments are AND-combined into a single slot.
    """
    from dazzle.core.ir import ConditionExpr

    base: dict[str, Any] = dict(scope_filters) if scope_filters else {}
    if where is None or (isinstance(where, str) and not where):
        return base or None

    from dazzle.back.runtime.predicate_compiler import compile_predicate
    from dazzle.core.ir.fk_graph import FKGraph as _FKGraph

    if isinstance(where, ConditionExpr):
        # Typed path — no string round-trip, no parse step.
        from dazzle.core.ir.condition_to_predicate import condition_expr_to_scope_predicate

        try:
            pred = condition_expr_to_scope_predicate(where)
        except ValueError:
            logger.debug(
                "ConditionExpr translation to ScopePredicate failed; skipping where-clause",
                exc_info=True,
            )
            return base or None
    else:
        # Legacy string path — used by bar_chart's `current_bucket`
        # sentinel substitution. Once that substitution moves to the
        # ConditionExpr layer this branch can delete.
        from dazzle.back.runtime.aggregate_where_parser import parse_aggregate_where

        spec = getattr(agg_repo, "entity_spec", None)
        known_cols: frozenset[str] = (
            frozenset(f.name for f in getattr(spec, "fields", []))
            if spec is not None
            else frozenset()
        )
        try:
            pred = parse_aggregate_where(where, known_columns=known_cols)
        except ValueError as exc:
            logger.debug(
                "Aggregate where-clause %r didn't parse via algebra (%s) — "
                "falling back to legacy _parse_simple_where",
                where,
                exc,
            )
            legacy = _parse_simple_where(where)
            base.update(legacy)
            return base or None

    where_sql, where_params = compile_predicate(pred, source_entity, _FKGraph())
    if not where_sql:
        return base or None

    existing_pred = base.get("__scope_predicate")
    if existing_pred is None:
        base["__scope_predicate"] = (where_sql, where_params)
    else:
        existing_sql, existing_params = existing_pred
        base["__scope_predicate"] = (
            f"({existing_sql}) AND ({where_sql})",
            list(existing_params) + list(where_params),
        )
    return base


async def _fetch_count_metric(
    metric_name: str,
    agg_repo: Any,
    where: Any,  # ConditionExpr | str | None — typed post-Slice 2
    scope_filters: dict[str, Any] | None = None,
    *,
    source_entity: str = "",
) -> tuple[str, Any]:
    """Fetch a single count aggregate metric from a repository.

    Per ADR-0024 / Slice 2 ``where`` is typed as :class:`ConditionExpr`
    in the main aggregate paths; the string branch remains for the
    bar_chart fast-path that substitutes ``current_bucket`` text.
    """
    try:
        agg_filters = _build_aggregate_filters(where, scope_filters, agg_repo, source_entity)
        agg_result = await agg_repo.list(page=1, page_size=1, filters=agg_filters)
        if isinstance(agg_result, dict):
            return metric_name, agg_result.get("total", 0)
    except Exception:
        logger.warning("Failed to compute aggregate metric %s", metric_name, exc_info=True)
    return metric_name, 0


async def _fetch_scalar_metric(
    metric_name: str,
    func: str,
    field_name: str | None,
    agg_repo: Any,
    where: Any,  # ConditionExpr | str | None — typed post-Slice 2
    scope_filters: dict[str, Any] | None = None,
    *,
    source_entity: str = "",
    expression: Any = None,  # ir.AggregateExpr | None — L3 (#1152)
    expression_alias: str | None = None,
) -> tuple[str, Any]:
    """Fetch a sum/avg/min/max aggregate metric (#888 Phase 1).

    L3 (#1152): when ``expression`` is set, ``field_name`` is ignored
    and the inner aggregate argument comes from the precompiled
    expression IR. ``expression_alias`` is the table-prefix applied to
    bare column refs inside the expression (typically the aggregated
    entity name for cross-entity expressions; ``None`` for
    source-relative ones).
    """
    try:
        agg_filters = _build_aggregate_filters(where, scope_filters, agg_repo, source_entity)
        measures: dict[str, str] = {metric_name: ""}
        measure_expressions: dict[str, tuple[str, list[Any]]] | None = None
        if expression is not None:
            from dazzle.back.runtime.aggregate_expression import (
                compile_aggregate_expression,
            )

            expr_sql, expr_params = compile_aggregate_expression(
                expression,
                placeholder=agg_repo.db.placeholder,
                table_alias=expression_alias,
            )
            measures[metric_name] = func
            measure_expressions = {metric_name: (expr_sql, expr_params)}
        else:
            measures[metric_name] = f"{func}:{field_name}"
        buckets = await agg_repo.aggregate(
            dimensions=[],
            measures=measures,
            filters=agg_filters,
            limit=1,
            measure_expressions=measure_expressions,
        )
        if buckets:
            value = buckets[0].measures.get(metric_name, 0)
            return metric_name, value
    except Exception:
        logger.warning("Failed to compute aggregate metric %s", metric_name, exc_info=True)
    return metric_name, 0


def _resolve_fk_target_spec(
    source_repo: Any,
    group_by: str,
    repositories: dict[str, Any] | None,
) -> Any | None:
    """Walk source_entity → field(group_by) → ref_entity → other repo's spec.

    Returns the target entity's EntitySpec when ``group_by`` is an FK,
    or None when it's a scalar / enum / state field. Used to drive
    ``aggregate.resolve_fk_display_field`` so the bar label resolves
    to the human-readable column on the related entity.
    """
    spec = getattr(source_repo, "entity_spec", None)
    if spec is None or repositories is None:
        return None
    field = next((f for f in getattr(spec, "fields", []) if f.name == group_by), None)
    if field is None:
        return None
    ftype = getattr(field, "type", None)
    if ftype is None or getattr(ftype, "kind", None) != "ref":
        return None
    target_entity = getattr(ftype, "ref_entity", None)
    if not target_entity:
        return None
    target_repo = repositories.get(target_entity)
    return getattr(target_repo, "entity_spec", None) if target_repo else None


async def _compute_pivot_buckets(
    aggregates: dict[str, str],
    repositories: dict[str, Any] | None,
    group_by_dims: list[Any],
    *,
    source_entity: str | None,
    source_entity_spec: Any,
    scope_filters: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Multi-dimension aggregate for pivot_table regions (cycle 25).

    Returns ``(buckets, dim_specs)`` where:
      * ``buckets`` is a list of ``{dim_<name>: <id>, dim_<name>_label:
        <display>, <metric>: <value>, ...}`` dicts ready for the
        template to render rows from;
      * ``dim_specs`` is a list of ``{name, label, is_fk}`` describing
        each dimension column header.

    For each dim that's a FK on the source entity, the runtime resolves
    the target's display field and routes the LEFT JOIN through
    ``Repository.aggregate``. Scalar dims pass through verbatim.
    """
    if not aggregates or not repositories or not source_entity:
        return [], []

    from dazzle.back.runtime.aggregate import Dimension, resolve_fk_display_field
    from dazzle.core.ir import AggregateRef
    from dazzle.core.ir.aggregate_legacy import condition_expr_to_legacy_where

    # Only the simple case (count(<source_entity>) with no current_bucket)
    # routes through the pivot fast path. Other shapes fall through.
    metric_name, ref = next(iter(aggregates.items()))
    if not isinstance(ref, AggregateRef) or ref.func != "count":
        return [], []
    entity_name = ref.entity or ""
    if entity_name != source_entity or _condition_references_current_bucket(ref.where):
        return [], []
    # Stringify for the legacy `_parse_simple_where` filter merge below
    # — the pivot path retains string-based merge until a future cleanup.
    where_clause = condition_expr_to_legacy_where(ref.where)

    source_repo = repositories.get(source_entity)
    if source_repo is None:
        return [], []

    # Resolve each dim — FK target spec (if any), display field via probe,
    # or time-bucket via BucketRef (cycle 28).
    from dazzle.core.ir import BucketRef

    dimensions: list[Dimension] = []
    dim_specs: list[dict[str, Any]] = []
    for dim_entry in group_by_dims:
        if isinstance(dim_entry, BucketRef):
            # Time-bucketed dim — no FK, no enum, just date_trunc on the
            # timestamp column. The label generator in _format_bucket_label
            # handles the display format.
            dimensions.append(Dimension(name=dim_entry.field, truncate=dim_entry.unit))
            dim_specs.append(
                {
                    "name": dim_entry.field,
                    "label": dim_entry.field.replace("_", " ").title(),
                    "is_fk": False,
                    "is_time_bucket": True,
                    "unit": dim_entry.unit,
                }
            )
            continue

        dim_name = dim_entry
        fld = next(
            (f for f in getattr(source_entity_spec, "fields", []) if f.name == dim_name),
            None,
        )
        ftype = getattr(fld, "type", None) if fld else None
        is_fk = ftype is not None and getattr(ftype, "kind", None) == "ref"
        fk_table = None
        fk_display_field = None
        if is_fk:
            target_name = getattr(ftype, "ref_entity", None)
            target_repo = repositories.get(target_name) if target_name else None
            target_spec = getattr(target_repo, "entity_spec", None) if target_repo else None
            fk_table = target_name
            fk_display_field = resolve_fk_display_field(target_spec)
        dimensions.append(
            Dimension(name=dim_name, fk_table=fk_table, fk_display_field=fk_display_field)
        )
        dim_specs.append(
            {
                "name": dim_name,
                "label": dim_name.replace("_", " ").title(),
                "is_fk": bool(fk_table and fk_display_field),
                "is_time_bucket": False,
                "unit": None,
            }
        )

    # Merge any author-supplied where clause + scope filters.
    merged_filters: dict[str, Any] = {}
    if where_clause:
        merged_filters.update(_parse_simple_where(where_clause))
    if scope_filters:
        merged_filters = {**scope_filters, **merged_filters}

    try:
        buckets = await source_repo.aggregate(
            dimensions=dimensions,
            measures={metric_name: "count"},
            filters=merged_filters or None,
        )
    except Exception:
        # Promoted to ERROR for #854 — a silent WARNING on a pivot region's
        # only failure path made the root cause invisible in production logs.
        # The dimensions + merged filter dict are logged so operators can
        # reproduce the exact SQL via `dazzle db explain-aggregate` without
        # needing repository internals.
        logger.error(
            "Pivot aggregate FAILED for %s by %r — returning empty buckets. "
            "dimensions=%r filters=%r",
            source_entity,
            group_by_dims,
            [(d.name, d.fk_table, d.fk_display_field, d.truncate) for d in dimensions],
            merged_filters or None,
            exc_info=True,
        )
        return [], dim_specs

    out: list[dict[str, Any]] = []
    for b in buckets:
        row: dict[str, Any] = {}
        for spec in dim_specs:
            raw = b.dimensions.get(spec["name"])
            row[spec["name"]] = raw
            if spec["is_fk"]:
                lbl_key = f"{spec['name']}_label"
                row[lbl_key] = b.dimensions.get(lbl_key) or raw
            elif spec.get("is_time_bucket"):
                # Formatted label + ISO string for chart axes / JSON.
                row[f"{spec['name']}_label"] = _format_bucket_label(raw, spec["unit"])
                if isinstance(raw, _dt.datetime | _dt.date):
                    row[spec["name"]] = raw.isoformat()
        for k, v in b.measures.items():
            row[k] = v
        out.append(row)
    return out, dim_specs


async def _aggregate_via_groupby(
    agg_repo: Any,
    *,
    measures: dict[str, str],
    group_by: Any,  # str | BucketRef
    where_clause: str | None,
    scope_filters: dict[str, Any] | None,
    source_entity_spec: Any,
    fk_target_spec: Any | None,
) -> list[dict[str, Any]]:
    """Run the bar-chart distribution as a single GROUP BY query.

    Strategy C — replaces the N+1 enumerate-then-per-bucket-count
    pipeline (#847–#851) with one ``Repository.aggregate`` call. The
    aggregate method composes ``SELECT <dim>, COUNT(*) FROM src LEFT
    JOIN <fk>... WHERE <scope> GROUP BY <dim>`` and returns the buckets
    + counts in a single round-trip. No enumeration phase, no per-bucket
    queries, no possibility of the two paths producing different scoped
    row sets.

    v0.61.32 (#879/#883 enabling): ``measures`` is a dict of
    ``{metric_name: spec}`` where spec is ``"count"`` or
    ``"<op>:<column>"`` (avg/sum/min/max) — enables multi-series charts
    by firing ALL measures in one query. Each returned bucket carries
    ``value`` (first measure, legacy alias) plus ``metrics: {<name>:
    <value>, ...}`` for templates that want all of them.
    """
    from dazzle.back.runtime.aggregate import Dimension, resolve_fk_display_field
    from dazzle.core.ir import BucketRef

    if not measures:
        return []

    first_metric_name = next(iter(measures))

    # Merge any author-supplied where clause into the filter dict via
    # _parse_simple_where — same semantics the slow path used to apply
    # before its per-bucket extension.
    merged_filters: dict[str, Any] = {}
    if where_clause:
        merged_filters.update(_parse_simple_where(where_clause))
    if scope_filters:
        merged_filters = {**scope_filters, **merged_filters}

    def _build_metrics_dict(b: Any) -> dict[str, Any]:
        return {name: b.measures.get(name, 0) for name in measures}

    # Time-bucketed single-dim path — no FK join, date_trunc in SQL.
    if isinstance(group_by, BucketRef):
        bucket_dim = Dimension(name=group_by.field, truncate=group_by.unit)  # type: ignore[arg-type]
        buckets = await agg_repo.aggregate(
            dimensions=[bucket_dim],
            measures=measures,
            filters=merged_filters or None,
        )
        out: list[dict[str, Any]] = []
        for b in buckets:
            raw = b.dimensions.get(group_by.field)
            if raw is None:
                continue
            label = _format_bucket_label(raw, group_by.unit)
            iso = raw.isoformat() if isinstance(raw, _dt.datetime | _dt.date) else str(raw)
            metrics = _build_metrics_dict(b)
            out.append(
                {
                    "label": label,
                    "value": metrics[first_metric_name],
                    "metrics": metrics,
                    "bucket": iso,
                }
            )
        return out

    fk_table = getattr(fk_target_spec, "name", None) if fk_target_spec is not None else None
    fk_display_field = (
        resolve_fk_display_field(fk_target_spec) if fk_target_spec is not None else None
    )

    dim = Dimension(name=group_by, fk_table=fk_table, fk_display_field=fk_display_field)
    buckets = await agg_repo.aggregate(
        dimensions=[dim],
        measures=measures,
        filters=merged_filters or None,
    )

    out = []
    for b in buckets:
        bucket_id = b.dimensions.get(group_by)
        if bucket_id is None:
            continue
        label_key = f"{group_by}_label"
        label = b.dimensions.get(label_key) or str(bucket_id)
        metrics = _build_metrics_dict(b)
        out.append(
            {
                "label": str(label),
                "value": metrics[first_metric_name],
                "metrics": metrics,
            }
        )
    return out


async def _enumerate_distinct_buckets(
    source_repo: Any,
    group_by: str,
    scope_filters: dict[str, Any] | None,
    fetch_cap: int = 1000,
) -> tuple[list[tuple[str, str]], bool]:
    """Pull distinct group_by values from the SOURCE entity (#849, #850).

    Pre-fix the bucket list was derived from the region's first items page
    — so any group_by value that didn't happen to appear on page 1 was
    silently absent from the chart. For FK / high-cardinality columns
    that's most of them.

    Pages through the source repo (cap at ``fetch_cap`` rows) and dedupes
    on the bucket key. Reuses ``_bucket_key_label`` so FK-dict cells
    bucket on id and render on display field, matching the per-bucket
    filter semantics in ``_compute_bucketed_aggregates``.

    The source query passes ``include=[group_by]`` so FK columns come back
    as ``{id, <display_field>, ...}`` dicts (#850) — without it the repo
    serialiser drops the relation and ``_bucket_key_label`` only sees the
    raw FK UUID, producing UUID-as-label bars.

    Returns ``(buckets, succeeded)``:
      * ``succeeded=True`` — the source query ran without raising, even
        if zero rows came back. Caller must not fall back to items-page
        derivation in this case (a true empty state should render as
        no bars, not as page-1 fallback).
      * ``succeeded=False`` — the source query raised and the caller
        should fall back to items-page derivation as a last resort.
    """
    seen_keys: set[str] = set()
    out: list[tuple[str, str]] = []
    page_size = 200
    page = 1
    fetched = 0
    while fetched < fetch_cap:
        try:
            result = await source_repo.list(
                page=page,
                page_size=page_size,
                filters=scope_filters,
                include=[group_by],
            )
        except Exception:
            logger.warning(
                "Failed to enumerate distinct buckets for %s — falling back to "
                "items-page derivation",
                group_by,
                exc_info=True,
            )
            return out, False
        items = result.get("items", []) if isinstance(result, dict) else []
        if not items:
            break
        for item in items:
            it = item.model_dump() if hasattr(item, "model_dump") else dict(item)
            v = it.get(group_by)
            if v is None:
                continue
            key, label = _bucket_key_label(v)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            out.append((key, label))
        fetched += len(items)
        if len(items) < page_size:
            break
        page += 1
    return out, True


def _compute_box_plot_stats(
    items: list[dict[str, Any]],
    value_field: str,
    group_by: str | None,
    show_outliers: bool = True,
) -> list[dict[str, Any]]:
    """Compute per-group quartile statistics for the box plot display (#881).

    Returns one dict per group_by bucket (or one global bucket if
    ``group_by`` is empty), each with:
      ``label``    – the group_by value (str),
      ``n``        – sample count,
      ``min``      – minimum value,
      ``q1``       – 25th percentile (linear-interp / "type 7"),
      ``median``   – 50th percentile,
      ``q3``       – 75th percentile,
      ``max``      – maximum value,
      ``iqr``      – Q3 − Q1,
      ``whisker_low``  – furthest data point ≥ Q1 − 1.5*IQR (Tukey fence),
      ``whisker_high`` – furthest data point ≤ Q3 + 1.5*IQR,
      ``outliers`` – list of values outside the fences (empty when
                     ``show_outliers=False``).

    Uses NumPy-default linear interpolation (R "type 7" / numpy.percentile
    default) — Q at position ``(n-1)*p``, fractional positions interpolate
    linearly between adjacent order statistics. Pure stdlib; no NumPy
    needed.

    Skips items where ``value_field`` is None or non-numeric. Groups
    with ``n < 2`` are returned with degenerate stats (q1 = median = q3
    = the single value, iqr = 0, no whiskers, no outliers) so the
    template can render a single-point marker rather than crash.
    """

    def _percentile(sorted_vals: list[float], p: float) -> float:
        n = len(sorted_vals)
        if n == 1:
            return sorted_vals[0]
        pos = (n - 1) * p
        lo_idx = int(pos)
        hi_idx = min(lo_idx + 1, n - 1)
        frac = pos - lo_idx
        return sorted_vals[lo_idx] + frac * (sorted_vals[hi_idx] - sorted_vals[lo_idx])

    # Bucket values by group_by (or one global bucket if absent).
    buckets: dict[str, list[float]] = {}
    order: list[str] = []
    for item in items:
        v = item.get(value_field)
        if v is None:
            continue
        try:
            v_num = float(v)
        except (TypeError, ValueError):
            continue
        # FK columns: prefer the `{field}_display` sibling injected by
        # `_inject_display_names()` so the bucket label is the resolved
        # display name (e.g. "AO1") rather than the dict repr (#889).
        # Mirrors heatmap's resolution at lines 1058-1074.
        if not group_by:
            key = ""
        else:
            display = item.get(f"{group_by}_display")
            if display:
                key = str(display)
            else:
                key = _resolve_display_name(item.get(group_by)) or ""
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(v_num)

    stats: list[dict[str, Any]] = []
    for key in order:
        vals = sorted(buckets[key])
        n = len(vals)
        if n == 0:
            continue
        if n == 1:
            stats.append(
                {
                    "label": key,
                    "n": 1,
                    "min": vals[0],
                    "q1": vals[0],
                    "median": vals[0],
                    "q3": vals[0],
                    "max": vals[0],
                    "iqr": 0.0,
                    "whisker_low": vals[0],
                    "whisker_high": vals[0],
                    "outliers": [],
                }
            )
            continue
        q1 = _percentile(vals, 0.25)
        median = _percentile(vals, 0.5)
        q3 = _percentile(vals, 0.75)
        iqr = q3 - q1
        fence_lo = q1 - 1.5 * iqr
        fence_hi = q3 + 1.5 * iqr
        in_fence = [v for v in vals if fence_lo <= v <= fence_hi]
        whisker_low = in_fence[0] if in_fence else vals[0]
        whisker_high = in_fence[-1] if in_fence else vals[-1]
        outliers = [v for v in vals if v < fence_lo or v > fence_hi] if show_outliers else []
        stats.append(
            {
                "label": key,
                "n": n,
                "min": vals[0],
                "q1": q1,
                "median": median,
                "q3": q3,
                "max": vals[-1],
                "iqr": iqr,
                "whisker_low": whisker_low,
                "whisker_high": whisker_high,
                "outliers": outliers,
            }
        )

    return stats


def _compute_histogram_bins(
    items: list[dict[str, Any]],
    value_field: str,
    bin_count: int | None,
) -> list[dict[str, Any]]:
    """Bin numeric values from ``items`` into equal-width buckets (#882).

    Returns one dict per bin in ascending order, each with:
      ``label``    – ``"<lo>–<hi>"`` (rounded for display),
      ``count``    – number of items whose ``value_field`` falls in [lo, hi),
      ``low``      – numeric lower edge (inclusive),
      ``high``     – numeric upper edge (exclusive, except final bin which
                     is closed so the global max isn't dropped).

    ``bin_count`` semantics:
      ``None``  → Sturges' rule: ⌈log2(N) + 1⌉, clamped to [1, 50].
      ``int``   → exact bin count (caller validates ≥ 1).

    Returns ``[]`` for empty input or when no item has a numeric value at
    ``value_field`` — the template falls back to its empty-state message.
    """
    import math

    raw_values: list[float] = []
    for item in items:
        v = item.get(value_field)
        if v is None:
            continue
        try:
            raw_values.append(float(v))
        except (TypeError, ValueError):
            continue

    if not raw_values:
        return []

    lo, hi = min(raw_values), max(raw_values)
    if lo == hi:
        # Single distinct value — one degenerate bin so the chart still
        # renders something meaningful instead of a divide-by-zero.
        return [
            {"label": f"{lo:g}", "count": len(raw_values), "low": lo, "high": hi},
        ]

    if bin_count is None:
        sturges = math.ceil(math.log2(len(raw_values)) + 1) if len(raw_values) > 1 else 1
        bin_count = max(1, min(sturges, 50))

    width = (hi - lo) / bin_count
    buckets: list[dict[str, Any]] = [
        {"low": lo + i * width, "high": lo + (i + 1) * width, "count": 0} for i in range(bin_count)
    ]

    for v in raw_values:
        # Final bin is closed on the right so v == hi lands in the last
        # bucket instead of falling through.
        idx = min(int((v - lo) / width), bin_count - 1)
        buckets[idx]["count"] += 1

    for b in buckets:
        b["label"] = f"{b['low']:g}–{b['high']:g}"

    return buckets


async def _compute_bucketed_aggregates(
    aggregates: dict[str, Any],
    repositories: dict[str, Any] | None,
    group_by: Any,  # str | BucketRef
    items: list[dict[str, Any]],
    bucket_values: list[str] | None = None,
    scope_filters: dict[str, Any] | None = None,
    source_entity: str | None = None,
) -> list[dict[str, Any]]:
    """Evaluate aggregate expressions once per bucket — for bar_chart distributions.

    Used by bar_chart regions when both ``group_by`` and ``aggregates`` are
    declared. The ``current_bucket`` sentinel inside the where clause is
    substituted with each distinct group_by value before the count is
    fetched, so authors can express true distributions:

        aggregate:
          students: count(Manuscript where computed_grade = current_bucket)

    Closes #847 — previously bar_chart counted source rows per bucket and
    silently dropped the aggregate clause.

    Args:
        aggregates: Mapping of metric_name → expression. The first
            metric is the one rendered as the bar value.
        repositories: Repository registry keyed by entity name.
        group_by: Field name to bucket by.
        items: The source rows (used as a fallback bucket source when
            ``bucket_values`` is empty AND ``source_entity`` cannot be
            queried for distinct values).
        bucket_values: Pre-computed bucket list (e.g. enum values or
            state-machine states from ``kanban_columns``). When empty,
            distinct values are pulled from the source entity instead
            (#849).
        scope_filters: Scope predicates to merge into every per-bucket
            query (security gate per #574). Also applied to the
            distinct-bucket enumeration so users can't see buckets they
            wouldn't be allowed to see rows for.
        source_entity: The source entity name — used to resolve the
            source repo for distinct-bucket enumeration (#849 Bug B).
    """
    if not aggregates:
        return []

    # Per ADR-0024 the aggregates dict values are typed AggregateRef.
    # Flatten each to the (name, func, arg, where_str) tuple the
    # downstream dispatch already handles. ``arg`` is the entity name
    # for ``count(...)`` and the column name for ``avg/sum/min/max(...)``.
    # The where-clause is stringified here ONLY for the bucketed path's
    # ``current_bucket`` sentinel substitution — the fetcher paths
    # consume the typed ConditionExpr directly via Slice 2 of the
    # migration.
    from dazzle.core.ir import AggregateRef
    from dazzle.core.ir.aggregate_legacy import condition_expr_to_legacy_where

    parsed_aggs: list[tuple[str, str, str, str | None, Any]] = []
    for name, ref in aggregates.items():
        if not isinstance(ref, AggregateRef):
            continue
        arg = ref.entity or "" if ref.func == "count" else ref.column or ""
        where_str = condition_expr_to_legacy_where(ref.where)
        parsed_aggs.append((name, ref.func, arg, where_str, ref.where))
    if not parsed_aggs:
        return []

    first_name, first_func, first_arg, first_where, first_typed_where = parsed_aggs[0]
    # The "count entity" the legacy single-measure code resolved against —
    # used as the fallback for the slow per-bucket path. For multi-measure
    # the source entity drives the agg_repo (since avg/sum apply to columns
    # on that entity, not a separate entity).
    legacy_entity_name = first_arg if first_func == "count" else (source_entity or "")
    agg_repo = repositories.get(legacy_entity_name) if repositories else None
    if not agg_repo:
        return []

    # ---- Fast path: ALL aggregates against `source_entity` with no
    # current_bucket — fire them as one multi-measure GROUP BY query.
    # Originally bar-chart's count(source) case (#847–#851); generalised
    # in v0.61.32 to support multiple measures so radar / line / area can
    # render multi-series profiles (#879, #883). The slow sentinel path
    # below stays for `count(OtherEntity where ... = current_bucket)`
    # expressions that need true per-bucket queries.
    from dazzle.core.ir import BucketRef as _BucketRef

    is_bucket_ref = isinstance(group_by, _BucketRef)

    def _fast_path_eligible(
        name: str, func: str, arg: str, where: str | None, _typed: Any = None
    ) -> bool:
        if where and "current_bucket" in where:
            return False
        if func == "count":
            # count(<X>) is fast-path-eligible only when X is the source
            return source_entity is not None and arg == source_entity
        # avg/sum/min/max apply to a column on the source entity
        return func in {"sum", "avg", "min", "max"} and source_entity is not None

    all_fast = bool(parsed_aggs) and all(_fast_path_eligible(*a) for a in parsed_aggs)
    is_simple_distribution = not bucket_values and all_fast

    if is_simple_distribution or (is_bucket_ref and all_fast):
        # Build measures dict for the multi-measure GROUP BY call.
        measures: dict[str, str] = {}
        for name, func, arg, _w, _tw in parsed_aggs:
            measures[name] = "count" if func == "count" else f"{func}:{arg}"
        # When multiple aggregates share a where clause they must all be
        # the same; otherwise the fast path can't represent it. Fall back
        # to slow path if they diverge.
        unique_wheres = {w for _n, _f, _a, w, _tw in parsed_aggs}
        if len(unique_wheres) == 1:
            shared_where = next(iter(unique_wheres))
            try:
                fk_target = None
                if not is_bucket_ref:
                    fk_target = _resolve_fk_target_spec(agg_repo, group_by, repositories)
                return await _aggregate_via_groupby(
                    agg_repo,
                    measures=measures,
                    group_by=group_by,
                    where_clause=shared_where,
                    scope_filters=scope_filters,
                    source_entity_spec=getattr(agg_repo, "entity_spec", None),
                    fk_target_spec=fk_target,
                )
            except Exception:
                logger.warning(
                    "GROUP BY aggregate failed for %s.%r — falling back to N+1",
                    legacy_entity_name,
                    group_by,
                    exc_info=True,
                )
                # fall through to the old loop on exception. Time buckets have
                # no N+1 fallback — they'll just return [] below.
                if is_bucket_ref:
                    return []

    # Below this point: slow per-bucket path. Multi-measure not yet
    # supported here — only the first parsed aggregate is evaluated.
    # ``first_where`` (the legacy stringified form) is intentionally
    # dropped here — the typed ``first_typed_where`` is the canonical
    # input post-#1154.
    metric_name, func, entity_name, typed_where = (
        first_name,
        first_func,
        first_arg,
        first_typed_where,
    )
    if func != "count":
        # Slow path is count-only today; non-count aggregates that didn't
        # qualify for the fast path drop out silently.
        return []
    agg_repo = repositories.get(entity_name) if repositories else None
    if not agg_repo:
        return []

    # ---- Slow path: per-bucket loop (enumeration + per-bucket count) ----
    # Used when the aggregate expression has a current_bucket sentinel
    # against a different entity, or when callers pre-supply bucket_values.
    # buckets is a list of (key, label). key goes into the per-bucket
    # filter; label renders on the bar. For FK group_by fields the list
    # endpoint serialises rows as `{id, <display_field>, ...}` dicts —
    # the old `str(dict)` produced a Python-repr string for both, so
    # filters never matched and labels rendered as junk (#848).
    if bucket_values:
        buckets: list[tuple[str, str]] = [(str(b), str(b)) for b in bucket_values]
    else:
        # Prefer enumerating distinct values from the source entity (#849
        # Bug B) so buckets that don't appear on the region's first items
        # page still render. Items-page derivation is a last-resort
        # fallback and only fires when the source query itself raises
        # — a successful-but-empty enumeration is a true empty state and
        # must not be papered over with a page-1 derivation that would
        # show stale or wrong-scope buckets (#850).
        source_repo = repositories.get(source_entity) if (repositories and source_entity) else None
        enum_succeeded = False
        if source_repo is not None:
            buckets, enum_succeeded = await _enumerate_distinct_buckets(
                source_repo, group_by, scope_filters
            )
        else:
            buckets = []
        if not buckets and not enum_succeeded:
            seen_keys: set[str] = set()
            derived: list[tuple[str, str]] = []
            for item in items:
                v = item.get(group_by)
                if v is None:
                    continue
                key, label = _bucket_key_label(v)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                derived.append((key, label))
            buckets = derived

    if not buckets:
        return []

    has_sentinel = _condition_references_current_bucket(typed_where)

    async def _per_bucket(bucket_key: str, bucket_label: str) -> tuple[str, int]:
        # #1154: both sentinel and non-sentinel paths now use typed
        # ConditionExpr through ``_build_aggregate_filters``. The
        # sentinel substitution rebuilds the IR with the bucket key
        # bound; the bucket-key filter is then merged in as an extra
        # scope-side filter so the existing predicate compiler handles
        # both halves through the same code path. Mirrors the items
        # list call's ``include=[group_by]`` to keep #851's UUID-coercion
        # fix in scope.
        try:
            per_bucket_where = (
                _substitute_current_bucket(typed_where, bucket_key) if has_sentinel else typed_where
            )
            bucket_scope: dict[str, Any] = {**scope_filters} if scope_filters else {}
            bucket_scope[group_by] = bucket_key
            base_filters = _build_aggregate_filters(
                per_bucket_where, bucket_scope, agg_repo, entity_name
            )
            agg_result = await agg_repo.list(
                page=1,
                page_size=1,
                filters=base_filters,
                include=[group_by],
            )
            value = agg_result.get("total", 0) if isinstance(agg_result, dict) else 0
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "bucketed-aggregate %s[%s=%s] → total=%s (filters=%r)",
                    metric_name,
                    group_by,
                    bucket_key,
                    value,
                    base_filters,
                )
            return bucket_label, value
        except Exception:
            logger.warning(
                "Per-bucket query failed for %s = %s",
                group_by,
                bucket_key,
                exc_info=True,
            )
            return bucket_label, 0

    results = await asyncio.gather(
        *(_per_bucket(key, label) for key, label in buckets),
        return_exceptions=True,
    )

    out: list[dict[str, Any]] = []
    for r in results:
        if isinstance(r, BaseException):
            logger.warning("Bucketed aggregate query failed: %s", r)
            continue
        bucket_label, value = r
        # Slow path is single-measure only — mirror the fast path's
        # ``metrics`` sub-dict so multi-series templates can iterate
        # uniformly (they'll just see one entry).
        out.append(
            {
                "label": bucket_label,
                "value": value,
                "metrics": {metric_name: value},
            }
        )
    return out


# Display-field probe order for FK dicts. `name` and `title` are common
# defaults; `code` / `label` cover enum-like reference data (e.g.
# AssessmentObjective.code, GradeBoundary.label). `display_name` is the
# convention used by user-management and FK display injection (#571).
_FK_DISPLAY_FIELDS: tuple[str, ...] = (
    "display_name",
    "name",
    "title",
    "label",
    "code",
)


def _bucket_key_label(value: Any) -> tuple[str, str]:
    """Derive (filter_key, render_label) from a group_by cell value (#848).

    For FK fields the list endpoint serialises the related row as a dict
    (``{id, <display_field>, ...}``). The id is what the per-bucket
    filter needs; the display field is what should render on the bar.
    Scalars pass through with key == label.
    """
    if isinstance(value, dict):
        # Prefer 'id' as the filter key; fall back to first key with a
        # primitive value so non-id-keyed dicts still bucket sensibly.
        key = value.get("id")
        if key is None:
            for _k, v in value.items():
                if isinstance(v, str | int | float | bool):
                    key = v
                    break
        key_str = str(key) if key is not None else str(value)
        for field in _FK_DISPLAY_FIELDS:
            if field in value and value[field]:
                return key_str, str(value[field])
        return key_str, key_str
    return str(value), str(value)


def _evaluate_derived_expr(expr: Any, values: dict[str, Any]) -> float | int:
    """Evaluate a DerivedMetricExpr tree over aggregated scalar *values*.

    Division by zero yields 0 (a dashboard ratio over an empty set reads as
    0%, not an error); missing/None operands coerce to 0.
    """
    if expr.metric_name is not None:
        v = values.get(expr.metric_name)
        return v if isinstance(v, int | float) else 0
    if expr.number_literal is not None:
        literal: int | float = expr.number_literal
        return literal
    if expr.binary_op is not None:
        left = _evaluate_derived_expr(expr.binary_left, values)
        right = _evaluate_derived_expr(expr.binary_right, values)
        if expr.binary_op == "+":
            return left + right
        if expr.binary_op == "-":
            return left - right
        if expr.binary_op == "*":
            return left * right
        return left / right if right else 0
    # Function call (whitelist enforced by the IR validator).
    args = [_evaluate_derived_expr(a, values) for a in expr.function_args]
    if expr.function_name == "round":
        return round(args[0], int(args[1])) if len(args) > 1 else round(args[0])
    if expr.function_name == "abs":
        return abs(args[0])
    if expr.function_name == "nullif":
        return 0 if args[0] == args[1] else args[0]
    # coalesce — first non-zero arg (None never survives evaluation here).
    return next((a for a in args if a), 0)


def _evaluate_derived_metrics(
    aggregates: dict[str, Any],
    sync_results: dict[str, Any],
    metric_order: list[str],
) -> None:
    """Fill ``sync_results`` for DerivedMetric entries, in declaration order.

    The parser guarantees a derived metric only references names declared
    earlier in the block, so a single ordered pass resolves chains
    (a derived metric may reference another derived metric).
    """
    from dazzle.core.ir import DerivedMetric

    for name in metric_order:
        ref = aggregates.get(name)
        if isinstance(ref, DerivedMetric):
            try:
                sync_results[name] = _evaluate_derived_expr(ref.expression, sync_results)
            except Exception:  # defensive — a bad tree must not kill the dashboard
                logger.warning("Derived metric %r evaluation failed", name, exc_info=True)
                sync_results[name] = 0


async def _compute_aggregate_metrics(
    aggregates: dict[str, Any],
    repositories: dict[str, Any] | None,
    total: int,
    items: list[dict[str, Any]],
    scope_filters: dict[str, Any] | None = None,
    delta: Any | None = None,  # ir.DeltaSpec | None — see #884
    *,
    source_entity: str | None = None,  # #888 Phase 1 — for scalar aggregates
    tones: dict[str, str] | None = None,  # v0.61.65 — per-tile palette token
) -> list[dict[str, Any]]:
    """Compute aggregate metrics, batching independent DB queries concurrently.

    Per ADR-0024 the ``aggregates`` dict values are typed
    :class:`dazzle.core.ir.AggregateRef` instances — the runtime
    dispatches on ``ref.func`` / ``ref.entity`` / ``ref.column`` directly
    rather than re-parsing a string with a regex.

    When ``delta`` is set (#884), each metric also gets a prior-period value
    computed via a second aggregate query with date-range filters on
    ``delta.date_field`` (defaults to ``created_at``). The metric dict gains
    ``delta`` (current - prior), ``delta_pct``, ``delta_direction``
    (up|down|flat), ``delta_sentiment`` (positive_up|positive_down|neutral),
    and ``delta_period_label`` keys.
    """
    from dazzle.core.ir import AggregateRef

    async_tasks: list[tuple[str, Any]] = []
    sync_results: dict[str, Any] = {}
    metric_order: list[str] = []

    for metric_name, ref in aggregates.items():
        metric_order.append(metric_name)
        if not isinstance(ref, AggregateRef):
            sync_results[metric_name] = 0
            continue
        if ref.func == "count":
            entity_name = ref.entity or ""
            agg_repo = repositories.get(entity_name) if repositories else None
            if agg_repo is None:
                sync_results[metric_name] = 0
                continue
            async_tasks.append(
                (
                    metric_name,
                    _fetch_count_metric(
                        metric_name,
                        agg_repo,
                        ref.where,
                        scope_filters,
                        source_entity=entity_name,
                    ),
                )
            )
        else:
            # Scalar aggregate: needs either a column OR an L3 expression
            # (IR validator enforces exactly-one).  Cross-entity
            # (ref.entity is not None) routes to that entity's repo —
            # the shape that was unrepresentable in the regex grammar
            # pre-ADR-0024. #1152 adds the expression branch for
            # arithmetic / casts / function calls inside the aggregate.
            if ref.column is None and ref.expression is None:
                sync_results[metric_name] = 0
                continue
            agg_entity = ref.entity if ref.entity is not None else source_entity
            if agg_entity is None:
                sync_results[metric_name] = 0
                continue
            agg_repo = repositories.get(agg_entity) if repositories else None
            if agg_repo is None:
                sync_results[metric_name] = 0
                continue
            async_tasks.append(
                (
                    metric_name,
                    _fetch_scalar_metric(
                        metric_name,
                        ref.func,
                        ref.column,
                        agg_repo,
                        ref.where,
                        scope_filters,
                        source_entity=agg_entity,
                        expression=ref.expression,
                        expression_alias=ref.entity,
                    ),
                )
            )

    # Fire all async queries concurrently
    if async_tasks:
        results = await asyncio.gather(*(coro for _, coro in async_tasks), return_exceptions=True)
        for result in results:
            if isinstance(result, tuple):
                sync_results[result[0]] = result[1]
            elif isinstance(result, BaseException):
                logger.warning("Aggregate metric query failed: %s", result)

    # #1359: derived metrics — Python arithmetic over the aggregated scalars,
    # evaluated in declaration order AFTER all queries resolved. Zero extra
    # queries; scope filters already applied pre-aggregation, so the
    # one-query-per-chart scope-safety contract is untouched.
    _evaluate_derived_metrics(aggregates, sync_results, metric_order)

    # Build output in original order. v0.61.65: attach per-tile `tone` from
    # the region-level `tones:` map when the metric name has an entry. The
    # template branches on `metric.tone` to apply a palette tint.
    _tones = tones or {}
    built_metrics = [
        {
            "label": name.replace("_", " ").title(),
            "value": sync_results.get(name, 0),
            **({"tone": _tones[name]} if name in _tones else {}),
        }
        for name in metric_order
    ]

    # v0.61.25 (#884): period-over-period delta. For each count() metric,
    # fire a second aggregate over the prior window so the template can
    # render the trend arrow + comparison line.
    if delta is not None and aggregates and repositories:
        from datetime import datetime, timedelta

        period = timedelta(seconds=delta.period_seconds)
        now = datetime.now(_dt.UTC)
        prior_start = now - 2 * period
        prior_end = now - period
        date_field = delta.date_field or "created_at"

        prior_tasks: list[Any] = []
        prior_metric_names: list[str] = []
        for metric_name, ref in aggregates.items():
            if not isinstance(ref, AggregateRef) or ref.func != "count":
                continue
            entity_name = ref.entity or ""
            agg_repo = repositories.get(entity_name)
            if not agg_repo:
                continue
            # Prior-period delta: AND-compose the typed where with the
            # date-window filter via _build_aggregate_filters, which
            # routes the ConditionExpr through compile_predicate.
            prior_window = {
                f"{date_field}__gte": prior_start.isoformat(),
                f"{date_field}__lt": prior_end.isoformat(),
            }
            if scope_filters:
                prior_window = {**scope_filters, **prior_window}
            prior_tasks.append(
                _fetch_count_metric(
                    metric_name,
                    agg_repo,
                    ref.where,
                    prior_window,
                    source_entity=entity_name,
                )
            )
            prior_metric_names.append(metric_name)

        prior_map: dict[str, Any] = {}
        if prior_tasks:
            prior_results = await asyncio.gather(*prior_tasks, return_exceptions=True)
            for result in prior_results:
                if isinstance(result, tuple):
                    prior_map[result[0]] = result[1]

        for metric_name, m in zip(metric_order, built_metrics, strict=False):
            if metric_name not in prior_map:
                continue
            try:
                current_val = float(m["value"])
                prior_val = float(prior_map[metric_name])
            except (TypeError, ValueError):
                continue
            delta_val = current_val - prior_val
            pct = (delta_val / prior_val * 100.0) if prior_val else 0.0
            direction = "up" if delta_val > 0 else ("down" if delta_val < 0 else "flat")
            m["delta"] = int(delta_val) if delta_val == int(delta_val) else round(delta_val, 2)
            m["delta_pct"] = round(pct, 1)
            m["delta_direction"] = direction
            m["delta_sentiment"] = delta.sentiment
            m["delta_period_label"] = delta.period_label

    return built_metrics


def _parse_simple_where(where_clause: str) -> dict[str, Any]:
    """Parse simple WHERE clause to repository filter dict.

    Supports: ``field = value``, ``field != value``, ``field > value``, etc.
    Multiple conditions joined with ``and``.
    """
    filters: dict[str, Any] = {}
    parts = [p.strip() for p in where_clause.split(" and ")]
    for part in parts:
        for op, suffix in [
            ("!=", "__ne"),
            (">=", "__gte"),
            ("<=", "__lte"),
            (">", "__gt"),
            ("<", "__lt"),
            ("=", ""),
        ]:
            if op in part:
                field, value = [x.strip() for x in part.split(op, 1)]
                key = f"{field}{suffix}" if suffix else field
                filters[key] = value
                break
    return filters
