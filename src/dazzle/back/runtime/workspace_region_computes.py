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

from typing import Any

from dazzle.back.runtime.workspace_card_data import (
    _initials_from,
    _interpolate_card_template,
    _resolve_path,
)
from dazzle.render.display_names import _resolve_display_name


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

    from dazzle.core.strings import to_api_plural

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
    (the dashboard doesn't crash on author error).
    """
    import logging

    logger = logging.getLogger(__name__)

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
        try:
            if not format_spec:
                formatted = str(value)
            elif "{" in format_spec:
                formatted = format_spec.format(value)
            else:
                formatted = format(value, format_spec)
        except (ValueError, TypeError, KeyError, IndexError):
            logger.warning(
                "bar_track region %r: invalid track_format %r — rendering raw value",
                region_name,
                format_spec,
            )
            formatted = str(value)
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

    from dazzle.back.runtime.workspace_aggregation import _fetch_count_metric
    from dazzle.core.ir import AggregateRef

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

    from dazzle.back.runtime.workspace_aggregation import _fetch_count_metric
    from dazzle.back.runtime.workspace_card_data import _coerce_pipeline_progress
    from dazzle.core.ir import AggregateRef

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
    member_via: str,
) -> dict[str, Any]:
    """Compute per-member aggregate values for a cohort_strip primary_aggregate lens.

    Phase 2 of #1144 Gap 1: closes the runtime gap where the IR was
    typed but the rendering raised ``NotImplementedError``. Per ADR-0024
    the aggregate is a typed :class:`AggregateRef`; the runtime
    dispatches on its fields.

    **Scope of phase 2:** the **no-via** case. The aggregated entity
    must declare a direct FK to the source entity; per-member filters
    are ``aggregated_entity.<source_fk> = <member_id>``. The ``via:``
    junction-binding case is deferred to phase 3 — that needs a
    parameter-binding via-subquery compiler that's semantically
    distinct from the scope-rule via reused at the IR layer.

    When ``lens.primary_aggregate.via`` is set, this helper logs a
    warning and returns an empty dict (cells will render as no-value).

    N+1 fan-out — one ``Repository.aggregate`` call per cohort member.
    Phase 3 batches into one GROUP BY query.

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
        member_via: The cohort_strip ``member_via:`` field (typically
            ``id`` or an FK column).

    Returns:
        Mapping of cohort member id → aggregate value. Members whose
        query failed or returned no rows are absent from the mapping
        (the cell renders without a value).
    """
    import asyncio as _asyncio
    import logging

    from dazzle.core.ir import AggregateRef

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
    junction_repo = repositories.get(via.junction_entity) if (via and repositories) else None
    via_link: tuple[str, str, str] | None = None  # (subq_select_field, agg_filter_col, direction)
    if via is not None:
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
                "junction %r — declare a direct reference or use the no-via "
                "case. Cells will render without a value.",
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

    # Build the shared measure spec — same for every per-member call.
    # L3 (#1152): when the AggregateRef carries an ``expression`` the
    # measure spec uses the outer aggregate func name and pairs it with
    # a precompiled SQL fragment in ``measure_expressions``. The runtime
    # builder slots the fragment into ``<FUNC>(<fragment>)`` and binds
    # the inner parameters ahead of the WHERE-clause ones.
    measure_expressions: dict[str, tuple[str, list[Any]]] | None = None
    if ref.func == "count":
        measures = {"primary": "count"}
    elif ref.expression is not None:
        from dazzle.back.runtime.aggregate_expression import (
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

    async def _fetch_for(member_id: str) -> tuple[str, Any]:
        from dazzle.back.runtime.workspace_aggregation import _build_aggregate_filters

        if via_link is not None and via is not None:
            # Phase 3: build the junction subquery as a __scope_predicate.
            subq_select_field, agg_filter_col, _direction = via_link
            via_sql, via_params = _build_cohort_via_subquery(
                via=via,
                member_id=member_id,
                junction_select_field=subq_select_field,
                aggregated_filter_col=agg_filter_col,
            )
            per_member_filters: dict[str, Any] = {"__scope_predicate": (via_sql, via_params)}
        else:
            # Phase 2: direct-FK per-member filter.
            assert fk_col is not None  # narrowed by the else branch above
            per_member_filters = {fk_col: member_id}

        merged = _build_aggregate_filters(
            ref.where,
            per_member_filters,
            agg_repo,
            aggregated_entity,
        )
        try:
            buckets = await agg_repo.aggregate(
                dimensions=[],
                measures=measures,
                filters=merged,
                limit=1,
                measure_expressions=measure_expressions,
            )
        except Exception:
            logger.warning(
                "cohort_strip lens %r aggregate query failed for member %r",
                getattr(lens, "id", "<unknown>"),
                member_id,
                exc_info=True,
            )
            return member_id, None
        if not buckets:
            return member_id, None
        return member_id, buckets[0].measures.get("primary")

    member_ids: list[str] = []
    for item in items:
        # Cohort member key — uses the source row's `id` field, matching
        # the `_build_cohort_cells` resolution.
        mid = str(item.get("id", "") or "")
        if mid:
            member_ids.append(mid)
    if not member_ids:
        return out

    results = await _asyncio.gather(
        *(_fetch_for(mid) for mid in member_ids), return_exceptions=False
    )
    for mid, value in results:
        if value is not None:
            out[mid] = value
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


def _build_cohort_via_subquery(
    *,
    via: Any,  # ViaCondition
    member_id: str,
    junction_select_field: str,
    aggregated_filter_col: str,
) -> tuple[str, list[Any]]:
    """Build a __scope_predicate SQL fragment from a cohort-aggregate
    ``via:`` clause + the current member's id.

    Distinct from the scope-rule via compiler (route_generator
    ``_build_via_subquery``) because the binding semantics differ:

    - Scope-rule via: ``target="id"`` refers to the **scoped entity's
      ``id`` column** — produces ``entity.id IN (SELECT ...)``.
    - Cohort-aggregate via: ``target="id"`` refers to the **current
      cohort member's id** — produces ``junction.field = <literal
      member_id>``.

    Shape:

      WHERE <aggregated_filter_col> IN (
          SELECT <junction_select_field>
          FROM <Junction>
          WHERE <each binding>
      )

    Binding interpretations:
      - ``target="id"`` → ``junction.field <op> <member_id literal>``
      - ``target="null"`` → ``junction.field IS NULL`` / ``IS NOT NULL``
      - Other targets (``current_user.*``, etc.) → not yet supported;
        skipped (the binding has no effect on the subquery).

    Returns ``(sql, params)`` ready to be plugged into a
    QueryBuilder ``__scope_predicate`` slot.
    """
    from dazzle.back.runtime.query_builder import quote_identifier

    junction_table = quote_identifier(via.junction_entity)
    where_clauses: list[str] = []
    params: list[Any] = []
    for binding in via.bindings:
        jf = quote_identifier(binding.junction_field)
        op = getattr(binding, "operator", "=") or "="
        target = binding.target
        if target == "null":
            if op == "=":
                where_clauses.append(f"{jf} IS NULL")
            else:
                where_clauses.append(f"{jf} IS NOT NULL")
        elif target == "id":
            where_clauses.append(f"{jf} {op} %s")
            params.append(member_id)
        # Other binding targets (current_user.*, literals) are not
        # part of the phase 3 surface — the cohort aggregate's only
        # parameter is the member id. Future phases can extend.
    where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"
    agg_col = quote_identifier(aggregated_filter_col)
    select_col = quote_identifier(junction_select_field)
    sql = f"{agg_col} IN (SELECT {select_col} FROM {junction_table} WHERE {where_sql})"
    return sql, params


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

    from dazzle.ui.utils.condition_eval import evaluate_condition as _eval_vis

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

    from dazzle.back.runtime.condition_evaluator import evaluate_condition as _eval_cond

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
