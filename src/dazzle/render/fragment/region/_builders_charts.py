"""Chart-family region builders.

Houses the chart builders that share the `_parse_reference_lines` /
`_parse_reference_bands` helpers and the same Surface-wrapping pattern:

  - _build_radar           radar polar profile (≥3 axes)
  - _build_line_chart      time-series line (single or overlaid series)
  - _build_diagram         Mermaid ER diagram (with structural fallback)
  - _build_comparison      ranked league (bar-track rows + outlier flags)
  - _build_insight_summary deterministic grounded narrative
  - _build_bar_chart       classic categorical bars

The dispatch tables stay in `_dispatcher.py`; this module only exposes
the mixin (consumed via class inheritance) and the two parsers (used
only by chart builders). All methods rely on `self.<...>` only for
cross-family calls — none currently exist — so the mixin works
without circular-import concerns.

See issue #1065 for the full decomposition plan.
"""

from __future__ import annotations

import math
from html import escape as _html_escape
from typing import Any, Literal

from dazzle.render.filters import (
    clerk_chart_axis_label,
    clerk_stage_label,
)
from dazzle.render.fragment import (
    BarChart,
    BarTrack,
    Diagram,
    EmptyState,
    Fragment,
    Radar,
    RawHTML,
    ReferenceBand,
    ReferenceLine,
    Stack,
    Surface,
    Text,
    TimeSeries,
    TimeSeriesSeries,
)
from dazzle.render.fragment.region._context import RegionContext
from dazzle.render.fragment.region._shared import (
    _chart_empty_title,
    _region_title,
    _wrap_surface,
)


def _parse_reference_lines(raw: Any) -> tuple[ReferenceLine, ...]:
    """Defensive parser — turn ctx['reference_lines'] into a tuple of
    typed ReferenceLine primitives. Unknown styles fall back to solid;
    non-numeric values silently drop."""
    if not isinstance(raw, list):
        return ()
    out: list[ReferenceLine] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            value = float(entry.get("value") or 0)
        except (TypeError, ValueError):
            continue
        style_raw = str(entry.get("style") or "solid")
        style: Literal["solid", "dashed", "dotted"] = (
            style_raw  # type: ignore[assignment]
            if style_raw in ("solid", "dashed", "dotted")
            else "solid"
        )
        out.append(ReferenceLine(value=value, label=str(entry.get("label") or ""), style=style))
    return tuple(out)


def _parse_reference_bands(raw: Any) -> tuple[ReferenceBand, ...]:
    """Defensive parser — accepts both `from`/`to` and `from_value`/
    `to_value` key shapes; bands with from > to silently drop;
    unknown colors fall back to target."""
    if not isinstance(raw, list):
        return ()
    out: list[ReferenceBand] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            from_val = float(entry.get("from") or entry.get("from_value") or 0)
            to_val = float(entry.get("to") or entry.get("to_value") or 0)
        except (TypeError, ValueError):
            continue
        if from_val > to_val:
            continue
        color_raw = str(entry.get("color") or "target")
        color: Literal["target", "positive", "warning", "destructive", "muted"] = (
            color_raw  # type: ignore[assignment]
            if color_raw in ("target", "positive", "warning", "destructive", "muted")
            else "target"
        )
        out.append(
            ReferenceBand(
                from_value=from_val,
                to_value=to_val,
                label=str(entry.get("label") or ""),
                color=color,
            )
        )
    return tuple(out)


def _coerce_series_points(raw_points: Any) -> list[tuple[str, float]]:
    """Coerce a series' raw points to `(label, value)` tuples.

    Accepts `(label, value)` tuples/lists or `{label|x, value|y}` dicts —
    the two shapes the orchestration emits for time-series buckets. Shared
    by the single-series (`points`) and multi-series (`series`) paths."""
    out: list[tuple[str, float]] = []
    for entry in raw_points or []:
        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
            try:
                out.append((str(entry[0]), float(entry[1])))
            except (TypeError, ValueError):
                continue
        elif isinstance(entry, dict):
            label = str(entry.get("label") or entry.get("x") or "")
            try:
                val = float(entry.get("value") or entry.get("y") or 0)
            except (TypeError, ValueError):
                val = 0.0
            if label:
                out.append((label, val))
    return out


def _fmt_num(v: object) -> str:
    """Format a cited value: ints bare, floats at 2dp (3 sig-figs for tiny non-zero)."""
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(v)
    if f == int(f):
        return str(int(f))
    return f"{f:.3g}" if 0 < abs(f) < 0.005 else f"{f:.2f}"


_CONFIDENCE_TONE = {"high": "positive", "medium": "warning", "low": "neutral"}


