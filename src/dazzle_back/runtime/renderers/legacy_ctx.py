"""Phase 4B.2 — translate legacy Jinja-template ctx into adapter ctx.

The legacy workspace runtime computes per-region ctx in
`workspace_rendering.py` and passes it as kwargs to a Jinja template
(`render_fragment(template, **kwargs)`). The typed-Fragment adapter
(`WorkspaceRegionAdapter._build_*`) consumes a different ctx shape —
flat dicts with explicit field names, pre-aggregated data tuples,
typed primitives expectations.

This module bridges the two paths so the runtime can hand the same
legacy ctx to either renderer. The translator's job is shape
reshaping, not data computation — the runtime continues to compute
all aggregates, rollups, and bucketings; the translator just renames
and restructures.

Shape mapping table per display: see
`dev_docs/2026-05-08-phase-4b-ctx-mapping.md` for the discovery
output that drove this design.

Phase 4B.3's dual-path validation gate consumes this translator: it
renders every example region via both paths (Jinja vs adapter) and
asserts byte-equivalent output modulo whitespace/attr-order. A
display's translator is "complete" when the byte-equivalence check
passes for its example regions.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _passthrough(legacy: dict[str, Any]) -> dict[str, Any]:
    """Default — copy the legacy ctx as-is.

    Used for displays whose adapter ctx accepts the legacy keys
    directly, OR as a placeholder for displays whose translator
    hasn't been written yet. Phase 4B.3's validation gate will
    surface the latter as failing diff cases.
    """
    return dict(legacy)


# === Chart family translators ===
# All five chart families share a common ctx-shape pattern:
#  - Legacy:  bucketed_metrics / box_plot_stats / bar_track_rows / etc.
#  - Adapter: buckets / points / axes / groups / rows
# The translators below extract the relevant pre-computed list and
# reshape it to the adapter's named-tuple-of-tuples expectations.


def _bucketed_to_buckets(legacy: dict[str, Any]) -> list[tuple[str, int]]:
    """Common shape: list of `{label, value}` dicts → `[(label, value)]`.

    Used by BAR_CHART, FUNNEL_CHART, HISTOGRAM as the primary path
    when the runtime supplies pre-aggregated `bucketed_metrics`.
    """
    bm = legacy.get("bucketed_metrics") or []
    out: list[tuple[str, int]] = []
    for entry in bm:
        if isinstance(entry, dict):
            label = str(entry.get("label", ""))
            try:
                value = int(entry.get("value", 0))
            except (TypeError, ValueError):
                continue
            if label:
                out.append((label, value))
    return out


def _translate_bar_chart(legacy: dict[str, Any]) -> dict[str, Any]:
    """BAR_CHART: bucketed_metrics → buckets (primary path).

    Legacy template falls back to client-side rollup of `items` +
    `group_by` when bucketed_metrics is absent. The runtime's
    aggregation pipeline normally pre-computes bucketed_metrics, so
    the fallback is rarely exercised — defer it to a follow-up if
    real-world ctx ever surfaces it.
    """
    return {
        "buckets": _bucketed_to_buckets(legacy),
        "chart_label": legacy.get("title"),
        "reference_lines": legacy.get("reference_lines", []),
        "reference_bands": legacy.get("reference_bands", []),
    }


def _translate_funnel_chart(legacy: dict[str, Any]) -> dict[str, Any]:
    """FUNNEL_CHART: stages from `kanban_columns` + counts from
    in-template iteration of `items`.

    The adapter wants pre-computed `buckets`. We emit them in the
    declared `kanban_columns` order so the funnel reads top-down.
    """
    items = legacy.get("items") or []
    stages = legacy.get("kanban_columns") or []
    group_by = legacy.get("group_by")
    counts: dict[str, int] = dict.fromkeys(stages, 0)
    if group_by:
        for it in items:
            if isinstance(it, dict):
                key = it.get(group_by)
                if key in counts:
                    counts[key] += 1
    buckets = [(s, counts[s]) for s in stages] if stages else _bucketed_to_buckets(legacy)
    return {
        "buckets": buckets,
        "chart_label": legacy.get("title"),
    }


def _translate_histogram(legacy: dict[str, Any]) -> dict[str, Any]:
    """HISTOGRAM: histogram_bins → buckets.

    Bins carry `{label, count, low, high}`; we only consume label +
    count. low/high (continuous-axis labels) and reference_lines
    (vertical grade boundaries) are legacy-only.
    """
    bins = legacy.get("histogram_bins") or []
    buckets: list[tuple[str, int]] = []
    for b in bins:
        if isinstance(b, dict):
            label = str(b.get("label", ""))
            try:
                count = int(b.get("count", 0))
            except (TypeError, ValueError):
                continue
            if label:
                buckets.append((label, count))
    return {
        "buckets": buckets,
        "chart_label": legacy.get("title"),
    }


def _bucketed_to_points(legacy: dict[str, Any]) -> list[tuple[str, float]]:
    """Common shape: bucketed_metrics → `[(label, float)]` for time series."""
    bm = legacy.get("bucketed_metrics") or []
    out: list[tuple[str, float]] = []
    for entry in bm:
        if isinstance(entry, dict):
            label = str(entry.get("label", ""))
            try:
                value = float(entry.get("value", 0))
            except (TypeError, ValueError):
                continue
            if label:
                out.append((label, value))
    return out


def _translate_line_chart(legacy: dict[str, Any]) -> dict[str, Any]:
    """LINE_CHART / AREA_CHART / SPARKLINE: bucketed_metrics → points."""
    return {
        "points": _bucketed_to_points(legacy),
        "chart_label": legacy.get("title"),
        "reference_lines": legacy.get("reference_lines", []),
        "reference_bands": legacy.get("reference_bands", []),
    }


def _translate_radar(legacy: dict[str, Any]) -> dict[str, Any]:
    """RADAR: bucketed_metrics → axes (single-series).

    Multi-series via `bucketed_metrics[i].metrics` is legacy-only;
    routing it through requires extending the Radar primitive's axes
    schema (Phase 4B.4 territory).
    """
    bm = legacy.get("bucketed_metrics") or []
    axes: list[tuple[str, float]] = []
    for entry in bm:
        if isinstance(entry, dict):
            label = str(entry.get("label", ""))
            try:
                value = float(entry.get("value", 0))
            except (TypeError, ValueError):
                continue
            if label:
                axes.append((label, value))
    return {
        "axes": axes,
        "chart_label": legacy.get("title"),
    }


def _translate_box_plot(legacy: dict[str, Any]) -> dict[str, Any]:
    """BOX_PLOT: box_plot_stats → groups.

    Legacy stats carry 11 fields; adapter consumes 6 (label, min,
    q1, median, q3, max). `n`, `iqr`, `whisker_low`, `whisker_high`,
    `outliers` are dropped — Phase 4B.4 deliverable to thread them
    through if needed.
    """
    stats = legacy.get("box_plot_stats") or []
    groups: list[dict[str, Any]] = []
    for s in stats:
        if isinstance(s, dict):
            label = str(s.get("label", ""))
            if not label:
                continue
            try:
                groups.append(
                    {
                        "label": label,
                        "min": float(s.get("min", 0)),
                        "q1": float(s.get("q1", 0)),
                        "median": float(s.get("median", 0)),
                        "q3": float(s.get("q3", 0)),
                        "max": float(s.get("max", 0)),
                    }
                )
            except (TypeError, ValueError):
                continue
    return {
        "groups": groups,
        "chart_label": legacy.get("title"),
        "reference_lines": legacy.get("reference_lines", []),
    }


def _translate_bar_track(legacy: dict[str, Any]) -> dict[str, Any]:
    """BAR_TRACK: bar_track_rows passthrough + max.

    Legacy and adapter use the same row shape `{label, value,
    formatted_value, fill_pct}`; the adapter's `_build_bar_track`
    consumes them directly. We just forward the rows + max.
    """
    return {
        "bar_track_rows": legacy.get("bar_track_rows", []),
        "bar_track_max": legacy.get("bar_track_max", 0),
    }


# === Detail / metric translators ===


def _translate_metrics(legacy: dict[str, Any]) -> dict[str, Any]:
    """METRICS / SUMMARY: rename delta_direction → trend, keep KPI fields.

    Legacy delta dict carries `delta, delta_direction, delta_sentiment,
    delta_pct, delta_period_label`. Adapter KPI primitive consumes
    `label, value, trend, delta`. Extended delta fields are dropped.
    """
    metrics = legacy.get("metrics") or []
    out: list[dict[str, Any]] = []
    for m in metrics:
        if not isinstance(m, dict):
            continue
        kpi: dict[str, Any] = {
            "label": m.get("label"),
            "value": m.get("value"),
        }
        # delta_direction is the legacy-only "up/down/flat" hint; the
        # KPI primitive accepts a `trend` field of the same shape.
        if "delta_direction" in m:
            kpi["trend"] = m["delta_direction"]
        elif "trend" in m:
            kpi["trend"] = m["trend"]
        if "delta" in m:
            kpi["delta"] = m["delta"]
        out.append(kpi)
    return {"metrics": out}


def _translate_detail(legacy: dict[str, Any]) -> dict[str, Any]:
    """DETAIL: columns → fields (adapter accepts both via alias)."""
    return {
        "item": legacy.get("item", {}),
        "fields": legacy.get("columns", []),
    }


def _translate_activity_feed(legacy: dict[str, Any]) -> dict[str, Any]:
    """ACTIVITY_FEED → TIMELINE: pick activity-shaped fields."""
    return {
        "items": legacy.get("items", []),
        "label_field": "description",
        "date_field": "created_at",
    }


# === Dispatch ===

# Display name → translator. Display names match the strings used by
# `WorkspaceRegionAdapter._BUILDERS` / `_ALIASES` keys (lowercase,
# underscored), NOT the upper-case `DisplayMode` enum.
_DISPATCH: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    # Chart family (Phase 4B.1.c — contracts stable as of v0.66.98).
    "bar_chart": _translate_bar_chart,
    "funnel_chart": _translate_funnel_chart,
    "histogram": _translate_histogram,
    "line_chart": _translate_line_chart,
    "area_chart": _translate_line_chart,
    "sparkline": _translate_line_chart,
    "radar": _translate_radar,
    "box_plot": _translate_box_plot,
    "bar_track": _translate_bar_track,
    # Detail / metric translators.
    "metrics": _translate_metrics,
    "summary": _translate_metrics,  # SUMMARY shares METRICS template.
    "detail": _translate_detail,
    "activity_feed": _translate_activity_feed,
}


def legacy_ctx_to_adapter_ctx(display: str, legacy: dict[str, Any]) -> dict[str, Any]:
    """Translate the legacy Jinja ctx for `display` into the shape
    expected by `WorkspaceRegionAdapter`.

    Returns a NEW dict — does not mutate the input. Displays without a
    registered translator fall back to passthrough (the adapter may
    or may not accept the legacy shape directly; Phase 4B.3's
    validation gate surfaces the gap).
    """
    translator = _DISPATCH.get(display, _passthrough)
    return translator(legacy)


__all__ = ["legacy_ctx_to_adapter_ctx"]
