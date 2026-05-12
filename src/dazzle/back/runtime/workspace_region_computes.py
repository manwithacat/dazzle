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
    _resolve_display_name,
    _resolve_path,
)


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
    build time) plus an optional ``count_aggregate`` expression. When
    parseable, fires one ``_fetch_count_metric`` per card concurrently
    via ``asyncio.gather``. Cross-entity counts run unscoped with a
    warning, mirroring the source-entity scope gate (#901). When
    ``scope_denied`` is True, all cards render without counts.
    """
    import asyncio as _asyncio
    import logging

    from dazzle.back.runtime.workspace_aggregation import (
        _AGGREGATE_RE,
        _fetch_count_metric,
    )

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
        expr = card.get("count_aggregate") or ""
        if not expr:
            continue
        m = _AGGREGATE_RE.match(expr)
        if not m:
            continue
        func, entity_name, where = m.groups()
        agg_repo = repositories.get(entity_name) if repositories else None
        if func != "count" or agg_repo is None:
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
                where,
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

    Each stage's ``value`` and ``progress`` fields are either:
    - an aggregate expression (matches ``_AGGREGATE_RE``, fires a count
      query),
    - or a literal string (renders verbatim — v0.61.66 #4).

    Cross-entity aggregates run unscoped with a warning (#901). When
    ``scope_denied`` is True, aggregate stages render without values
    but literals are preserved.
    """
    import asyncio as _asyncio
    import logging

    from dazzle.back.runtime.workspace_aggregation import (
        _AGGREGATE_RE,
        _fetch_count_metric,
    )
    from dazzle.back.runtime.workspace_card_data import _coerce_pipeline_progress

    logger = logging.getLogger(__name__)
    out: list[dict[str, Any]] = []

    if not stages:
        return out

    if scope_denied:
        for stage in stages:
            expr = stage.get("value") or ""
            is_literal = bool(expr) and not _AGGREGATE_RE.match(expr)
            prog_expr = stage.get("progress") or ""
            prog_is_literal = bool(prog_expr) and not _AGGREGATE_RE.match(prog_expr)
            prog_raw: Any = prog_expr if prog_is_literal else None
            prog_clamped, prog_overshoot = _coerce_pipeline_progress(prog_raw)
            out.append(
                {
                    "label": stage.get("label", ""),
                    "caption": stage.get("caption", ""),
                    "value": expr if is_literal else None,
                    "progress": prog_clamped,
                    "progress_overshoot": prog_overshoot,
                }
            )
        return out

    stage_tasks: list[Any] = []
    stage_task_keys: list[tuple[int, str]] = []
    stage_literals: dict[tuple[int, str], str] = {}

    def queue_stage_field(sidx: int, field: str, expr: str) -> None:
        if not expr:
            return
        m = _AGGREGATE_RE.match(expr)
        if not m:
            stage_literals[(sidx, field)] = expr
            return
        func, entity_name, where = m.groups()
        agg_repo = repositories.get(entity_name) if repositories else None
        if func != "count" or agg_repo is None:
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
                where,
                stage_scope,
                source_entity=entity_name,
            )
        )
        stage_task_keys.append((sidx, field))

    for sidx, stage in enumerate(stages):
        queue_stage_field(sidx, "value", stage.get("value") or "")
        queue_stage_field(sidx, "progress", stage.get("progress") or "")

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
        val: Any = stage_literals.get((sidx, "value"), stage_results.get((sidx, "value")))
        prog_raw_resolved: Any = stage_literals.get(
            (sidx, "progress"), stage_results.get((sidx, "progress"))
        )
        prog_clamped, prog_overshoot = _coerce_pipeline_progress(prog_raw_resolved)
        out.append(
            {
                "label": stage.get("label", ""),
                "caption": stage.get("caption", ""),
                "value": val,
                "progress": prog_clamped,
                "progress_overshoot": prog_overshoot,
            }
        )
    return out


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
