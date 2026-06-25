"""Pure leaf data builders for non-trivial display modes.

Extracted from _workspace_region_handler in #1057 cut 7 (v0.67.106).
Each function here takes already-fetched ``items`` plus the relevant
slice of region config and returns a structured data shape ready
for the typed-primitive renderer to consume. No I/O, no DB, no IR
dispatch — pure data transforms.

These started life as inline blocks inside the 1,455-line
``_workspace_region_handler`` dispatcher. Pulling them out shrinks
the dispatcher and makes each compute independently testable.
"""

import math
from typing import Any

from dazzle.core.condition_eval import evaluate_condition as _eval_vis
from dazzle.core.ir import AggregateRef
from dazzle.core.ir.workspaces import ComparisonOutlierSpec
from dazzle.core.strings import to_api_plural
from dazzle.http.runtime.workspace_card_data import (
    _apply_format_spec,
    _initials_from,
    _interpolate_card_template,
    _resolve_path,
)
from dazzle.render.display_names import _resolve_display_name
from dazzle.render.fragment.outliers import Flag, flag_outliers


def _coerce_float(value: Any) -> float | None:
    """Best-effort float coercion; None and unparseable values → None."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_comparison_rows(
    records: list[dict[str, Any]],
    *,
    label_key: str,
    value_key: str,
    order: str,
    outlier_spec: ComparisonOutlierSpec,
    extra_keys: list[str],
) -> tuple[list[dict[str, Any]], float]:
    """Rank ``records`` by ``value_key`` and flag outliers — the comparison spine (#1470).

    Pure: runs AFTER the scope-safe fetch, so it never widens scope. Sorts by
    value (``None`` always last regardless of ``order``), assigns ranks 1..N,
    computes ``bar_fraction = value / max`` clamped to [0, 1], and attaches the
    per-row outlier flag from :func:`flag_outliers`. Returns ``(rows, max)``
    where ``max`` is the largest numeric value (``0.0`` when none).
    """
    if not records:
        return [], 0.0

    enriched = [(rec, _coerce_float(rec.get(value_key))) for rec in records]
    non_none = [pair for pair in enriched if pair[1] is not None]
    nones = [pair for pair in enriched if pair[1] is None]
    non_none.sort(key=lambda pair: pair[1], reverse=order != "asc")  # type: ignore[arg-type,return-value]
    ordered = non_none + nones

    values = [v for _rec, v in ordered]
    max_value = max((v for v in values if v is not None), default=0.0)
    denom = max_value if max_value > 0 else 1.0
    flags = flag_outliers(values, outlier_spec)

    rows: list[dict[str, Any]] = []
    for rank, ((rec, value), flag) in enumerate(zip(ordered, flags, strict=True), start=1):
        fraction = max(0.0, min(1.0, value / denom)) if value is not None else 0.0
        rows.append(
            {
                "rank": rank,
                "label": str(rec.get(label_key, "") or ""),
                "value": value,
                "bar_fraction": fraction,
                "columns": {k: rec.get(k) for k in extra_keys},
                "outlier": flag,
            }
        )
    return rows, max_value


def build_comparison_inputs(
    *,
    group_by: Any,
    bucketed_metrics: list[dict[str, Any]],
    items: list[dict[str, Any]],
    columns: list[dict[str, Any]],
    rank_by: str,
    order: str,
    outlier_spec: ComparisonOutlierSpec,
) -> tuple[list[dict[str, Any]], float]:
    """Select the comparison data source by mode, then rank (#1470).

    Group mode (``group_by`` + buckets): rank by the named aggregate, pulling it
    from each bucket's ``metrics`` (falling back to the primary ``value``).
    Entity-row mode: rank the scoped list ``items`` by the numeric ``rank_by``
    field, labelling by the first non-metric column and surfacing the remaining
    columns as ``columns``.
    """
    if group_by and bucketed_metrics:
        records = [
            {
                "label": b.get("label"),
                rank_by: (b.get("metrics") or {}).get(rank_by, b.get("value")),
            }
            for b in bucketed_metrics
        ]
        return build_comparison_rows(
            records,
            label_key="label",
            value_key=rank_by,
            order=order,
            outlier_spec=outlier_spec,
            extra_keys=[],
        )

    col_keys = [str(k) for c in columns if (k := c.get("key"))]
    label_key = next((k for k in col_keys if k != rank_by), "id")
    extra_keys = [k for k in col_keys if k not in (label_key, rank_by)]
    return build_comparison_rows(
        items,
        label_key=label_key,
        value_key=rank_by,
        order=order,
        outlier_spec=outlier_spec,
        extra_keys=extra_keys,
    )


def build_outlier_flags(
    items: list[dict[str, Any]], *, column: str, spec: ComparisonOutlierSpec
) -> list[Flag | None]:
    """Per-row outlier flag for one column, index-aligned to ``items`` (#1470).

    Reads ``column`` from each item, coercing non-numeric / non-finite / None to
    None (excluded from the distribution and never flagged), then runs the shared
    ``flag_outliers`` pass. Pure: runs after the scoped fetch, never widens scope.
    """
    values: list[float | None] = []
    for item in items:
        raw = item.get(column) if isinstance(item, dict) else None
        v = _coerce_float(raw)
        values.append(v if v is not None and math.isfinite(v) else None)
    return flag_outliers(values, spec)


def compute_heatmap(
    items: list[dict[str, Any]],
    rows_field: str,
    cols_field: str,
    value_field: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Build (matrix, col_values) for a HEATMAP region.

    Reads ``items`` (already resolved with ``_inject_display_names``)
    and pivots them on the given row/column/value fields. Returns:
    - matrix: ``[{"row": label, "row_id": id, "cells": [{"value", "column"}, ...]}, ...]``
    - col_values: sorted list of distinct column labels.

    Empty inputs return ``([], [])``. The row_id resolution mirrors
    #633: when the FK is a dict use its ``id``; when it's a UUID
    string, treat it as the target entity ID; otherwise fall back
    to the source item's id.
    """
    if not items:
        return [], []

    col_set: set[str] = set()
    for item in items:
        cv = str(item.get(f"{cols_field}_display", "")) or _resolve_display_name(
            item.get(cols_field, "")
        )
        if cv:
            col_set.add(cv)
    col_values = sorted(col_set)

    row_map: dict[str, dict[str, float]] = {}
    row_ids: dict[str, str] = {}
    for item in items:
        rv = str(item.get(f"{rows_field}_display", "")) or _resolve_display_name(
            item.get(rows_field, "")
        )
        cv = str(item.get(f"{cols_field}_display", "")) or _resolve_display_name(
            item.get(cols_field, "")
        )
        val = float(item.get(value_field, 0) or 0)
        if rv not in row_map:
            row_map[rv] = {}
        row_map[rv][cv] = val
        raw_row = item.get(rows_field)
        if isinstance(raw_row, dict):
            row_id = str(raw_row.get("id", ""))
        elif raw_row:
            row_id = str(raw_row)
        else:
            row_id = str(item.get("id", ""))
        row_ids[rv] = row_id

    matrix: list[dict[str, Any]] = []
    for row_label in sorted(row_map.keys()):
        cells: list[dict[str, Any]] = []
        for col_label in col_values:
            cell_val = row_map[row_label].get(col_label, 0.0)
            cells.append({"value": cell_val, "column": col_label})
        matrix.append({"row": row_label, "row_id": row_ids.get(row_label, ""), "cells": cells})
    return matrix, col_values


def compute_progress(
    items: list[dict[str, Any]],
    stages_list: list[str],
    complete_at: str,
    status_field: str,
) -> dict[str, Any]:
    """Build progress-counter dict for a PROGRESS region (v0.44.0).

    Counts ``items`` per stage and computes completion percentage.
    Returns:
        {
          "stage_counts": [{"name", "count", "complete"}, ...],
          "total": int,
          "complete_count": int,
          "complete_pct": float,
        }

    Empty stages_list returns a zeroed shape.
    """
    if not stages_list:
        return {"stage_counts": [], "total": 0, "complete_count": 0, "complete_pct": 0.0}

    stage_counter: dict[str, int] = dict.fromkeys(stages_list, 0)
    for item in items:
        item_stage = str(item.get(status_field, ""))
        if item_stage in stage_counter:
            stage_counter[item_stage] += 1
    total = sum(stage_counter.values())

    complete_idx = stages_list.index(complete_at) if complete_at in stages_list else -1
    stage_counts: list[dict[str, Any]] = []
    complete_count = 0
    for i, stage_name in enumerate(stages_list):
        cnt = stage_counter.get(stage_name, 0)
        is_complete = complete_idx >= 0 and i >= complete_idx
        stage_counts.append({"name": stage_name, "count": cnt, "complete": is_complete})
        if is_complete:
            complete_count += cnt

    complete_pct = round(complete_count / total * 100, 1) if total > 0 else 0.0
    return {
        "stage_counts": stage_counts,
        "total": total,
        "complete_count": complete_count,
        "complete_pct": complete_pct,
    }


def compute_tree(
    items: list[dict[str, Any]],
    parent_field: str,
) -> list[dict[str, Any]]:
    """Build a tree of items by walking each item's ``parent_field``
    against the set of item ids (#565).

    Items whose parent is not in the set become roots. Each node gets
    a mutated ``_children`` key with the recursively-built subtree.
    Returns the list of root nodes.
    """
    items_by_id = {str(item.get("id", "")): item for item in items}
    children_map: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        parent_id = str(item.get(parent_field, "") or "")
        children_map.setdefault(parent_id, []).append(item)

    roots = [item for item in items if str(item.get(parent_field, "") or "") not in items_by_id]

    def _build_subtree(node: dict[str, Any]) -> dict[str, Any]:
        node_id = str(node.get("id", ""))
        node["_children"] = children_map.get(node_id, [])
        for child in node["_children"]:
            _build_subtree(child)
        return node

    return [_build_subtree(r) for r in roots]


def compute_queue(
    entity_spec: Any,
    source_name: str,
) -> tuple[list[dict[str, str]], str, str]:
    """Build (transitions, status_field, api_endpoint) for a QUEUE region.

    Reads the entity's state-machine transitions and emits one
    transition dict per distinct ``to_state`` (first-occurrence wins
    on the order they appear in the IR — preserves the curated order
    DSL authors expect).
    """
    transitions: list[dict[str, str]] = []
    status_field = ""
    if entity_spec is None:
        return transitions, status_field, ""

    sm = entity_spec.state_machine
    if sm:
        status_field = sm.status_field
        seen: set[str] = set()
        for t in sm.transitions:
            to_state = t.to_state if isinstance(t.to_state, str) else str(t.to_state)
            if to_state not in seen:
                seen.add(to_state)
                transitions.append(
                    {
                        "to_state": to_state,
                        "label": to_state.replace("_", " ").title(),
                    }
                )

    api_endpoint = f"/{to_api_plural(source_name)}"
    return transitions, status_field, api_endpoint


def compute_bullet(
    items: list[dict[str, Any]],
    label_field: str | None,
    actual_field: str | None,
    target_field: str | None,
    reference_bands: list[Any] | None,
) -> tuple[list[dict[str, Any]], float]:
    """Build (rows, max_value) for a BULLET region.

    Each row carries label/actual/target. The shared max scale is
    the largest of all actuals, targets, and reference-band upper
    extents so out-of-range values still fit on the canvas.
    """
    rows: list[dict[str, Any]] = []
    if not (label_field and actual_field):
        return rows, 0.0

    for item in items:
        actual_raw = item.get(actual_field)
        if actual_raw is None:
            continue
        try:
            actual = float(actual_raw)
        except (TypeError, ValueError):
            continue
        target: float | None = None
        if target_field:
            target_raw = item.get(target_field)
            if target_raw is not None:
                try:
                    target = float(target_raw)
                except (TypeError, ValueError):
                    target = None
        rows.append(
            {
                "label": str(item.get(label_field, "") or ""),
                "actual": actual,
                "target": target,
            }
        )

    scale_candidates: list[float] = [r["actual"] for r in rows]
    scale_candidates.extend(r["target"] for r in rows if r["target"] is not None)
    scale_candidates.extend(getattr(b, "to_value", 0.0) for b in (reference_bands or []))
    max_value = max(scale_candidates) if scale_candidates else 0.0
    return rows, max_value


def compute_bar_track(
    bucketed_metrics: list[dict[str, Any]],
    explicit_max: float | None,
    format_spec: str,
    region_name: str,
) -> tuple[list[dict[str, Any]], float]:
    """Build (rows, max) for a BAR_TRACK region.

    Each bucket becomes a row with label / value / fill_pct /
    formatted_value. The fill_pct is clamped to [0, 100]. When
    explicit_max is None, the auto-max is the largest bucket value
    (falling back to 1.0 to avoid div-by-zero).

    Accepts both str.format-template syntax (``"{:.0%}"``) and bare
    format-spec syntax (``".0%"``); detects by looking for ``{``.
    Malformed format specs fall back to raw str + a logger warning
    (the dashboard doesn't crash on author error) — see
    ``workspace_card_data._apply_format_spec`` (shared with cohort_strip
    aggregate lenses, #1300).
    """
    rows: list[dict[str, Any]] = []
    if not bucketed_metrics:
        return rows, 0.0

    values: list[float] = []
    for bucket in bucketed_metrics:
        try:
            values.append(float(bucket.get("value") or 0))
        except (TypeError, ValueError):
            values.append(0.0)

    max_value = (
        float(explicit_max)
        if explicit_max is not None
        else (max(values) if values and max(values) > 0 else 1.0)
    )

    for bucket, value in zip(bucketed_metrics, values, strict=True):
        fill_pct = max(0.0, min(100.0, (value / max_value) * 100.0)) if max_value else 0.0
        # #1300: shared format helper (was an inline try/except here). Same
        # behaviour — empty spec → str, invalid spec → warn + raw value.
        formatted = _apply_format_spec(
            value, format_spec, context=f"bar_track region {region_name!r}"
        )
        rows.append(
            {
                "label": str(bucket.get("label") or ""),
                "value": value,
                "fill_pct": fill_pct,
                "formatted_value": formatted,
            }
        )
    return rows, max_value


def compute_profile_card(
    items: list[dict[str, Any]],
    ctx_region: Any,
) -> dict[str, Any]:
    """Build the profile_card payload dict (#892).

    Reads the first item (callers narrow via ``filter:`` to one
    record), then resolves the avatar/primary/secondary/stats/facts
    fields. The secondary + fact templates support tiny
    ``{{ field }}`` / ``{{ field.path }}`` interpolation via
    ``_interpolate_card_template`` — logic-less, no Jinja eval.

    Empty items returns an empty dict — caller treats this as
    "render the empty: message".
    """
    if not items:
        return {}
    item = items[0]
    avatar_field = ctx_region.avatar_field
    primary_field = ctx_region.primary
    secondary_tmpl = ctx_region.secondary
    stats_specs = ctx_region.profile_stats or []
    fact_tmpls = ctx_region.facts or []

    avatar_url = str(_resolve_path(item, avatar_field) or "") if avatar_field else ""
    primary_str = str(_resolve_path(item, primary_field) or "") if primary_field else ""
    initials = _initials_from(primary_str)

    return {
        "avatar_url": avatar_url,
        "initials": initials,
        "primary": primary_str,
        "secondary": _interpolate_card_template(secondary_tmpl or "", item),
        "stats": [
            {
                "label": stat["label"],
                "value": str(_resolve_path(item, stat["value"]) or ""),
            }
            for stat in stats_specs
        ],
        "facts": [_interpolate_card_template(fact, item) for fact in fact_tmpls],
    }


def compute_confirm_action_state(
    items: list[dict[str, Any]],
    state_field: str | None,
) -> str:
    """Read state_value from the first fetched item for a
    CONFIRM_ACTION_PANEL region (v0.61.72, #6).

    Empty string when no field configured or no item — caller falls
    through to the safe default ("off").
    """
    if not (state_field and items):
        return ""
    return str(_resolve_path(items[0], state_field) or "")


async def compute_action_grid(
    cards: list[dict[str, Any]],
    repositories: dict[str, Any] | None,
    source_entity: str,
    scope_only_filters: dict[str, Any] | None,
    scope_denied: bool,
) -> list[dict[str, Any]]:
    """Build action-card payloads with optional aggregate counts (#891).

    Each card carries label/icon/url/tone (already resolved at context
    build time) plus an optional ``count`` :class:`AggregateRef`. When
    set with a ``count`` func and a resolvable entity, fires one
    ``_fetch_count_metric`` per card concurrently via ``asyncio.gather``.
    Cross-entity counts run unscoped with a warning (#901). When
    ``scope_denied`` is True, all cards render without counts.

    Per ADR-0024 the aggregate is a typed IR object, not a string —
    no regex dispatch.
    """
    import asyncio as _asyncio
    import logging

    from dazzle.http.runtime.workspace_aggregation import _fetch_count_metric

    logger = logging.getLogger(__name__)
    out: list[dict[str, Any]] = []

    if not cards:
        return out

    if scope_denied:
        for card in cards:
            out.append(
                {
                    "label": card.get("label", ""),
                    "icon": card.get("icon", ""),
                    "url": card.get("url", ""),
                    "tone": card.get("tone", "neutral"),
                    "count": None,
                }
            )
        return out

    count_tasks: list[Any] = []
    count_indices: list[int] = []
    for idx, card in enumerate(cards):
        count_ref = card.get("count")
        # Only count() with a resolvable entity drives a badge — scalar
        # aggregates on action cards have no defined render path yet.
        if not isinstance(count_ref, AggregateRef) or count_ref.func != "count":
            continue
        entity_name = count_ref.entity
        if not entity_name:
            continue
        agg_repo = repositories.get(entity_name) if repositories else None
        if agg_repo is None:
            continue
        card_scope = scope_only_filters if entity_name == source_entity else None
        if card_scope is None and scope_only_filters is not None:
            logger.warning(
                "action_grid card %d (entity=%s, source=%s): cross-entity "
                "count is unscoped — destination entity's own RBAC at "
                "navigation time still applies, but the count badge "
                "shows ALL rows the runtime can read",
                idx,
                entity_name,
                source_entity,
            )
        count_tasks.append(
            _fetch_count_metric(
                f"action_card_{idx}",
                agg_repo,
                count_ref.where,
                card_scope,
                source_entity=entity_name,
            )
        )
        count_indices.append(idx)

    count_results: dict[int, Any] = {}
    if count_tasks:
        results = await _asyncio.gather(*count_tasks, return_exceptions=True)
        for ridx, rresult in zip(count_indices, results, strict=True):
            if isinstance(rresult, tuple):
                count_results[ridx] = rresult[1]
            else:
                logger.warning("action_grid card %d count query failed: %s", ridx, rresult)

    for idx, card in enumerate(cards):
        out.append(
            {
                "label": card.get("label", ""),
                "icon": card.get("icon", ""),
                "url": card.get("url", ""),
                "tone": card.get("tone", "neutral"),
                "count": count_results.get(idx),
            }
        )
    return out


async def compute_pipeline_steps(
    stages: list[dict[str, Any]],
    repositories: dict[str, Any] | None,
    source_entity: str,
    scope_only_filters: dict[str, Any] | None,
    scope_denied: bool,
) -> list[dict[str, Any]]:
    """Build pipeline-stage data with aggregate value/progress per stage (#890).

    Each stage's ``value`` and ``progress`` fields are a discriminated
    union (ADR-0024): a typed :class:`AggregateRef` (fires a count
    query) OR a literal string (renders verbatim — v0.61.66 #4).
    ``None`` means the field was omitted.

    Cross-entity aggregates run unscoped with a warning (#901). When
    ``scope_denied`` is True, aggregate stages render without values
    but literals are preserved.
    """
    import asyncio as _asyncio
    import logging

    from dazzle.http.runtime.workspace_aggregation import _fetch_count_metric
    from dazzle.http.runtime.workspace_card_data import _coerce_pipeline_progress

    logger = logging.getLogger(__name__)
    out: list[dict[str, Any]] = []

    if not stages:
        return out

    if scope_denied:
        for stage in stages:
            val = stage.get("value")
            prog_val = stage.get("progress")
            # Literal strings preserve; AggregateRef renders as None.
            value_out = val if isinstance(val, str) else None
            prog_raw = prog_val if isinstance(prog_val, str) else None
            prog_clamped, prog_overshoot = _coerce_pipeline_progress(prog_raw)
            out.append(
                {
                    "label": stage.get("label", ""),
                    "caption": stage.get("caption", ""),
                    "value": value_out,
                    "progress": prog_clamped,
                    "progress_overshoot": prog_overshoot,
                }
            )
        return out

    stage_tasks: list[Any] = []
    stage_task_keys: list[tuple[int, str]] = []
    stage_literals: dict[tuple[int, str], str] = {}

    def queue_stage_field(sidx: int, field: str, payload: Any) -> None:
        # Three shapes per ADR-0024:
        #   - None      → field omitted, nothing to do
        #   - str       → literal, render verbatim
        #   - AggregateRef → fire a query (count only for now)
        if payload is None:
            return
        if isinstance(payload, str):
            if payload:
                stage_literals[(sidx, field)] = payload
            return
        if not isinstance(payload, AggregateRef) or payload.func != "count":
            return
        entity_name = payload.entity
        if not entity_name:
            return
        agg_repo = repositories.get(entity_name) if repositories else None
        if agg_repo is None:
            return
        stage_scope = scope_only_filters if entity_name == source_entity else None
        if stage_scope is None and scope_only_filters is not None:
            logger.warning(
                "pipeline_steps stage %d %s (entity=%s, source=%s): "
                "cross-entity count is unscoped — destination entity's "
                "own RBAC at navigation time still applies, but the "
                "stage %s shows ALL rows the runtime can read",
                sidx,
                field,
                entity_name,
                source_entity,
                field,
            )
        stage_tasks.append(
            _fetch_count_metric(
                f"pipeline_stage_{sidx}_{field}",
                agg_repo,
                payload.where,
                stage_scope,
                source_entity=entity_name,
            )
        )
        stage_task_keys.append((sidx, field))

    for sidx, stage in enumerate(stages):
        queue_stage_field(sidx, "value", stage.get("value"))
        queue_stage_field(sidx, "progress", stage.get("progress"))

    stage_results: dict[tuple[int, str], Any] = {}
    if stage_tasks:
        sresults = await _asyncio.gather(*stage_tasks, return_exceptions=True)
        for key, srresult in zip(stage_task_keys, sresults, strict=True):
            if isinstance(srresult, tuple):
                stage_results[key] = srresult[1]
            else:
                logger.warning(
                    "pipeline_steps stage %d %s query failed: %s",
                    key[0],
                    key[1],
                    srresult,
                )

    for sidx, stage in enumerate(stages):
        resolved_val: Any = stage_literals.get((sidx, "value"), stage_results.get((sidx, "value")))
        prog_raw_resolved: Any = stage_literals.get(
            (sidx, "progress"), stage_results.get((sidx, "progress"))
        )
        prog_clamped, prog_overshoot = _coerce_pipeline_progress(prog_raw_resolved)
        out.append(
            {
                "label": stage.get("label", ""),
                "caption": stage.get("caption", ""),
                "value": resolved_val,
                "progress": prog_clamped,
                "progress_overshoot": prog_overshoot,
            }
        )
    return out


async def compute_cohort_aggregate_primary(
    *,
    items: list[dict[str, Any]],
    lens: Any,  # CohortStripLens with primary_aggregate
    source_entity: str,
    repositories: dict[str, Any] | None,
    scope_only_filters: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compute per-member aggregate values for a cohort_strip primary_aggregate lens.

    Batched (#1153): one ``Repository.aggregate`` GROUP BY query for the
    whole cohort. The no-via case adds a ``Dimension`` on the FK column
    so each result row carries its member id; the via-junction case
    runs a bespoke ``JOIN`` query because the GROUP BY column lives on
    the junction, not the aggregated entity.

    Three link strategies:
      - Without ``via:`` or ``share:`` — direct FK from aggregated
        entity → source entity. Batched as ``GROUP BY aggregated.<fk_col>``
        with ``aggregated.<fk_col> IN (...member_ids)``.
      - With ``via:`` — true-junction subquery (junction has a direct
        FK to aggregated). Batched as a JOIN through the junction
        with ``GROUP BY junction.<member_binding_col>``.
      - With ``share:`` (#1216) — shared-parent JOIN. Cohort source row
        and aggregated row both FK to the named pivot entity; the JOIN
        composes ``a.<agg_to_pivot_fk> = s.<source_to_pivot_fk>``,
        grouped by ``s.id``. Refuses at compute time when either side
        has zero or multiple ``ref <pivot>`` fields (no silent guessing).

    Args:
        items: Cohort source rows (already RBAC-scoped upstream).
        lens: The active :class:`CohortStripLens` carrying
            ``primary_aggregate``.
        source_entity: Name of the cohort source entity (used to
            resolve the FK from aggregated entity → source).
        repositories: Repository registry keyed by entity name.
        scope_only_filters: Source-entity scope filters (applied to
            the *aggregated* entity only when ``ref.entity ==
            source_entity``; for cross-entity aggregates the
            aggregated entity's RBAC must be composed separately —
            phase 3).

    Returns:
        Mapping of cohort member id → aggregate value. Members whose
        query failed or returned no rows are absent from the mapping
        (the cell renders without a value).
    """
    import logging

    logger = logging.getLogger(__name__)
    out: dict[str, Any] = {}

    primary_aggregate = getattr(lens, "primary_aggregate", None)
    if primary_aggregate is None:
        return out
    ref = primary_aggregate.aggregate
    if not isinstance(ref, AggregateRef):
        return out

    # Resolve the aggregated entity's repository. Cross-entity scalars
    # (ref.entity set) and source-relative scalars (ref.entity is None)
    # both supported.
    aggregated_entity = ref.entity if ref.entity is not None else source_entity
    if not repositories or aggregated_entity not in repositories:
        return out
    agg_repo = repositories[aggregated_entity]

    # Two link strategies, in priority order (#1144 Gap 1 phases 2-3):
    #   - With `via:` set → junction-binding subquery (phase 3, this slice).
    #     The cohort member's id is substituted as a literal parameter into
    #     the junction WHERE clause.
    #   - Without `via:` → direct FK from aggregated entity → source entity
    #     (phase 2). Per-member filter is `aggregated_entity.<fk> = member_id`.
    via = primary_aggregate.via
    share_entity = getattr(primary_aggregate, "share", None)
    junction_repo = repositories.get(via.junction_entity) if (via and repositories) else None
    via_link: tuple[str, str, str] | None = None  # (subq_select_field, agg_filter_col, direction)
    share_link: tuple[str, str] | None = None  # (agg_to_pivot_fk, source_to_pivot_fk)
    if share_entity is not None:
        # #1216: shared-parent JOIN. Cohort source row and the
        # aggregated row both reference the named pivot. We refuse to
        # silently pick a FK when there's more than one candidate —
        # better empty cells + a clear warning than silently-wrong
        # SQL. (`share:` and `via:` are mutually exclusive at parse
        # time, so we never hit both branches.)
        source_repo = repositories.get(source_entity)
        if source_repo is None:
            logger.warning(
                "cohort_strip lens %r: share=%r set but source entity %r not in repositories",
                getattr(lens, "id", "<unknown>"),
                share_entity,
                source_entity,
            )
            return out
        agg_pivot_fks = _all_fks_to(agg_repo, share_entity)
        source_pivot_fks = _all_fks_to(source_repo, share_entity)
        if not agg_pivot_fks or not source_pivot_fks:
            logger.warning(
                "cohort_strip lens %r: share=%r not reachable — "
                "aggregated %r FKs→pivot=%r, source %r FKs→pivot=%r. "
                "Both entities must declare a `ref %s` field.",
                getattr(lens, "id", "<unknown>"),
                share_entity,
                aggregated_entity,
                agg_pivot_fks or "none",
                source_entity,
                source_pivot_fks or "none",
                share_entity,
            )
            return out
        if len(agg_pivot_fks) > 1 or len(source_pivot_fks) > 1:
            logger.warning(
                "cohort_strip lens %r: share=%r is ambiguous — "
                "aggregated %r has %d FKs to %r (%s); source %r has %d (%s). "
                "Multiple candidate FKs to the pivot are not yet supported; "
                "rename one or split the entity.",
                getattr(lens, "id", "<unknown>"),
                share_entity,
                aggregated_entity,
                len(agg_pivot_fks),
                share_entity,
                ",".join(agg_pivot_fks),
                source_entity,
                len(source_pivot_fks),
                ",".join(source_pivot_fks),
            )
            return out
        share_link = (agg_pivot_fks[0], source_pivot_fks[0])
        fk_col = None
    elif via is not None:
        if junction_repo is None:
            logger.warning(
                "cohort_strip lens %r: junction entity %r not in repositories — "
                "cells will render without a value.",
                getattr(lens, "id", "<unknown>"),
                via.junction_entity,
            )
            return out
        via_link = _resolve_via_link_direction(agg_repo, junction_repo, via.junction_entity)
        if via_link is None:
            logger.warning(
                "cohort_strip lens %r: no FK between aggregated entity %r and "
                "junction %r — declare a direct reference, set `share:` "
                "(shared-parent JOIN), or use the no-via case. "
                "Cells will render without a value.",
                getattr(lens, "id", "<unknown>"),
                aggregated_entity,
                via.junction_entity,
            )
            return out
        fk_col = None
    else:
        fk_col = _find_fk_to(agg_repo, source_entity)
        if fk_col is None:
            logger.warning(
                "cohort_strip lens %r: aggregated entity %r has no FK to "
                "source entity %r — per-member filtering not possible. "
                "Cells will render without a value.",
                getattr(lens, "id", "<unknown>"),
                aggregated_entity,
                source_entity,
            )
            return out

    # Build the shared measure spec.
    # L3 (#1152): when the AggregateRef carries an ``expression`` the
    # measure spec uses the outer aggregate func name and pairs it with
    # a precompiled SQL fragment in ``measure_expressions``. The runtime
    # builder slots the fragment into ``<FUNC>(<fragment>)`` and binds
    # the inner parameters ahead of the WHERE-clause ones.
    measure_expressions: dict[str, tuple[str, list[Any]]] | None = None
    if ref.func == "count":
        measures = {"primary": "count"}
    elif ref.expression is not None:
        from dazzle.http.runtime.aggregate_expression import (
            compile_aggregate_expression,
        )

        # Cross-entity expressions take the aggregated entity's table
        # as the implicit alias; source-relative ones pass None so the
        # column refs stay unqualified.
        alias: str | None = ref.entity
        expr_sql, expr_params = compile_aggregate_expression(
            ref.expression,
            placeholder=agg_repo.db.placeholder,
            table_alias=alias,
        )
        measures = {"primary": ref.func}
        measure_expressions = {"primary": (expr_sql, expr_params)}
    else:
        measures = {"primary": f"{ref.func}:{ref.column}"}

    member_ids: list[str] = []
    for item in items:
        # Cohort member key — uses the source row's `id` field, matching
        # the `_build_cohort_cells` resolution.
        mid = str(item.get("id", "") or "")
        if mid:
            member_ids.append(mid)
    if not member_ids:
        return out

    try:
        if share_link is not None:
            assert repositories is not None  # narrowed by the share branch above
            return await _batched_share_cohort_aggregate(
                agg_repo=agg_repo,
                source_repo=repositories[source_entity],
                share_link=share_link,
                aggregated_entity=aggregated_entity,
                member_ids=member_ids,
                measures=measures,
                measure_expressions=measure_expressions,
                where=ref.where,
                scope_filters=scope_only_filters,
            )
        if via_link is not None and via is not None:
            return await _batched_via_cohort_aggregate(
                agg_repo=agg_repo,
                via=via,
                via_link=via_link,
                aggregated_entity=aggregated_entity,
                member_ids=member_ids,
                measures=measures,
                measure_expressions=measure_expressions,
                where=ref.where,
                scope_filters=scope_only_filters,
            )
        assert fk_col is not None  # narrowed by the else branch above
        # #1250: for cross-entity aggregates the source-entity
        # __scope_predicate references a table not in the aggregate's
        # FROM clause — strip it before passing through. Same root cause
        # as #1231 for the share/via paths; the FK path's IN clause
        # (`{fk_col}__in = member_ids`) already enforces source-row
        # scoping because member_ids only contains scope-passing ids.
        # When aggregated_entity == source_entity (same-entity aggregate,
        # e.g. self-referencing FK), keep the predicate — it qualifies a
        # column on the table that IS in the FROM.
        fk_scope_filters = scope_only_filters
        if aggregated_entity != source_entity:
            fk_scope_filters = _strip_scope_predicate(scope_only_filters)
        return await _batched_fk_cohort_aggregate(
            agg_repo=agg_repo,
            fk_col=fk_col,
            aggregated_entity=aggregated_entity,
            member_ids=member_ids,
            measures=measures,
            measure_expressions=measure_expressions,
            where=ref.where,
            scope_filters=fk_scope_filters,
        )
    except Exception:
        logger.warning(
            "cohort_strip lens %r batched aggregate query failed",
            getattr(lens, "id", "<unknown>"),
            exc_info=True,
        )
        return {}


async def _batched_fk_cohort_aggregate(
    *,
    agg_repo: Any,
    fk_col: str,
    aggregated_entity: str,
    member_ids: list[str],
    measures: dict[str, str],
    measure_expressions: dict[str, tuple[str, list[Any]]] | None,
    where: Any,
    scope_filters: dict[str, Any] | None,
) -> dict[str, Any]:
    """Batched no-via cohort aggregate (#1153).

    One GROUP BY query keyed on the aggregated entity's FK to the
    source. Each result row carries its member id under the FK column.
    Members not present in the result (no rows matched) are absent
    from the returned dict — cells render without a value, same
    semantics as the old N+1 path.

    ``where`` is the typed ``ConditionExpr`` from the AggregateRef.
    ``measure_expressions`` carries L3 (#1152) precompiled SQL
    fragments. Scope filters merge in via
    :func:`workspace_aggregation._build_aggregate_filters` so the
    aggregated entity's RBAC predicate is composed pre-GROUP BY.
    """
    from dazzle.http.runtime.aggregate import Dimension
    from dazzle.http.runtime.workspace_aggregation import _build_aggregate_filters

    per_cohort_filters: dict[str, Any] = {**scope_filters} if scope_filters else {}
    # ``field__in`` syntax — QueryBuilder.FilterCondition.parse converts
    # this to a SQL ``IN (?, ?, ...)`` clause.
    per_cohort_filters[f"{fk_col}__in"] = list(member_ids)
    merged = _build_aggregate_filters(where, per_cohort_filters, agg_repo, aggregated_entity)
    buckets = await agg_repo.aggregate(
        dimensions=[Dimension(name=fk_col)],
        measures=measures,
        filters=merged,
        # Cohort size + headroom — every member should fit. We don't
        # want a silent truncation when the result row count exceeds
        # the default limit.
        limit=len(member_ids) + 10,
        measure_expressions=measure_expressions,
    )
    out: dict[str, Any] = {}
    for bucket in buckets:
        member = bucket.dimensions.get(fk_col)
        if member is None:
            continue
        value = bucket.measures.get("primary")
        if value is not None:
            out[str(member)] = value
    return out


async def _batched_via_cohort_aggregate(
    *,
    agg_repo: Any,
    via: Any,  # ViaCondition
    via_link: tuple[str, str, str],
    aggregated_entity: str,
    member_ids: list[str],
    measures: dict[str, str],
    measure_expressions: dict[str, tuple[str, list[Any]]] | None,
    where: Any,
    scope_filters: dict[str, Any] | None,
) -> dict[str, Any]:
    """Batched via-junction cohort aggregate (#1153).

    Composes a JOIN-aware GROUP BY query. The dimension lives on the
    junction (the via binding with ``target == "id"``), not on the
    aggregated entity — so this can't go through ``build_aggregate_sql``,
    which assumes the dimension column is on the source table.

    SQL shape::

        SELECT j.<member_binding_col> AS member_id,
               <agg>(<measure>) AS primary
        FROM   <aggregated_table> a
        INNER JOIN <junction> j
               ON a.<aggregated_filter_col> = j.<junction_select_field>
        WHERE  j.<member_binding_col> IN (...)
          AND  <non-id bindings>
          AND  <where + scope predicates against a>
        GROUP BY j.<member_binding_col>
        LIMIT N+10

    The ``aggregated_filter_col`` / ``junction_select_field`` pair
    comes from :func:`_resolve_via_link_direction` — same direction
    discovery the N+1 path uses, so the two paths agree on the link
    shape.
    """
    from dazzle.http.runtime.aggregate import measure_to_sql
    from dazzle.http.runtime.query_builder import QueryBuilder, quote_identifier
    from dazzle.http.runtime.workspace_aggregation import _build_aggregate_filters

    subq_select_field, agg_filter_col, _direction = via_link

    # Locate the binding whose target is the cohort member id — that
    # column becomes the GROUP BY dimension. Other bindings (e.g.
    # ``revoked_at = null``) compose into the WHERE clause.
    member_binding_col: str | None = None
    static_bindings: list[Any] = []
    for binding in via.bindings:
        if binding.target == "id" and member_binding_col is None:
            member_binding_col = binding.junction_field
        else:
            static_bindings.append(binding)
    if member_binding_col is None:
        # Without an ``id``-target binding there's no member key to
        # group on — fall back to empty so cells render without
        # values rather than fabricating ones.
        return {}

    placeholder = agg_repo.db.placeholder
    agg_table = quote_identifier(agg_repo.table_name)
    junction_table = quote_identifier(via.junction_entity)
    member_col_q = quote_identifier(member_binding_col)
    agg_filter_q = quote_identifier(agg_filter_col)
    subq_select_q = quote_identifier(subq_select_field)

    # Measure SQL (one measure — "primary"). Either via the precompiled
    # expression (L3) or the simple ``func:col`` shape that
    # ``measure_to_sql`` understands.
    measure_sql: str
    measure_params: list[Any] = []
    if measure_expressions and "primary" in measure_expressions:
        outer_func = measures["primary"].lower()
        inner_sql, inner_params = measure_expressions["primary"]
        measure_sql = f"{outer_func.upper()}({inner_sql})"
        measure_params = list(inner_params)
    else:
        compiled = measure_to_sql(measures["primary"])
        if compiled is None:
            return {}
        measure_sql = compiled

    # Member-id IN clause for the junction.
    in_placeholders = ", ".join(placeholder for _ in member_ids)
    where_clauses: list[str] = [f"j.{member_col_q} IN ({in_placeholders})"]
    where_params: list[Any] = list(member_ids)

    # Non-id bindings translate to junction-side WHERE filters.
    for binding in static_bindings:
        col = quote_identifier(binding.junction_field)
        op = getattr(binding, "operator", "=") or "="
        if binding.target == "null":
            where_clauses.append(f"j.{col} IS NULL" if op == "=" else f"j.{col} IS NOT NULL")
        elif binding.target == "id":
            # Already handled above as the dimension binding.
            continue
        # Other targets (current_user.*, literals) are out of scope —
        # mirrors the N+1 helper's reach.

    # #1231: drop any source-entity scope predicate from scope_filters
    # before composition. The IN clause above (`j.{member_col_q} IN (...)`)
    # already enforces source-row scoping — only members whose source row
    # passed RBAC are in member_ids. Threading the source-entity
    # `__scope_predicate` through here would emit a qualifier like
    # `"ClassEnrolment"."school" = $N` which Postgres rejects because
    # the source table isn't in this FROM clause (only `a JOIN j`).
    scope_filters = _strip_scope_predicate(scope_filters)

    # AggregateRef.where + scope_filters → reuse the existing builder
    # so the typed ConditionExpr → SQL path stays single-sourced.
    composed_filters = _build_aggregate_filters(where, scope_filters, agg_repo, aggregated_entity)
    if composed_filters:
        # #1229: the aggregated table is aliased ``a`` in the FROM clause
        # below, but ``_build_aggregate_filters`` compiles the typed
        # ``where`` predicate against ``aggregated_entity``, so the
        # ``__scope_predicate`` SQL is already qualified with the entity
        # name (e.g. ``"MarkingResult"."col"``). Rewrite that qualifier
        # to the alias ``a`` so Postgres can resolve the column.
        composed_filters = _retarget_scope_predicate_to_alias(
            composed_filters, aggregated_entity, "a"
        )
        sub_builder = QueryBuilder(table_name=agg_repo.table_name, placeholder_style=placeholder)
        sub_builder.add_filters(composed_filters)
        sub_sql, sub_params = sub_builder.build_where_clause()
        # ``build_where_clause`` returns ``"WHERE ..."`` (uppercased).
        # Strip the leading WHERE so we can compose with AND.
        if sub_sql.lower().startswith("where "):
            sub_sql_body = sub_sql[6:].strip()
            if sub_sql_body:
                where_clauses.append(sub_sql_body)
                where_params.extend(sub_params)

    sql_parts: list[str] = [
        f"SELECT j.{member_col_q} AS member_id, {measure_sql} AS {quote_identifier('primary')}",
        f"FROM {agg_table} a",
        f"INNER JOIN {junction_table} j ON a.{agg_filter_q} = j.{subq_select_q}",
        "WHERE " + " AND ".join(where_clauses),
        f"GROUP BY j.{member_col_q}",
        f"LIMIT {len(member_ids) + 10}",
    ]
    sql = " ".join(sql_parts)
    params = measure_params + where_params

    with agg_repo.db.connection() as conn:
        cursor = conn.cursor()
        # Composition path above quotes every identifier via
        # ``quote_identifier`` and passes all literals as bound
        # parameters; same safety contract as ``Repository.aggregate``.
        cursor.execute(  # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query
            sql, params
        )
        rows = cursor.fetchall()

    out: dict[str, Any] = {}
    for row in rows:
        if hasattr(row, "keys"):
            row_dict = dict(row)
        else:
            row_dict = {"member_id": row[0], "primary": row[1]}
        member = row_dict.get("member_id")
        if member is None:
            continue
        value = row_dict.get("primary")
        if value is not None:
            out[str(member)] = value
    return out


async def _batched_share_cohort_aggregate(
    *,
    agg_repo: Any,
    source_repo: Any,
    share_link: tuple[str, str],  # (agg_to_pivot_fk, source_to_pivot_fk)
    aggregated_entity: str,
    member_ids: list[str],
    measures: dict[str, str],
    measure_expressions: dict[str, tuple[str, list[Any]]] | None,
    where: Any,
    scope_filters: dict[str, Any] | None,
) -> dict[str, Any]:
    """Batched shared-parent cohort aggregate (#1216).

    For each cohort source row, aggregate ``aggregated_entity`` rows
    whose reference to the named pivot equals the source row's
    reference to the same pivot. Single GROUP BY query keyed on the
    source row's primary key — the pivot table itself never appears
    in the FROM clause because both FKs hold the same id values, so
    an equi-join on the FK columns suffices.

        SELECT s.id AS member_id,
               <agg>(<measure>) AS primary
        FROM   <aggregated_table> a
        INNER JOIN <source_table> s
               ON a.<agg_to_pivot_fk> = s.<source_to_pivot_fk>
        WHERE  s.id IN (...member_ids)
          AND  <where + scope predicates against a>
        GROUP BY s.id
        LIMIT N+10

    Mutually exclusive with the ``via:`` true-junction path — see
    :class:`LensAggregatePrimary` and the parse-time guard.
    """
    from dazzle.http.runtime.aggregate import measure_to_sql
    from dazzle.http.runtime.query_builder import QueryBuilder, quote_identifier
    from dazzle.http.runtime.workspace_aggregation import _build_aggregate_filters

    agg_to_pivot_fk, source_to_pivot_fk = share_link

    placeholder = agg_repo.db.placeholder
    agg_table = quote_identifier(agg_repo.table_name)
    source_table = quote_identifier(source_repo.table_name)
    agg_pivot_q = quote_identifier(agg_to_pivot_fk)
    source_pivot_q = quote_identifier(source_to_pivot_fk)

    measure_sql: str
    measure_params: list[Any] = []
    if measure_expressions and "primary" in measure_expressions:
        outer_func = measures["primary"].lower()
        inner_sql, inner_params = measure_expressions["primary"]
        measure_sql = f"{outer_func.upper()}({inner_sql})"
        measure_params = list(inner_params)
    else:
        compiled = measure_to_sql(measures["primary"])
        if compiled is None:
            return {}
        measure_sql = compiled

    in_placeholders = ", ".join(placeholder for _ in member_ids)
    where_clauses: list[str] = [f's."id" IN ({in_placeholders})']
    where_params: list[Any] = list(member_ids)

    # #1231: drop the source-entity __scope_predicate before composition —
    # the `s."id" IN (...)` clause above already enforces source-row
    # scoping (only members whose source row passed RBAC are in member_ids).
    # The raw predicate is qualified by source-entity name (e.g.
    # `"ClassEnrolment"."school" = $N`) and would need retargeting to
    # the alias `s`; cheaper and clearer to strip it.
    scope_filters = _strip_scope_predicate(scope_filters)

    composed_filters = _build_aggregate_filters(where, scope_filters, agg_repo, aggregated_entity)
    if composed_filters:
        # #1229: see _batched_via_cohort_aggregate above — the FROM clause
        # aliases the aggregated table to ``a``, so the predicate SQL
        # (qualified with the entity name) must be retargeted to the alias.
        composed_filters = _retarget_scope_predicate_to_alias(
            composed_filters, aggregated_entity, "a"
        )
        sub_builder = QueryBuilder(table_name=agg_repo.table_name, placeholder_style=placeholder)
        sub_builder.add_filters(composed_filters)
        sub_sql, sub_params = sub_builder.build_where_clause()
        if sub_sql.lower().startswith("where "):
            sub_sql_body = sub_sql[6:].strip()
            if sub_sql_body:
                where_clauses.append(sub_sql_body)
                where_params.extend(sub_params)

    sql_parts: list[str] = [
        f'SELECT s."id" AS member_id, {measure_sql} AS {quote_identifier("primary")}',
        f"FROM {agg_table} a",
        f"INNER JOIN {source_table} s ON a.{agg_pivot_q} = s.{source_pivot_q}",
        "WHERE " + " AND ".join(where_clauses),
        'GROUP BY s."id"',
        f"LIMIT {len(member_ids) + 10}",
    ]
    sql = " ".join(sql_parts)
    params = measure_params + where_params

    with agg_repo.db.connection() as conn:
        cursor = conn.cursor()
        cursor.execute(  # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query
            sql, params
        )
        rows = cursor.fetchall()

    out: dict[str, Any] = {}
    for row in rows:
        if hasattr(row, "keys"):
            row_dict = dict(row)
        else:
            row_dict = {"member_id": row[0], "primary": row[1]}
        member = row_dict.get("member_id")
        if member is None:
            continue
        value = row_dict.get("primary")
        if value is not None:
            out[str(member)] = value
    return out


def _strip_scope_predicate(
    filters: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return a copy of ``filters`` with the ``__scope_predicate`` key
    removed. Used by ``share:`` / ``via:`` cohort paths where the
    member-id IN clause already enforces source-row scoping and the
    raw scope predicate (qualified with the source-entity name) would
    reference a table not in the bespoke FROM clause (#1231).
    """
    if not filters or "__scope_predicate" not in filters:
        return filters
    out = dict(filters)
    out.pop("__scope_predicate", None)
    return out


def _retarget_scope_predicate_to_alias(
    filters: dict[str, Any], entity_name: str, alias: str
) -> dict[str, Any]:
    """Rewrite ``__scope_predicate`` SQL so ``"<entity_name>".`` qualifiers
    become ``"<alias>".`` — used by the ``share:`` / ``via:`` cohort paths
    where the aggregated table is aliased in the FROM clause but the
    predicate compiler emits entity-name-qualified column refs.

    Returns a shallow copy so the caller's dict isn't mutated.
    """
    pred = filters.get("__scope_predicate")
    if pred is None:
        return filters
    pred_sql, pred_params = pred
    needle = f'"{entity_name}".'
    if needle not in pred_sql:
        return filters
    new_sql = pred_sql.replace(needle, f'"{alias}".')
    out = dict(filters)
    out["__scope_predicate"] = (new_sql, pred_params)
    return out


def _all_fks_to(repo: Any, target_entity: str) -> list[str]:
    """Return *all* ref-field names on ``repo``'s entity pointing at
    ``target_entity``.

    Used by the ``share:`` compute path (#1216) to detect ambiguous
    pivot references — when the caller needs to refuse rather than
    silently pick the first FK.
    """
    spec = getattr(repo, "entity_spec", None)
    if spec is None:
        return []
    out: list[str] = []
    for fld in getattr(spec, "fields", []):
        ftype = getattr(fld, "type", None)
        if ftype is None or getattr(ftype, "kind", None) != "ref":
            continue
        if getattr(ftype, "ref_entity", None) == target_entity:
            name = fld.name
            if name is not None:
                out.append(str(name))
    return out


def _resolve_via_link_direction(
    aggregated_repo: Any,
    junction_repo: Any,
    junction_entity_name: str,
) -> tuple[str, str, str] | None:
    """Discover how the aggregated entity links to the junction.

    Two directions are supported (phase 3 of #1144):

    - **Junction → Aggregated** (most common for true M2M junctions):
      the junction has a FK column pointing at the aggregated entity.
      The subquery selects that FK column; the aggregated entity is
      filtered on its primary key ``id``.

    - **Aggregated → Junction**: the aggregated entity has a FK
      column pointing at the junction. The subquery selects the
      junction's ``id``; the aggregated entity is filtered on its
      FK column.

    Junction-to-aggregated is checked first because it's the natural
    shape of declarative junction tables. Returns ``None`` when no FK
    in either direction can be discovered — caller logs a clear
    warning and skips the lens.

    Returns ``(subquery_select_field, aggregated_filter_col, direction)``
    where ``direction`` is ``"junction_to_agg"`` or ``"agg_to_junction"``.
    """
    aggregated_entity_name = _entity_name_of(aggregated_repo)
    # Direction A: junction has FK to aggregated entity.
    if aggregated_entity_name:
        col = _find_fk_to(junction_repo, aggregated_entity_name)
        if col is not None:
            return col, "id", "junction_to_agg"
    # Direction B: aggregated entity has FK to junction.
    col = _find_fk_to(aggregated_repo, junction_entity_name)
    if col is not None:
        return "id", col, "agg_to_junction"
    return None


def _entity_name_of(repo: Any) -> str | None:
    """Read the entity name from a repository's spec. Returns None when
    the spec doesn't carry a ``name`` attribute (e.g. test mocks)."""
    spec = getattr(repo, "entity_spec", None)
    if spec is None:
        return None
    return getattr(spec, "name", None)


def _find_fk_to(repo: Any, target_entity: str) -> str | None:
    """Find the column on ``repo``'s entity that's a FK referencing
    ``target_entity``. Returns the column name or None when no such
    FK exists.

    Used by ``compute_cohort_aggregate_primary`` to discover the
    per-member filter column without requiring authors to declare it.
    """
    spec = getattr(repo, "entity_spec", None)
    if spec is None:
        return None
    for fld in getattr(spec, "fields", []):
        ftype = getattr(fld, "type", None)
        if ftype is None or getattr(ftype, "kind", None) != "ref":
            continue
        if getattr(ftype, "ref_entity", None) == target_entity:
            name = fld.name
            return str(name) if name is not None else None
    return None


def compute_columns_for_persona(
    precomputed_columns: list[dict[str, Any]],
    user_roles: list[str],
) -> list[dict[str, Any]]:
    """Filter precomputed columns by their ``visible_condition`` (#872).

    Builds a fresh list — never mutates the shared one. Columns
    without a visible_condition pass through. Roles are stripped
    of any ``role_`` prefix to match how the condition author
    writes them.
    """
    if not any(c.get("visible_condition") for c in precomputed_columns):
        return precomputed_columns

    role_ctx = {"user_roles": [r.removeprefix("role_") for r in user_roles]}
    return [
        c
        for c in precomputed_columns
        if not c.get("visible_condition") or _eval_vis(c["visible_condition"], {}, role_ctx)
    ]


def compute_filter_columns_and_active(
    columns: list[dict[str, Any]],
    query_params: Any,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Build (filter_columns, active_filters) from column metadata + request.

    Filter columns are the subset of resolved columns marked
    ``filterable``. Active filters are the ``filter_<key>=<value>``
    query-param pairs.
    """
    filter_columns = [
        {
            "key": c["key"],
            "label": c["label"],
            "options": c.get("filter_options", []),
        }
        for c in columns
        if c.get("filterable")
    ]
    active_filters: dict[str, str] = {
        k[7:]: v for k, v in query_params.items() if k.startswith("filter_") and v
    }
    return filter_columns, active_filters


def apply_attention_signals(
    items: list[dict[str, Any]],
    attention_signals: list[Any],
    filter_context: dict[str, Any],
) -> None:
    """Annotate items with the highest-severity attention signal that
    matches each one (mutates items in place).

    Each item gets an ``_attention`` key with ``{level, message}`` for
    the most severe signal whose condition evaluates true. Severity
    order: critical > warning > notice > info.
    """
    if not (attention_signals and items):
        return

    import logging

    from dazzle.http.runtime.condition_evaluator import evaluate_condition as _eval_cond

    logger = logging.getLogger(__name__)
    severity_order = {"critical": 0, "warning": 1, "notice": 2, "info": 3}

    for item in items:
        best: dict[str, str] | None = None
        best_sev = 999
        for sig in attention_signals:
            try:
                cond_dict = sig.condition.model_dump(exclude_none=True)
                if _eval_cond(cond_dict, item, filter_context):
                    lvl = sig.level.value if hasattr(sig.level, "value") else str(sig.level)
                    sev = severity_order.get(lvl, 99)
                    if sev < best_sev:
                        best_sev = sev
                        best = {"level": lvl, "message": sig.message}
            except Exception:
                logger.debug("Failed to evaluate attention signal", exc_info=True)
        if best:
            item["_attention"] = best


def compute_kanban_columns(
    entity_spec: Any,
    group_by_field: str,
) -> list[str]:
    """Resolve the bucket column list for a grouped view (KANBAN /
    BAR_CHART / FUNNEL_CHART).

    First checks the field's enum values, then falls back to the
    entity's state-machine states (only when the state machine's
    ``status_field`` matches ``group_by_field``).

    Returns an empty list when the field has no enum and no matching
    state machine — caller should fall back to distinct items[group_by].
    """
    if entity_spec is None:
        return []

    for f in entity_spec.fields:
        if f.name == group_by_field:
            ev = getattr(f.type, "enum_values", None)
            if ev:
                return list(ev)
            break

    sm = entity_spec.state_machine
    if sm and sm.status_field == group_by_field:
        return [s if isinstance(s, str) else str(s) for s in sm.states]

    return []
