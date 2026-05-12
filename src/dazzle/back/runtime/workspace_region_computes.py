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

from dazzle.back.runtime.workspace_card_data import _resolve_display_name


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
