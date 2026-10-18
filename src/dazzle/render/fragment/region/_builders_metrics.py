"""Metrics-family region builders.

Houses the metrics-family builders. All share the dashboard Surface
kind and tile/list/stage-row shapes:

  - _build_metrics         MetricsGrid of MetricTile primitives
  - _build_status_list     vertical icon + title + caption + pill rows
  - _build_pipeline_steps  horizontal stage cards with arrow connectors

No family-local helpers — all cross-cutting plumbing lives in `_shared`.

See issue #1065 for the full decomposition plan.
"""

from __future__ import annotations

from typing import Any, Literal

from dazzle.core.ir import AggregateRef, DerivedMetricExpr
from dazzle.render.filters import (
    _metric_number_filter,
    clerk_pipeline_stage_value,
    sentence_case_words,
)
from dazzle.render.fragment import (
    EmptyState,
    Fragment,
    MetricsGrid,
    MetricTile,
    PipelineStage,
    PipelineSteps,
    StatusList,
    StatusListEntry,
    Surface,
)
from dazzle.render.fragment.region._context import RegionContext
from dazzle.render.fragment.region._shared import (
    _region_title,
    _wrap_surface,
)
from dazzle.render.presentation import present
from dazzle.render.user_chip import looks_like_person_ref


def _metrics_tile_display_value(metric: dict[str, Any]) -> str | None:
    """Format a KPI value, or None when person×metrics_tile is refused.

    Numeric/bool/None stay on ``_metric_number_filter``. A person-shaped
    dict (or leftover name on a person-keyed metric) must not invent
    ``str(dict)`` / name prose on a tile (oral #44).
    """
    value = metric.get("value")
    if isinstance(value, (int, float, bool)) or value is None:
        return _metric_number_filter(value)
    col = {
        "key": str(metric.get("key") or ""),
        "type": str(metric.get("type") or ""),
        "ref_entity": str(metric.get("ref_entity") or ""),
    }
    probe = value if isinstance(value, dict) else None
    if probe is None:
        return _metric_number_filter(value)
    if not looks_like_person_ref(probe, col):
        return _metric_number_filter(value)
    pr = present("person", "metrics_tile", probe, col)
    if pr.density == "refuse" or pr.suppress_label:
        return None
    return _metric_number_filter(value)


def _metric_tile_from_dict(metric: dict[str, Any], drill_url: str = "") -> MetricTile | None:
    """One MetricTile, or None when label/value is refused.

    ``drill_url`` (#1798) is the region-level tile drill — every tile of the
    strip opens the same target.
    """
    label = str(metric.get("label") or metric.get("name") or "")
    if not label:
        return None
    value_str = _metrics_tile_display_value(metric)
    if value_str is None:
        return None
    tone_raw = str(metric.get("tone") or "")
    tone: Literal["", "positive", "warning", "destructive", "accent", "neutral"] = (
        tone_raw  # type: ignore[assignment]
        if tone_raw in ("", "positive", "warning", "destructive", "accent", "neutral")
        else ""
    )
    direction_raw = str(metric.get("delta_direction") or "")
    direction: Literal["", "up", "down", "flat"] = (
        direction_raw  # type: ignore[assignment]
        if direction_raw in ("", "up", "down", "flat")
        else ""
    )
    sentiment_raw = str(metric.get("delta_sentiment") or "")
    sentiment: Literal["", "positive_up", "positive_down"] = (
        sentiment_raw  # type: ignore[assignment]
        if sentiment_raw in ("", "positive_up", "positive_down")
        else ""
    )
    try:
        delta_pct = float(metric.get("delta_pct") or 0)
    except (TypeError, ValueError):
        delta_pct = 0.0
    return MetricTile(
        label=label,
        value=value_str,
        metric_key=str(metric.get("key", "")),
        tone=tone,
        delta_direction=direction,
        delta_sentiment=sentiment,
        delta_value=str(metric.get("delta") or ""),
        delta_pct=delta_pct,
        delta_period_label=str(metric.get("delta_period_label") or ""),
        drill_url=drill_url,
    )


