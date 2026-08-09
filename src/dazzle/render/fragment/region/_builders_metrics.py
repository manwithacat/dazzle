"""Metrics-family region builders.

Houses the 4 metrics-family builders. All four share the dashboard
Surface kind and tile/list/bar/stage-row shapes:

  - _build_metrics         MetricsGrid of MetricTile primitives
  - _build_status_list     vertical icon + title + caption + pill rows
  - _build_accordion       exclusive details group (FAQ / section disclosure)
  - _build_carousel        media stage strip with prev/next/dots
  - _build_map             map plan board of Marker pin chrome
  - _build_progress        <progress> header + StageBar chip list
  - _build_progress_bar    HM progress hyperpart — toned determinate .dz-progress
  - _build_pipeline_steps  horizontal stage cards with arrow connectors

No family-local helpers — all cross-cutting plumbing lives in `_shared`.

See issue #1065 for the full decomposition plan.
"""

from __future__ import annotations

from typing import Any, Literal

from dazzle.core.ir import AggregateRef, DerivedMetricExpr
from dazzle.render.fragment import (
    Accordion,
    AccordionItem,
    Carousel,
    CarouselSlide,
    EmptyState,
    Fragment,
    MapBoard,
    Marker,
    MetricsGrid,
    MetricTile,
    PipelineStage,
    PipelineSteps,
    Stack,
    StageBar,
    StatusList,
    StatusListEntry,
    Surface,
)
from dazzle.render.fragment.region._context import RegionContext
from dazzle.render.fragment.region._progress_bar import (
    progress_bars_from_entries,
    progress_bars_from_items,
)
from dazzle.render.fragment.region._shared import (
    _region_title,
    _wrap_surface,
)

_CAROUSEL_MEDIA_KEYS = ("preview_url", "logo_url", "photo_url", "image_url", "src")
_MAP_LABEL_KEYS = (
    "location",
    "city",
    "site",
    "region",
    "place",
    "address",
    "name",
    "title",
    "label",
)
_MAP_TONE_BY_STATUS: dict[str, str] = {
    "active": "success",
    "online": "success",
    "ok": "success",
    "healthy": "success",
    "warning": "warning",
    "degraded": "warning",
    "prototype": "warning",
    "pending": "warning",
    "danger": "danger",
    "critical": "danger",
    "recalled": "danger",
    "alert": "danger",
    "error": "danger",
    "failed": "danger",
}


def _carousel_src_from_item(item: dict[str, Any]) -> str:
    for key in _CAROUSEL_MEDIA_KEYS:
        val = item.get(key)
        if val:
            return str(val)
    return ""