def _stored_insight_card(title: str, stored: Any, nar: Any) -> Surface:
    """Render a stored (pre-computed) narrative overlay over the deterministic
    grounding: prose, then the cited values + a confidence badge + 'as of'
    freshness. The citations come from the deterministic narrative, so the prose
    is always verifiable against the real numbers beneath it (#1470 Slice 2a)."""
    from html import escape as _esc

    children: list[Fragment] = [
        Text(body=str(line)) for line in (getattr(stored, "prose", ()) or ())
    ]
    citations = getattr(nar, "citations", ()) or ()
    if citations:
        cite_str = " · ".join(f"{lbl} {_fmt_num(val)}" for lbl, val in citations)
        children.append(Text(body=f"Based on: {cite_str}", tone="muted"))
    conf = str(getattr(stored, "confidence", "") or "")
    tone = _CONFIDENCE_TONE.get(conf, "neutral")
    children.append(
        RawHTML(
            f'<span class="dz-badge dz-badge-sm" data-dz-tone="{tone}" role="status" '
            f'aria-label="Confidence: {_esc(conf)}">confidence: {_esc(conf)}</span>'
        )
    )
    children.append(
        Text(
            body=f"{getattr(nar, 'scope', '')} · as of {getattr(stored, 'generated_at', '')}".strip(
                " ·"
            ),
            tone="muted",
        )
    )
    return _wrap_surface(title, "report", Stack(children=tuple(children), gap="sm"))


def _comparison_track_rows(raw_rows: Any) -> list[tuple[str, float, str, float]]:
    """Coerce ctx['comparison_rows'] into BarTrack `(label, value, formatted, fill_pct)`.

    The label carries the rank prefix; the formatted value carries the
    format-layer string plus an outlier badge (``⚠ low``/``⚠ high``). All
    strings are escaped at emit time by the BarTrack renderer — no escaping
    here. Malformed entries silently drop (the dashboard never crashes on a
    bad row). #1470.
    """
    rows: list[tuple[str, float, str, float]] = []
    if not isinstance(raw_rows, list):
        return rows
    for entry in raw_rows:
        if not isinstance(entry, dict):
            continue
        base_label = str(entry.get("label") or "")
        if not base_label:
            continue
        raw_value = entry.get("value")
        try:
            value = float(raw_value) if raw_value is not None else 0.0
            fraction = float(entry.get("bar_fraction") or 0)
        except (TypeError, ValueError):
            continue
        # IEEE inf/nan would crash BarTrack's `_num()` (int(inf) → OverflowError)
        # and its fill_pct invariant; drop the row rather than the whole region.
        if not math.isfinite(value):
            continue
        if not math.isfinite(fraction):
            fraction = 0.0
        rank = entry.get("rank")
        label = f"{rank}. {base_label}" if rank is not None else base_label
        # Whole counts stay bare (12, not 12.00). format_cell("text") on a
        # float dumps two-decimal theater (oral #153). Leftover labels stay put.
        formatted = _fmt_num(raw_value) if raw_value is not None else "—"
        outlier = entry.get("outlier")
        if outlier in ("low", "high"):
            formatted = f"{formatted} ⚠ {outlier}"
        fill_pct = max(0.0, min(100.0, fraction * 100.0))
        rows.append((label, value, formatted, fill_pct))
    return rows