class _BuildersMetricsMixin:
    """Mixin adding the metrics-family `_build_*` methods to
    `WorkspaceRegionAdapter`. Same pattern as `_BuildersChartsMixin`.
    """

    def _build_pipeline_steps(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: pipeline_steps` renders a horizontal row of stage
        cards with arrow connectors. Phase 4B.4 wave 2: dedicated
        `PipelineSteps` primitive replacing prior Card+Stack composition
        for byte-equivalence with `workspace/regions/pipeline_steps.html`.

        ctx shape (primary):
            pipeline_stage_data: list of dicts {label, value, caption,
                progress, progress_overshoot}
            empty_message: optional empty-state fallback
        """
        title = _region_title(region)
        raw_stages = ctx.get("pipeline_stage_data") or []

        stages: list[PipelineStage] = []
        if isinstance(raw_stages, list):
            for entry in raw_stages:
                if not isinstance(entry, dict):
                    continue
                label = str(entry.get("label") or entry.get("name") or "")
                if not label:
                    continue
                # Counts stay int; literal flow-card strings ride (oral #161).
                # ``int("Daily 02:00 UTC")`` used to become None → "—".
                value = clerk_pipeline_stage_value(entry.get("value"))
                # progress: None preserved (omits the bar); coerce to int else.
                progress: int | None
                progress_raw = entry.get("progress")
                if progress_raw is None:
                    progress = None
                else:
                    try:
                        progress = int(progress_raw)
                    except (TypeError, ValueError):
                        progress = None
                stages.append(
                    PipelineStage(
                        label=label,
                        value=value,
                        caption=str(entry.get("caption") or ""),
                        progress=progress,
                        progress_overshoot=bool(entry.get("progress_overshoot")),
                    )
                )

        empty_msg = (
            ctx.get("empty_message")
            or getattr(region, "empty_message", None)
            or "No pipeline data available."
        )
        body: Fragment = PipelineSteps(stages=tuple(stages), empty_message=str(empty_msg))
        return _wrap_surface(title, "dashboard", body)

    def _build_status_list(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: status_list` regions render as a `StatusList`
        primitive — vertical list of icon + title + caption + state-pill
        rows. Phase 4B.4 wave 1: dedicated primitive replacing the prior
        Stack+Row+Badge composition for byte-equivalence with
        `workspace/regions/status_list.html`.

        ctx shape:
            status_entries: list of dicts with keys
                title (required), state, caption, icon
            empty_message: optional override for the empty-state line
            (legacy items + label_field + status_field shape is no
             longer the primary path — the runtime supplies authored
             `status_entries` per the v0.61.69 design)
        """
        title = _region_title(region)
        raw_entries = ctx.get("status_entries") or []
        entries: list[StatusListEntry] = []
        for raw in raw_entries:
            if not isinstance(raw, dict):
                continue
            entry_title = str(raw.get("title") or "")
            if not entry_title:
                continue
            state_raw = str(raw.get("state") or "neutral") or "neutral"
            state: Literal["neutral", "positive", "warning", "destructive", "accent"] = (
                state_raw  # type: ignore[assignment]
                if state_raw in ("neutral", "positive", "warning", "destructive", "accent")
                else "neutral"
            )
            entries.append(
                StatusListEntry(
                    title=entry_title,
                    state=state,
                    caption=str(raw.get("caption") or ""),
                    icon=str(raw.get("icon") or ""),
                )
            )

        empty_msg = (
            ctx.get("empty_message")
            or getattr(region, "empty_message", None)
            or "No status entries."
        )
        body: Fragment = StatusList(entries=tuple(entries), empty_message=str(empty_msg))
        return _wrap_surface(title, "list", body)

    def _build_metrics(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: metrics` (and `summary`) regions render a row of
        MetricTile primitives — one per declared aggregate. Phase 4B.1.a
        replaced KPI with MetricTile so the legacy template's extended
        delta block (delta_pct, delta_period_label, delta_sentiment,
        per-tile tone) is preserved on the typed-Fragment path.

        Values are passed through `_metrics_tile_display_value`
        (number filter, or refuse person-shaped dicts) before reaching
        the primitive — same string the Jinja path produces for counts.

        ctx shape:
            metrics: list of dicts with keys:
              - label, value (required)
              - tone: one of "", "positive", "warning", "destructive",
                "accent", "neutral"
              - delta_direction: "" | "up" | "down" | "flat"
              - delta_sentiment: "" | "positive_up" | "positive_down"
              - delta: stringified delta value
              - delta_pct: float (rendered as `(N%)` when non-zero)
              - delta_period_label: rendered as `vs <label>`
            metrics_drill_url: whole-tile drill from the region's explicit
                `action:` (#1798); empty → tiles are not links
            (legacy) aggregates: dict[name → resolved value], used as
                fallback when metrics list isn't supplied
        """
        title = _region_title(region)
        metrics_list: list[dict[str, Any]] = ctx.get("metrics", []) or []
        if not metrics_list:
            agg = ctx.get("aggregates") or getattr(region, "aggregates", {}) or {}
            if isinstance(agg, dict):
                # Only resolved values become tiles. The sole runtime path that
                # populates `aggregates` stores the *raw* IR dict (AggregateRef /
                # DerivedMetricExpr), so on scope-denial — where the orchestrator
                # correctly leaves `metrics` empty — this fallback would otherwise
                # stringify the typed IR (`func='count' where=ConditionExpr(...)`)
                # straight into the tile, leaking the where-clause of an entity the
                # user can't read (#1425). Drop unresolved IR so the region renders
                # the clean "No metrics" empty state instead, mirroring
                # `compute_pipeline_steps`'s None-on-denied handling.
                metrics_list = [
                    {"label": sentence_case_words(str(name)), "key": str(name), "value": val}
                    for name, val in agg.items()
                    if not isinstance(val, (AggregateRef, DerivedMetricExpr))
                ]

        body: Fragment
        if not metrics_list:
            body = EmptyState(
                title="No metrics",
                description=getattr(region, "empty_message", None) or "No metrics declared.",
            )
            return _wrap_surface(title, "dashboard", body)

        drill_url = str(ctx.get("metrics_drill_url") or "")
        tiles: list[object] = []
        for m in metrics_list:
            if not isinstance(m, dict):
                continue
            tile = _metric_tile_from_dict(m, drill_url)
            if tile is not None:
                tiles.append(tile)

        if not tiles:
            body = EmptyState(title="No metrics", description="No metric tiles produced.")
        else:
            body = MetricsGrid(tiles=tuple(tiles))

        return _wrap_surface(title, "dashboard", body)
