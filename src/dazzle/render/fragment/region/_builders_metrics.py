"""Metrics-family region builders.

Houses the 4 metrics-family builders. All four share the dashboard
Surface kind and tile/list/bar/stage-row shapes:

  - _build_metrics         MetricsGrid of MetricTile primitives
  - _build_status_list     vertical icon + title + caption + pill rows
  - _build_progress        <progress> header + StageBar chip list
  - _build_pipeline_steps  horizontal stage cards with arrow connectors

No family-local helpers — all cross-cutting plumbing lives in `_shared`.

See issue #1065 for the full decomposition plan.
"""

from __future__ import annotations

from typing import Any, Literal

from dazzle.render.fragment import (
    EmptyState,
    Fragment,
    MetricsGrid,
    MetricTile,
    PipelineStage,
    PipelineSteps,
    StageBar,
    StatusList,
    StatusListEntry,
    Surface,
)
from dazzle.render.fragment.region._shared import (
    _region_title,
    _wrap_surface,
)


class _BuildersMetricsMixin:
    """Mixin adding the 4 metrics-family `_build_*` methods to
    `WorkspaceRegionAdapter`. Same pattern as `_BuildersChartsMixin`.
    """

    def _build_pipeline_steps(self, region: Any, ctx: dict[str, Any]) -> Surface:
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
                # value: None preserved (renders as "—"); coerce to int else.
                value: int | None
                value_raw = entry.get("value")
                if value_raw is None:
                    value = None
                else:
                    try:
                        value = int(value_raw)
                    except (TypeError, ValueError):
                        value = None
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

    def _build_progress(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: progress` renders a `<progress>` header + chip list
        of stages. Phase 4B.1.b uses the typed StageBar primitive
        matching the legacy `workspace/regions/progress.html` shape.

        ctx shape (primary):
            stage_counts: list of dicts {"name": str, "count": int,
                "complete": bool} — pre-computed per-stage rollups
            complete_pct: float (0..100) — percentage for the header bar
            complete_count: int — for the "N of M complete" summary
            progress_total: int — denominator for the summary; 0 omits it

        ctx shape (legacy fallback, Phase 4A):
            items: list of dicts {"label": str, "percent": int 0..100}
                — fallback-rendered as one synthetic stage per row with
                `complete = (percent == 100)`. The Phase 4B.2 translator
                will replace this with the primary path.
        """
        title = _region_title(region)
        stage_counts = ctx.get("stage_counts") or []

        stages: list[tuple[str, int, bool]] = []
        for entry in stage_counts:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or entry.get("label") or "")
            if not name:
                continue
            try:
                count = int(entry.get("count") or 0)
            except (TypeError, ValueError):
                count = 0
            complete = bool(entry.get("complete"))
            stages.append((name, count, complete))

        # Legacy fallback — items: [{label, percent}]
        if not stages:
            for entry in ctx.get("items") or []:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("label") or entry.get("name") or "")
                if not name:
                    continue
                try:
                    percent = int(entry.get("percent") or entry.get("value") or 0)
                except (TypeError, ValueError):
                    percent = 0
                percent = max(0, min(100, percent))
                stages.append((f"{name} ({percent}%)", percent, percent == 100))

        body: Fragment
        if not stages:
            body = EmptyState(
                title="No progress",
                description=getattr(region, "empty_message", None) or "No data in this region.",
            )
            return _wrap_surface(title, "list", body)

        try:
            complete_pct = float(ctx.get("complete_pct") or 0)
        except (TypeError, ValueError):
            complete_pct = 0.0
        complete_pct = max(0.0, min(100.0, complete_pct))
        try:
            complete_count = int(ctx.get("complete_count") or 0)
        except (TypeError, ValueError):
            complete_count = 0
        try:
            total = int(ctx.get("progress_total") or 0)
        except (TypeError, ValueError):
            total = 0

        body = StageBar(
            stages=tuple(stages),
            complete_pct=complete_pct,
            complete_count=complete_count,
            total=total,
        )
        return _wrap_surface(title, "list", body)

    def _build_status_list(self, region: Any, ctx: dict[str, Any]) -> Surface:
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

    def _build_metrics(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: metrics` (and `summary`) regions render a row of
        MetricTile primitives — one per declared aggregate. Phase 4B.1.a
        replaced KPI with MetricTile so the legacy template's extended
        delta block (delta_pct, delta_period_label, delta_sentiment,
        per-tile tone) is preserved on the typed-Fragment path.

        Values are passed through `_metric_number_filter` (K/M-suffix
        formatting) before reaching the primitive — same string the
        Jinja path produces.

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
            (legacy) aggregates: dict[name → resolved value], used as
                fallback when metrics list isn't supplied
        """
        from dazzle.render.filters import _metric_number_filter

        title = _region_title(region)
        metrics_list: list[dict[str, Any]] = ctx.get("metrics", []) or []
        if not metrics_list:
            agg = ctx.get("aggregates") or getattr(region, "aggregates", {}) or {}
            if isinstance(agg, dict):
                metrics_list = [
                    {"label": str(name).replace("_", " ").title(), "value": val}
                    for name, val in agg.items()
                ]

        body: Fragment
        if not metrics_list:
            body = EmptyState(
                title="No metrics",
                description=getattr(region, "empty_message", None) or "No metrics declared.",
            )
            return _wrap_surface(title, "dashboard", body)

        tiles: list[object] = []
        for m in metrics_list:
            if not isinstance(m, dict):
                continue
            label = str(m.get("label") or m.get("name") or "")
            if not label:
                continue
            value_str = _metric_number_filter(m.get("value"))

            tone_raw = str(m.get("tone") or "")
            tone: Literal["", "positive", "warning", "destructive", "accent", "neutral"] = (
                tone_raw  # type: ignore[assignment]
                if tone_raw in ("", "positive", "warning", "destructive", "accent", "neutral")
                else ""
            )
            direction_raw = str(m.get("delta_direction") or "")
            direction: Literal["", "up", "down", "flat"] = (
                direction_raw  # type: ignore[assignment]
                if direction_raw in ("", "up", "down", "flat")
                else ""
            )
            sentiment_raw = str(m.get("delta_sentiment") or "")
            sentiment: Literal["", "positive_up", "positive_down"] = (
                sentiment_raw  # type: ignore[assignment]
                if sentiment_raw in ("", "positive_up", "positive_down")
                else ""
            )
            try:
                delta_pct = float(m.get("delta_pct") or 0)
            except (TypeError, ValueError):
                delta_pct = 0.0

            tiles.append(
                MetricTile(
                    label=label,
                    value=value_str,
                    tone=tone,
                    delta_direction=direction,
                    delta_sentiment=sentiment,
                    delta_value=str(m.get("delta") or ""),
                    delta_pct=delta_pct,
                    delta_period_label=str(m.get("delta_period_label") or ""),
                )
            )

        if not tiles:
            body = EmptyState(title="No metrics", description="No metric tiles produced.")
        else:
            body = MetricsGrid(tiles=tuple(tiles))

        return _wrap_surface(title, "dashboard", body)