class _BuildersChartsMixin:
    """Mixin adding the chart-family `_build_*` methods to
    `WorkspaceRegionAdapter`.

    Mixin-not-subclass so the public class (`WorkspaceRegionAdapter`)
    stays the single import path for external callers. The other 5
    family mixins (cards/tables/timeline/metrics/misc) follow the same
    pattern across subsequent PRs against #1065.
    """

    def _build_radar(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: radar` regions render as a Radar polar profile.

        ctx shape:
            axes: list of (label, value) tuples or {axis, value} dicts
            chart_label: optional override
        """
        title = _region_title(region)
        chart_label = str(ctx.get("chart_label") or title or "Radar")
        raw_axes = ctx.get("axes") or []
        axes: list[tuple[str, float]] = []
        for entry in raw_axes:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                try:
                    raw_label = entry[0]
                    shown = clerk_chart_axis_label(raw_label) or str(raw_label)
                    axes.append((shown, float(entry[1])))
                except (TypeError, ValueError):
                    continue
            elif isinstance(entry, dict):
                raw_label = entry.get("axis") or entry.get("label") or ""
                shown = clerk_chart_axis_label(raw_label) or str(raw_label)
                try:
                    val = float(entry.get("value") or 0)
                except (TypeError, ValueError):
                    val = 0.0
                if shown:
                    axes.append((shown, val))

        body: Fragment
        # Radar primitive requires ≥3 axes; fewer collapses to a line.
        # Adapter degrades to EmptyState rather than crashing.
        if len(axes) < 3:
            body = EmptyState(
                title=_chart_empty_title(region, ctx),
                description=getattr(region, "empty_message", None)
                or "Radar requires at least 3 axes.",
            )
        else:
            body = Radar(label=chart_label, axes=tuple(axes))

        return _wrap_surface(title, "report", body)

    def _build_line_chart(self, region: Any, ctx: RegionContext) -> Surface:
        """Render a TimeSeries primitive as a line chart.

        ctx shape:
            points: list of (label, value) tuples or {label, value} /
                {x, y} dicts — pre-aggregated by the runtime
            chart_label: optional override
            reference_lines: list of dicts {value, label, style} — Phase
                4B.1.b. Style is one of solid/dashed/dotted; unknown
                styles fall back to solid.
            reference_bands: list of dicts {from, to, label, color}.
                `color` is one of target/positive/warning/destructive/
                muted; unknown colors fall back to target. Bands with
                from > to silently drop.
        """
        title = _region_title(region)
        chart_label = str(ctx.get("chart_label") or title or "Line")

        body: Fragment

        # Multi-series path (#883): `series` is a list of {name, points}
        # shaped by the adapter from bucketed_metrics + overlay_series_data.
        raw_series: Any = ctx.get("series") or []
        if raw_series:
            series: list[TimeSeriesSeries] = []
            for s in raw_series:
                if not isinstance(s, dict):
                    continue
                s_points = _coerce_series_points(s.get("points") or [])
                if s_points:
                    series.append(
                        TimeSeriesSeries(name=str(s.get("name") or ""), points=tuple(s_points))
                    )
            if series:
                body = TimeSeries(
                    label=chart_label,
                    view="line",
                    series=tuple(series),
                    reference_lines=_parse_reference_lines(ctx.get("reference_lines")),
                    reference_bands=_parse_reference_bands(ctx.get("reference_bands")),
                )
                return _wrap_surface(title, "report", body)

        points = _coerce_series_points(ctx.get("points") or [])

        if not points:
            body = EmptyState(
                title=_chart_empty_title(region, ctx),
                description=getattr(region, "empty_message", None) or "No points to plot.",
            )
            return _wrap_surface(title, "report", body)

        ref_lines = _parse_reference_lines(ctx.get("reference_lines"))
        ref_bands = _parse_reference_bands(ctx.get("reference_bands"))

        body = TimeSeries(
            label=chart_label,
            points=tuple(points),
            view="line",
            reference_lines=ref_lines,
            reference_bands=ref_bands,
        )
        return _wrap_surface(title, "report", body)

    def _build_diagram(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: diagram` renders an entity-relationship diagram via
        the Diagram primitive.

        Phase 4B preferred: `ctx['diagram_data']` carries Mermaid syntax
        produced by `_build_diagram_data` in the workspace renderer; we
        forward it as `Diagram.mermaid_source` and the renderer emits
        a `<pre class="mermaid">` + Mermaid CDN loader script matching
        the legacy `workspace/regions/diagram.html` byte-for-byte.

        Phase 4A fallback (no `diagram_data`): construct a structural
        node/edge list from `ctx['nodes']` + `ctx['edges']`. Used by
        tests + any consumer that hasn't built a Mermaid source.
        """
        title = _region_title(region)
        mermaid_source = str(ctx.get("diagram_data") or "")
        # Legacy template hardcodes the empty-state copy — match it
        # verbatim for byte-equivalence rather than reading
        # region.empty_message.
        empty_message = "No entity relationships to display."

        if mermaid_source:
            body: Fragment = Diagram(mermaid_source=mermaid_source)
            return _wrap_surface(title, "report", body)

        nodes = tuple(str(n) for n in (ctx.get("nodes") or []) if n)
        if not nodes:
            # Empty branch matches the legacy template's literal markup
            # (`<p class="dz-diagram-empty">…</p>`) for byte-equivalence;
            # the generic dz-empty-state primitive emits different chrome.
            empty_html = f'<p class="dz-diagram-empty">{_html_escape(empty_message)}</p>'
            return _wrap_surface(title, "report", RawHTML(empty_html))

        raw_edges = ctx.get("edges") or ctx.get("relations") or []
        edges: list[tuple[str, str]] = []
        node_set = set(nodes)
        for entry in raw_edges:
            src: str = ""
            dst: str = ""
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                src, dst = str(entry[0]), str(entry[1])
            elif isinstance(entry, dict):
                src = str(entry.get("from") or entry.get("source") or "")
                dst = str(entry.get("to") or entry.get("target") or "")
            if src and dst and src in node_set and dst in node_set:
                edges.append((src, dst))

        return _wrap_surface(title, "report", Diagram(nodes=nodes, edges=tuple(edges)))

    def _build_comparison(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: comparison` renders a ranked league as labelled ARIA
        tracks: one row per ranked entry, the rank woven into the label,
        the metric value formatted via the format layer, an inline filled
        track (``bar_fraction``), and a ``⚠ low``/``⚠ high`` outlier badge
        on flagged rows. #1470.

        ctx shape:
            comparison_rows: list of dicts {"rank": int, "label": str,
                "value": float|None, "bar_fraction": float (0..1),
                "outlier": "low"|"high"|None} — pre-ranked + pre-flagged by
                the runtime (`build_comparison_rows`).
            comparison_max: float — scale endpoint (largest metric value).

        Empty rows degrade to EmptyState. Reuses the BarTrack primitive so
        the inline tracks share the dashboard's bar styling + ARIA semantics.
        """
        title = _region_title(region)
        try:
            max_value = float(ctx.get("comparison_max") or 0)
        except (TypeError, ValueError):
            max_value = 0.0
        # Guard non-finite (inf/nan → BarTrack `_num()` OverflowError) and ≤0.
        if not math.isfinite(max_value) or max_value <= 0:
            max_value = 1.0  # BarTrack invariant guard (fill_pct already clamped)

        rows = _comparison_track_rows(ctx.get("comparison_rows"))
        body: Fragment
        if not rows:
            body = EmptyState(
                title=_chart_empty_title(region, ctx),
                description=getattr(region, "empty_message", None) or "No data available.",
            )
        else:
            body = BarTrack(rows=tuple(rows), max_value=max_value)
        return _wrap_surface(title, "report", body)

    def _build_insight_summary(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: insight_summary` renders a deterministic grounded narrative
        (scale + leader + outlier) above a trust block (the cited values + scope +
        a 'Computed' badge). All strings escaped at emit by the Text primitive. #1470.
        """
        title = _region_title(region)
        nar = ctx.get("insight_narrative")
        lines = tuple(getattr(nar, "lines", ()) or ())
        if not lines:
            return _wrap_surface(
                title,
                "report",
                EmptyState(
                    title="No insight",
                    description=getattr(region, "empty_message", None) or "No data to summarise.",
                ),
            )

        # #1470 Slice 2a: a stored (pre-computed) narrative overlays the
        # deterministic facts; fall back to the deterministic narrative when none.
        stored = ctx.get("stored_insight")
        if getattr(stored, "prose", None):
            return _stored_insight_card(title, stored, nar)

        children: list[Fragment] = [Text(body=str(line)) for line in lines]
        citations = getattr(nar, "citations", ()) or ()
        if citations:
            cite_str = " · ".join(f"{lbl} {_fmt_num(val)}" for lbl, val in citations)
            children.append(Text(body=f"Based on: {cite_str}", tone="muted"))
        footer = f"{getattr(nar, 'scope', '')} · {getattr(nar, 'badge', '')}".strip(" ·")
        children.append(Text(body=footer, tone="muted"))
        return _wrap_surface(title, "report", Stack(children=tuple(children), gap="sm"))

    def _build_bar_chart(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: bar_chart` regions render as a BarChart primitive
        — list of (label, count) tuples derived from the region's
        group_by aggregation.

        ctx shape:
            buckets: list[(str, int)] — pre-aggregated by the runtime
            (legacy) items + group_by_field as fallback
            chart_label: optional override for the BarChart label
        """
        title = _region_title(region)
        chart_label = str(ctx.get("chart_label") or title or "Chart")
        raw_buckets = ctx.get("buckets") or []
        buckets: list[tuple[str, int]] = []
        for entry in raw_buckets:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                try:
                    raw_label = entry[0]
                    shown = clerk_stage_label(raw_label) or str(raw_label)
                    buckets.append((shown, int(entry[1])))
                except (TypeError, ValueError):
                    continue
            elif isinstance(entry, dict):
                raw_label = entry.get("label") or entry.get("key") or ""
                shown = clerk_stage_label(raw_label) or str(raw_label)
                try:
                    val = int(entry.get("value") or entry.get("count") or 0)
                except (TypeError, ValueError):
                    val = 0
                if shown:
                    buckets.append((shown, val))

        body: Fragment
        if not buckets:
            body = EmptyState(
                title=_chart_empty_title(region, ctx),
                description=getattr(region, "empty_message", None) or "No buckets to chart.",
            )
        else:
            body = BarChart(
                label=chart_label,
                buckets=tuple(buckets),
                reference_lines=_parse_reference_lines(ctx.get("reference_lines")),
                reference_bands=_parse_reference_bands(ctx.get("reference_bands")),
            )

        return _wrap_surface(title, "report", body)
