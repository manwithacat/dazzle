"""Charts-family render mixin.

Houses the 16 chart primitives + the dedicated tree-node helper.
All SVG and special-purpose visualisations live here.

Also houses `_DIAGRAM_MERMAID_SCRIPT` — the inline Mermaid CDN loader
embedded by `_emit_diagram` when rendering ER diagrams.

All methods only call `self._emit(child, ctx)` for recursion (plus
`self._emit_tree_node` for the tree case — which lives in this mixin
too, so it's intra-family).

See issue #1064 for the full decomposition plan.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dazzle.render.fragment.context import RenderContext
from dazzle.render.fragment.icon_html import lucide_svg_html
from dazzle.render.fragment.ingest import BarChart as BarChartSeam
from dazzle.render.fragment.ingest import BarChartRow as BarChartRowSeam
from dazzle.render.fragment.ingest import BoxPlot as BoxPlotSeam
from dazzle.render.fragment.ingest import BoxPlotGroup as BoxPlotGroupSeam
from dazzle.render.fragment.ingest import Bullet as BulletSeam
from dazzle.render.fragment.ingest import BulletBand as BulletBandSeam
from dazzle.render.fragment.ingest import BulletRow as BulletRowSeam
from dazzle.render.fragment.ingest import Diagram as DiagramSeam
from dazzle.render.fragment.ingest import Funnel as FunnelSeam
from dazzle.render.fragment.ingest import FunnelStage as FunnelStageSeam
from dazzle.render.fragment.ingest import Heatmap as HeatmapSeam
from dazzle.render.fragment.ingest import HeatmapRow as HeatmapRowSeam
from dazzle.render.fragment.ingest import Histogram as HistogramSeam
from dazzle.render.fragment.ingest import HistogramBin as HistogramBinSeam
from dazzle.render.fragment.ingest import KanbanCard as KanbanCardSeam
from dazzle.render.fragment.ingest import Radar as RadarSeam
from dazzle.render.fragment.ingest import RadarAxis as RadarAxisSeam
from dazzle.render.fragment.ingest import Sparkline as SparklineSeam
from dazzle.render.fragment.ingest import TimelineEvent as TimelineEventSeam
from dazzle.render.fragment.ingest import TimeSeries as TimeSeriesSeam
from dazzle.render.fragment.ingest import TimeSeriesLayer as TimeSeriesLayerSeam
from dazzle.render.fragment.ingest import TimeSeriesPoint as TimeSeriesPointSeam
from dazzle.render.fragment.ingest import (
    render_bar_chart,
    render_box_plot,
    render_bullet,
    render_diagram,
    render_funnel,
    render_heatmap,
    render_histogram,
    render_kanban_card,
    render_radar,
    render_sparkline,
    render_time_series,
    render_timeline_event,
)
from dazzle.render.fragment.primitives import (
    BarChart,
    BoxPlot,
    Bullet,
    CalendarGrid,
    Diagram,
    Funnel,
    Heatmap,
    Histogram,
    KanbanBoard,
    KanbanRegion,
    PipelineSteps,
    Radar,
    Sparkline,
    Timeline,
    TimelineEvent,
    TimeSeries,
    Tree,
    TreeNode,
)

if TYPE_CHECKING:
    from dazzle.render.fragment.primitives import Fragment


# Mermaid CDN loader script — emitted byte-for-byte by `_emit_diagram`
# when a `Diagram(mermaid_source=...)` is rendered. Keeps the version
# pin + SRI hash + comments aligned with the legacy template; bumping
# the pinned Mermaid version means updating BOTH this string and the
# legacy template (the dual-path test will catch any drift).
_DIAGRAM_MERMAID_SCRIPT = (
    "<script>\n"
    '    if (typeof mermaid === "undefined") {\n'
    '      var s = document.createElement("script");\n'
    "      // Pinned version + SRI hash (#830 Phase 1 of external-resource hardening).\n"
    "      // Hash regenerated when the pinned version is bumped — `curl -sL <url> |\n"
    "      // openssl dgst -sha384 -binary | openssl base64 -A`.\n"
    '      s.src = "https://cdn.jsdelivr.net/npm/mermaid@11.14.0/dist/mermaid.min.js";\n'
    '      s.integrity = "sha384-1CMXl090wj8Dd6YfnzSQUOgWbE6suWCaenYG7pox5AX7apTpY3PmJMeS2oPql4Gk";\n'
    '      s.crossOrigin = "anonymous";\n'
    "      s.onload = function () {\n"
    '        mermaid.initialize({ startOnLoad: true, theme: "neutral" });\n'
    "        mermaid.run();\n"
    "      };\n"
    "      document.head.appendChild(s);\n"
    "    } else {\n"
    "      mermaid.run();\n"
    "    }\n"
    "  </script>"
)


class _RenderChartsMixin:
    """Mixin adding the 16 charts-family `_emit_*` methods (and the
    private `_emit_tree_node` helper) to `FragmentRenderer`. Same
    pattern as the other render mixins.
    """

    if TYPE_CHECKING:

        def _emit(self, fragment: Fragment, ctx: RenderContext) -> str: ...

    def _emit_bar_chart(self, b: BarChart, ctx: RenderContext) -> str:
        """Render a BarChart via HM dual-lock BarChart seam.

        Bucket labels still use status-badge HTML (product path); widths
        are computed here and passed into the seam model.
        """
        from dazzle.render.fragment.region import (
            _render_status_badge_html,
        )

        if not b.buckets:
            return render_bar_chart(BarChartSeam(rows=[]))

        max_val = max((c for _, c in b.buckets), default=1) or 1
        rows = [
            BarChartRowSeam(
                label=str(label),
                count=int(count),
                width_pct=int(count / max_val * 100),
                label_html=_render_status_badge_html(label, size="sm"),
            )
            for label, count in b.buckets
        ]
        return render_bar_chart(BarChartSeam(rows=rows))

    def _emit_timeline(self, t: Timeline, ctx: RenderContext) -> str:
        """Render a Timeline via HM dual-lock TimelineEvent seams.

        Region chrome / overflow stay local; each item maps through
        ``render_timeline_event`` so markup matches ``contracts/timeline.py``.
        """
        # Coerce Phase 4A `(label, iso-date)` tuples for uniformity.
        events_norm: list[TimelineEvent] = []
        for evt in t.events:
            if isinstance(evt, TimelineEvent):
                events_norm.append(evt)
            elif isinstance(evt, tuple) and len(evt) == 2:
                label, when = evt
                events_norm.append(TimelineEvent(title=str(label), date_label=str(when)))

        if not events_norm:
            return (
                f'<div class="dz-timeline-region">'
                f'<p class="dz-empty-dense" role="status">'
                f"{ctx.escape(t.empty_message)}</p>"
                f"</div>"
            )

        items: list[str] = []
        for evt in events_norm:
            fields_html = ""
            for label, value in evt.fields:
                if isinstance(value, str):
                    value_html = ctx.escape(value)
                else:
                    value_html = self._emit(value, ctx)  # type: ignore[arg-type]
                fields_html += (
                    f'<p class="dz-timeline-field">'
                    f"<span>{ctx.escape(label)}:</span> "
                    f"{value_html}"
                    f"</p>"
                )
            items.append(
                render_timeline_event(
                    TimelineEventSeam(
                        title=evt.title,
                        date_label=evt.date_label,
                        fields_html=fields_html,
                    )
                )
            )

        overflow_html = ""
        if t.total > len(events_norm):
            overflow_html = (
                f'<p class="dz-timeline-overflow">Showing {len(events_norm)} of {t.total}</p>'
            )

        return (
            f'<div class="dz-timeline-region">'
            f'<ul class="dz-timeline-list">{"".join(items)}</ul>'
            f"{overflow_html}"
            f"</div>"
        )

    def _emit_kanban_board(self, k: KanbanBoard, ctx: RenderContext) -> str:
        cols = "".join(
            f'<div class="dz-kanban__column" data-dz-key="{ctx.escape_attr(key)}">'
            + "".join(self._emit(item, ctx) for item in items)  # type: ignore[arg-type]
            + "</div>"
            for key, items in k.columns
        )
        return f'<div class="dz-kanban">{cols}</div>'

    def _emit_calendar_grid(self, c: CalendarGrid, ctx: RenderContext) -> str:
        cls = f"dz-calendar dz-calendar--view-{c.view}"
        events = "".join(
            f'<li class="dz-calendar__event">'
            f'<time datetime="{ctx.escape_attr(when)}">{ctx.escape(when)}</time> '
            f"{ctx.escape(label)}"
            f"</li>"
            for label, when in c.events
        )
        return f'<div class="{cls}"><ul>{events}</ul></div>'

    def _emit_diagram(self, d: Diagram, ctx: RenderContext) -> str:
        """Render an entity-relationship diagram.

        Phase 4B.4 wave 4 (v0.66.118) — two modes:

        Mermaid mode (`mermaid_source` non-empty): emit `<pre class="mermaid">`
        carrying the raw Mermaid syntax + the legacy Mermaid CDN loader
        script. Byte-equivalent to the legacy `diagram.html` template.

        Structural mode (`mermaid_source` empty): nodes as labelled `<li>`
        boxes and edges as `from → to` rows (Phase 4A fallback,
        retained for tests and any consumer that hasn't built Mermaid
        source).
        """
        if d.mermaid_source:
            return (
                render_diagram(DiagramSeam(mermaid_source=d.mermaid_source))
                + _DIAGRAM_MERMAID_SCRIPT
            )
        return render_diagram(
            DiagramSeam(
                nodes=list(d.nodes),
                edges=list(d.edges),
            )
        )

    def _emit_time_series(self, t: TimeSeries, ctx: RenderContext) -> str:
        """Render line/area via HM dual-lock TimeSeries seam.

        SVG geometry stays in ``dazzle.render.svg.time_series_svg``; the
        seam carries trusted SVG (+ multi-series legend HTML).
        """
        from dazzle.render.svg import _series_color, time_series_svg

        # Sparkline view is dual-locked via the Sparkline primitive; this
        # path still accepts view="sparkline" for legacy TimeSeries callers
        # and maps it to the line wrapper class (pre-existing behaviour).
        view = t.view if t.view in ("line", "area") else "line"

        if t.series:
            series_pairs = tuple((s.name, s.points) for s in t.series)
            all_vals = [v for _n, pts in series_pairs for _l, v in pts]
            max_val = max(all_vals, default=1) or 1
            max_val_str = str(int(max_val)) if max_val == int(max_val) else str(max_val)
            svg = time_series_svg(
                t.label,
                (),
                view=view,
                series=series_pairs,
                reference_lines=t.reference_lines,
                reference_bands=t.reference_bands,
            )
            legend_items = "".join(
                f'<li class="dz-chart-legend-item">'
                f'<span class="dz-chart-legend-swatch" '
                f'style="background:{_series_color(i)}"></span>'
                f'<span class="dz-chart-legend-name">{ctx.escape(s.name)}</span></li>'
                for i, s in enumerate(t.series)
            )
            return render_time_series(
                TimeSeriesSeam(
                    label=t.label,
                    view=view,
                    series=[
                        TimeSeriesLayerSeam(
                            name=s.name,
                            points=[
                                TimeSeriesPointSeam(label=lbl, value=val) for lbl, val in s.points
                            ],
                        )
                        for s in t.series
                    ],
                    svg_html=svg,
                    legend_html=f'<ul class="dz-chart-legend">{legend_items}</ul>',
                    peak_display=max_val_str,
                )
            )

        if not t.points:
            return render_time_series(TimeSeriesSeam(label=t.label, view=view))

        max_val = max((v for _, v in t.points), default=1) or 1
        max_val_str = str(int(max_val)) if max_val == int(max_val) else str(max_val)
        svg = time_series_svg(
            t.label,
            t.points,
            view=view,
            reference_lines=t.reference_lines,
            reference_bands=t.reference_bands,
        )
        return render_time_series(
            TimeSeriesSeam(
                label=t.label,
                view=view,
                points=[TimeSeriesPointSeam(label=lbl, value=val) for lbl, val in t.points],
                svg_html=svg,
                peak_display=max_val_str,
            )
        )

    def _emit_radar(self, r: Radar, ctx: RenderContext) -> str:
        """Render a Radar via HM dual-lock Radar seam.

        SVG geometry stays in ``dazzle.render.svg.radar_svg``.
        """
        from dazzle.render.filters import _metric_number_filter
        from dazzle.render.svg import radar_svg

        if not r.axes:
            return render_radar(RadarSeam(label=r.label, axes=[]))

        svg = radar_svg(r.label, r.axes)
        max_val = max((v for _, v in r.axes), default=1) or 1
        max_for_filter = int(max_val) if max_val == int(max_val) else max_val
        max_val_str = _metric_number_filter(max_for_filter)
        return render_radar(
            RadarSeam(
                label=r.label,
                axes=[RadarAxisSeam(label=lbl, value=val) for lbl, val in r.axes],
                svg_html=svg,
                peak_display=max_val_str,
            )
        )

    def _emit_box_plot(self, b: BoxPlot, ctx: RenderContext) -> str:
        """Render a BoxPlot via HM dual-lock BoxPlot seam.

        SVG geometry stays in ``dazzle.render.svg.box_plot_svg``; the seam
        carries the trusted SVG plus group stats for the summary line.
        """
        from dazzle.render.svg import box_plot_svg

        if not b.groups:
            return render_box_plot(BoxPlotSeam(label=b.label, groups=[]))

        svg = box_plot_svg(
            b.label,
            b.groups,
            reference_lines=b.reference_lines,
            samples=b.samples,
        )
        samples = b.samples if b.samples else (0,) * len(b.groups)
        return render_box_plot(
            BoxPlotSeam(
                label=b.label,
                groups=[
                    BoxPlotGroupSeam(
                        label=label,
                        min=mn,
                        q1=q1,
                        median=med,
                        q3=q3,
                        max=mx,
                        samples=samples[i] if i < len(samples) else 0,
                    )
                    for i, (label, mn, q1, med, q3, mx) in enumerate(b.groups)
                ],
                svg_html=svg,
            )
        )

    def _emit_bullet(self, b: Bullet, ctx: RenderContext) -> str:
        """Render a Bullet via HM dual-lock Bullet seam."""
        return render_bullet(
            BulletSeam(
                rows=[
                    BulletRowSeam(label=r.label, actual=r.actual, target=r.target) for r in b.rows
                ],
                max_value=b.max_value,
                bands=[
                    BulletBandSeam(
                        from_value=band.from_value,
                        to_value=band.to_value,
                        label=band.label,
                        color=band.color,
                    )
                    for band in b.reference_bands
                ],
                empty_message=b.empty_message,
            )
        )

    def _emit_sparkline(self, s: Sparkline, ctx: RenderContext) -> str:
        """Render a Sparkline via HM dual-lock Sparkline seam."""
        return render_sparkline(SparklineSeam(points=list(s.points), empty_message=s.empty_message))

    def _emit_tree(self, t: Tree, ctx: RenderContext) -> str:
        """Render a Tree matching legacy `workspace/regions/tree.html`
        byte-for-byte: recursive `<details class="dz-tree-node">` with
        chevron SVG + label + optional child count, top-level depth-0
        nodes open by default.
        """
        if not t.nodes:
            return ""
        return "".join(self._emit_tree_node(n, depth=0, ctx=ctx) for n in t.nodes)

    def _emit_tree_node(self, node: TreeNode, *, depth: int, ctx: RenderContext) -> str:
        open_attr = " open" if depth == 0 else ""
        chevron = (
            '<svg class="dz-tree-chevron" fill="none" viewBox="0 0 24 24" '
            'stroke="currentColor" stroke-width="2" aria-hidden="true">'
            '<path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"/>'
            "</svg>"
        )
        count_html = (
            f'<span class="dz-tree-count">{len(node.children)}</span>' if node.children else ""
        )
        summary = (
            f'<summary class="dz-tree-summary">'
            f"{chevron}"
            f'<span class="dz-tree-label">{ctx.escape(node.label)}</span>'
            f"{count_html}"
            f"</summary>"
        )
        if node.children:
            children_html = "".join(
                self._emit_tree_node(c, depth=depth + 1, ctx=ctx) for c in node.children
            )
            return (
                f'<details class="dz-tree-node"{open_attr}>'
                f"{summary}"
                f'<div class="dz-tree-children">{children_html}</div>'
                f"</details>"
            )
        return f'<details class="dz-tree-node"{open_attr}>{summary}</details>'

    def _emit_pipeline_steps(self, p: PipelineSteps, ctx: RenderContext) -> str:
        """Render a PipelineSteps row matching legacy
        `workspace/regions/pipeline_steps.html` byte-for-byte:
        outer `dz-pipeline-steps-region`, `<ol class="dz-pipeline-stages">`
        of `<li class="dz-pipeline-stage">` rows with kicker label,
        headline value (or "—"), optional caption, optional progress
        block, and per-non-last-stage connector SVGs (desktop arrow
        + mobile chevron).
        """
        if not p.stages:
            return (
                f'<div class="dz-pipeline-steps-region">'
                f'<p class="dz-empty-dense" role="status">'
                f"{ctx.escape(p.empty_message)}</p>"
                f"</div>"
            )

        last_idx = len(p.stages) - 1
        items: list[str] = []
        for i, stage in enumerate(p.stages):
            value_str = str(stage.value) if stage.value is not None else "—"
            caption_html = (
                f'<span class="dz-pipeline-stage-caption">{ctx.escape(stage.caption)}</span>'
                if stage.caption
                else ""
            )

            progress_html = ""
            if stage.progress is not None:
                overshoot_attr = (
                    ' data-dz-progress-overshoot="true"' if stage.progress_overshoot else ""
                )
                progress_html = (
                    f'<div class="dz-pipeline-stage-progress" '
                    f'data-dz-progress="{stage.progress}"{overshoot_attr} '
                    f'role="progressbar" '
                    f'aria-valuemin="0" aria-valuemax="100" '
                    f'aria-valuenow="{stage.progress}" '
                    f'aria-label="{ctx.escape_attr(stage.label)} progress">'
                    f'<div class="dz-pipeline-stage-progress-track">'
                    f'<div class="dz-pipeline-stage-progress-fill" '
                    f'style="width: {stage.progress}%;"></div>'
                    f"</div>"
                    f'<span class="dz-pipeline-stage-progress-label">'
                    f"{stage.progress}%</span>"
                    f"</div>"
                )

            connector_html = ""
            if i < last_idx:
                connector_html = (
                    '<span class="dz-pipeline-connector" aria-hidden="true">'
                    '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" '
                    'xmlns="http://www.w3.org/2000/svg">'
                    '<path d="M3 1.5L9 7l-6 5.5" stroke="currentColor" '
                    'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
                    "</svg>"
                    "</span>"
                    '<span class="dz-pipeline-connector-mobile" aria-hidden="true">'
                    '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" '
                    'xmlns="http://www.w3.org/2000/svg">'
                    '<path d="M1.5 3L7 9l5.5-6" stroke="currentColor" '
                    'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
                    "</svg>"
                    "</span>"
                )

            items.append(
                f'<li class="dz-pipeline-stage">'
                f'<span class="dz-pipeline-stage-label">{ctx.escape(stage.label)}</span>'
                f'<span class="dz-pipeline-stage-value">{value_str}</span>'
                f"{caption_html}"
                f"{progress_html}"
                f"{connector_html}"
                f"</li>"
            )

        return (
            f'<div class="dz-pipeline-steps-region">'
            f'<ol class="dz-pipeline-stages">{"".join(items)}</ol>'
            f"</div>"
        )

    def _emit_kanban_region(self, k: KanbanRegion, ctx: RenderContext) -> str:
        """Render a KanbanRegion matching legacy
        `workspace/regions/kanban.html` byte-for-byte: outer
        `dz-kanban-board`, per-column head with badge + count, stack
        of cards with title + secondary fields + optional attention
        tag, optional overflow row with Load all button.

        Empty path renders the legacy `fragments/empty_state.html` shape.
        """
        from dazzle.render.fragment.region import (
            _render_status_badge_html,
        )

        if not k.columns:
            label = k.empty_message or "No items found."
            return (
                f'<div class="dz-empty-state" data-dz-empty-kind="read-only" role="status">'
                f"{lucide_svg_html('kanban', cls='dz-empty-state__icon')}"
                f'<p class="dz-empty-state__description">{ctx.escape(label)}</p>'
                f"</div>"
            )

        column_html: list[str] = []
        total_cards = 0
        for col in k.columns:
            cards_html: list[str] = []
            for card in col.cards:
                fields_html = ""
                for label, value in card.fields:
                    if isinstance(value, str):
                        value_html = ctx.escape(value)
                    else:
                        value_html = self._emit(value, ctx)  # type: ignore[arg-type]
                    fields_html += (
                        f'<p class="dz-kanban-card-field">'
                        f"<span>{ctx.escape(label)}:</span> "
                        f"{value_html}"
                        f"</p>"
                    )
                cards_html.append(
                    render_kanban_card(
                        KanbanCardSeam(
                            title=card.title,
                            fields_html=fields_html,
                            attention_level=card.attention_level,
                            attention_message=card.attention_message,
                        )
                    )
                )
            stack_inner = "".join(cards_html)
            if not col.cards:
                stack_inner = '<p class="dz-kanban-empty">No items</p>'
            badge_html = _render_status_badge_html(col.label)
            column_html.append(
                f'<div class="dz-kanban-column">'
                f'<div class="dz-kanban-column-head">'
                f"{badge_html}"
                f'<span class="dz-kanban-column-count">{len(col.cards)}</span>'
                f"</div>"
                f'<div class="dz-kanban-stack">{stack_inner}</div>'
                f"</div>"
            )
            total_cards += len(col.cards)

        overflow_html = ""
        if k.total > total_cards:
            overflow_html = (
                f'<div class="dz-kanban-overflow">'
                f'<p class="dz-kanban-overflow-text">'
                f"Showing {total_cards} of {k.total}"
                f"</p>"
                f'<button type="button" class="dz-kanban-load-all" '
                f'hx-get="{ctx.escape_attr(k.endpoint)}?page_size={k.total}" '
                f'hx-target="closest [data-dz-region]" '
                f'hx-swap="outerHTML">Load all</button>'
                f"</div>"
            )

        # role=region + tabindex=0: overflow-x:auto is intentional; axe
        # scrollable-region-focusable requires keyboard access when the board
        # actually scrolls (common once the container is width-constrained).
        return (
            f'<div class="dz-kanban-board" role="region" '
            f'aria-label="Kanban board" tabindex="0">'
            f"{''.join(column_html)}</div>{overflow_html}"
        )

    def _emit_funnel(self, f: Funnel, ctx: RenderContext) -> str:
        """Render a Funnel via HM dual-lock Funnel seam."""
        return render_funnel(
            FunnelSeam(
                stages=[
                    FunnelStageSeam(label=stage.label, count=stage.count) for stage in f.stages
                ],
                total=f.total,
                empty_message=f.empty_message,
            )
        )

    def _emit_heatmap(self, h: Heatmap, ctx: RenderContext) -> str:
        """Render a Heatmap via HM dual-lock Heatmap seam."""
        return render_heatmap(
            HeatmapSeam(
                columns=list(h.columns),
                rows=[HeatmapRowSeam(label=r.label, cells=list(r.cells)) for r in h.rows],
                thresholds=list(h.thresholds),
                total=h.total,
                empty_message=h.empty_message,
            )
        )

    def _emit_histogram(self, h: Histogram, ctx: RenderContext) -> str:
        """Render a Histogram via HM dual-lock Histogram seam.

        SVG geometry stays in ``dazzle.render.svg.histogram_svg``; the seam
        carries the trusted SVG plus bin stats for the summary line.
        """
        from dazzle.render.svg import histogram_svg

        if not h.bins:
            return render_histogram(
                HistogramSeam(label=h.label, bins=[], empty_message=h.empty_message)
            )

        svg_bins = tuple((b.label, b.count, b.low, b.high) for b in h.bins)
        svg = histogram_svg(h.label, svg_bins, reference_lines=h.reference_lines)
        return render_histogram(
            HistogramSeam(
                label=h.label,
                bins=[
                    HistogramBinSeam(label=b.label, count=b.count, low=b.low, high=b.high)
                    for b in h.bins
                ],
                svg_html=svg,
                empty_message=h.empty_message,
            )
        )