def _stable_map_xy(key: str) -> tuple[float, float]:
    """Deterministic placement in the inner 12–88% band (avoid canvas edges)."""
    h = 0
    for ch in key:
        h = (h * 33 + ord(ch)) & 0xFFFFFFFF
    x = 12.0 + (h % 7600) / 100.0  # 12..88
    y = 12.0 + ((h // 7600) % 7600) / 100.0
    return x, y


def _map_tone_from_status(status: str) -> str:
    return _MAP_TONE_BY_STATUS.get(str(status).strip().lower(), "")


def _map_label_from_item(item: dict[str, Any]) -> str:
    for key in _MAP_LABEL_KEYS:
        val = item.get(key)
        if val not in (None, "", "—"):
            return str(val).strip()
    return ""


def _map_markers_from_items(items: list[Any]) -> list[Marker]:
    markers: list[Marker] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        label = _map_label_from_item(raw)
        if not label:
            continue
        status = str(raw.get("status") or raw.get("state") or raw.get("tone") or "")
        tone = _map_tone_from_status(status) if status else ""
        if status and status.lower() in ("success", "warning", "danger"):
            tone = status.lower()
        title = str(raw.get("name") or raw.get("title") or label)
        # Prefer distinct seed for placement so same location still fans out by id.
        seed = str(raw.get("id") or raw.get("serial_number") or title or label)
        x, y = _stable_map_xy(seed)
        markers.append(
            Marker(label=label[:40], tone=tone, x_pct=x, y_pct=y, title=title)  # type: ignore[arg-type]
        )
    return markers


def _entry_field(raw: Any, *names: str) -> str:
    """First non-empty field from a status-entry dict or IR object."""
    for name in names:
        if isinstance(raw, dict):
            val = raw.get(name)
        else:
            val = getattr(raw, name, None)
        if val not in (None, "", "—"):
            return str(val).strip()
    return ""


def _coerce_marker_tone(raw: str) -> str:
    if raw in ("success", "warning", "danger"):
        return raw
    return _map_tone_from_status(raw)


def _map_markers_from_entries(entries: list[Any]) -> list[Marker]:
    markers: list[Marker] = []
    for i, raw in enumerate(entries):
        label = _entry_field(raw, "title", "label")
        if not label:
            continue
        tone = _coerce_marker_tone(_entry_field(raw, "caption", "body", "tone"))
        size_raw = _entry_field(raw, "icon", "size").lower()
        size = "lg" if size_raw in ("lg", "large") else ""
        x, y = _stable_map_xy(f"{i}:{label}")
        markers.append(
            Marker(label=label[:40], tone=tone, size=size, x_pct=x, y_pct=y, title=label)  # type: ignore[arg-type]
        )
    return markers


def _carousel_slides_from_items(items: list[Any]) -> list[CarouselSlide]:
    slides: list[CarouselSlide] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        src = _carousel_src_from_item(item)
        if not src:
            continue
        alt = str(
            item.get("name") or item.get("title") or item.get("label") or item.get("alt") or "Slide"
        )
        chip = str(item.get("chip") or item.get("asset_type") or "")
        slides.append(CarouselSlide(src=src, alt=alt, chip=chip))
    return slides


def _carousel_slides_from_entries(raw_entries: list[Any]) -> list[CarouselSlide]:
    slides: list[CarouselSlide] = []
    for raw in raw_entries:
        if not isinstance(raw, dict):
            continue
        entry_title = str(raw.get("title") or raw.get("alt") or "")
        src = str(raw.get("body") or raw.get("caption") or raw.get("src") or "")
        chip = str(raw.get("icon") or raw.get("chip") or "")
        if src:
            slides.append(CarouselSlide(src=src, alt=entry_title or "Slide", chip=chip))
        elif entry_title:
            slides.append(
                CarouselSlide(
                    title=entry_title,
                    body=str(raw.get("body") or raw.get("caption") or ""),
                )
            )
    return slides


class _BuildersMetricsMixin:
    """Mixin adding the 4 metrics-family `_build_*` methods to
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

    def _build_progress(self, region: Any, ctx: RegionContext) -> Surface:
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

    def _build_accordion(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: accordion` regions render HM Accordion of exclusive details.

        Reuses authored ``status_entries`` (``entries:`` block): ``title`` is
        the summary trigger; ``caption`` is the panel body (agent-facing
        synonym for body copy). First entry starts open for progressive
        disclosure; remaining stay closed. Shared ``name=`` uses region name.
        """
        title = _region_title(region)
        raw_entries = ctx.get("status_entries") or []
        items: list[AccordionItem] = []
        for i, raw in enumerate(raw_entries):
            if not isinstance(raw, dict):
                continue
            entry_title = str(raw.get("title") or "")
            if not entry_title:
                continue
            body = str(raw.get("body") or raw.get("caption") or "")
            items.append(
                AccordionItem(
                    title=entry_title,
                    body=body,
                    open=(i == 0),
                )
            )
        empty_msg = (
            ctx.get("empty_message") or getattr(region, "empty_message", None) or "No panels."
        )
        region_name = str(getattr(region, "name", None) or "acc")
        # Stable HTML name token for exclusive group
        name = "dz-acc-" + "".join(c if c.isalnum() else "-" for c in region_name)
        body_frag: Fragment = Accordion(
            items=tuple(items),
            name=name,
            empty_message=str(empty_msg),
        )
        return _wrap_surface(title, "list", body_frag)

    def _build_carousel(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: carousel` regions render HM Carousel media stage.

        Prefer entity rows with media URL fields (``preview_url`` /
        ``logo_url`` / ``photo_url`` / ``image_url``). Fall back to authored
        ``entries:`` where ``title`` is alt text and ``caption``/``body`` is
        the image URL (optional ``icon`` as aspect chip). Clamp wrap default.
        """
        title = _region_title(region)
        slides = _carousel_slides_from_items(list(ctx.get("items") or []))
        if not slides:
            slides = _carousel_slides_from_entries(list(ctx.get("status_entries") or []))
        empty_msg = (
            ctx.get("empty_message") or getattr(region, "empty_message", None) or "No slides."
        )
        label = title or str(getattr(region, "name", None) or "Gallery")
        body_frag: Fragment = Carousel(
            slides=tuple(slides),
            label=str(label),
            wrap="none",
            ratio="16/9",
            empty_message=str(empty_msg),
        )
        return _wrap_surface(title, "list", body_frag)

    def _build_map(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: map` — vendor-free plan board of HM Marker pins.

        Entity rows → pins (label from location/name; tone from status).
        Static ``entries:`` use title=label, caption/body=tone, icon=size.
        Placement is a stable hash of the label (no lat/lng / tile SDK).
        """
        title = _region_title(region)
        markers = _map_markers_from_items(list(ctx.get("items") or []))
        if not markers:
            markers = _map_markers_from_entries(list(ctx.get("status_entries") or []))
        empty_msg = (
            ctx.get("empty_message") or getattr(region, "empty_message", None) or "No locations."
        )
        label = title or str(getattr(region, "name", None) or "Map")
        body_frag: Fragment = MapBoard(
            markers=tuple(markers),
            label=str(label),
            empty_message=str(empty_msg),
        )
        return _wrap_surface(title, "list", body_frag)

    def _build_progress_bar(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: progress_bar` — HM Progress hyperpart (toned determinate bar).

        Distinct from ``display: progress`` (StageBar / progress-region).
        Static ``entries:``: title=label, caption/body=value (0..100),
        optional icon=tone (success|warning|destructive). Entity rows may
        supply ``percent`` / ``progress`` / ``value`` + name/title.
        """
        title = _region_title(region)
        bars = progress_bars_from_entries(list(ctx.get("status_entries") or []))
        if not bars:
            bars = progress_bars_from_items(list(ctx.get("items") or []))
        empty_msg = (
            ctx.get("empty_message") or getattr(region, "empty_message", None) or "No progress."
        )
        body_frag: Fragment
        if not bars:
            body_frag = EmptyState(
                title="No progress",
                description=str(empty_msg),
            )
        elif len(bars) == 1:
            body_frag = bars[0]
        else:
            body_frag = Stack(children=tuple(bars), gap="sm")
        return _wrap_surface(title, "dashboard", body_frag)

    def _build_metrics(self, region: Any, ctx: RegionContext) -> Surface:
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
                    {"label": str(name).replace("_", " ").title(), "value": val}
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
