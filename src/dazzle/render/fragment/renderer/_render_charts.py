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
from dazzle.render.fragment.ingest import KanbanCard as KanbanCardSeam
from dazzle.render.fragment.ingest import render_kanban_card
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
        """Render a bar chart as label/track/fill/value rows — byte-equivalent
        to the legacy `workspace/regions/bar_chart.html` template's
        `bucketed_metrics` primary branch.

        Phase 4B.4 wave 3: aligned with legacy template:
          - Outer `dz-bar-chart-region` carries no aria-label (label is
            owned by the surrounding region_card chrome)
          - Bucket label wrapped in `render_status_badge(value, size='sm')`
            via `_render_status_badge_html`
          - No summary line (legacy summary appears in the items+group_by
            branch, not the bucketed_metrics branch)
          - No `<dl>` references block (Phase 4B-only addition with no
            legacy equivalent in this branch)
        """
        if not b.buckets:
            return '<div class="dz-bar-chart-region"></div>'

        # Late import to avoid circular dependency between renderer and
        # workspace adapter (the helper lives in adapter for now; could
        # be promoted to a shared module if more renderers need it).
        from dazzle.render.fragment.region import (
            _render_status_badge_html,
        )

        max_val = max((c for _, c in b.buckets), default=1) or 1
        rows = "".join(
            f'<div class="dz-bar-chart-row">'
            f'<span class="dz-bar-chart-label">'
            f"{_render_status_badge_html(label, size='sm')}"
            f"</span>"
            f'<div class="dz-bar-chart-track">'
            f'<div class="dz-bar-chart-fill" '
            f'style="width: {int(count / max_val * 100)}%"></div>'
            f"</div>"
            f'<span class="dz-bar-chart-value">{count}</span>'
            f"</div>"
            for label, count in b.buckets
        )
        return f'<div class="dz-bar-chart-region"><div class="dz-bar-chart-bars">{rows}</div></div>'

    def _emit_timeline(self, t: Timeline, ctx: RenderContext) -> str:
        """Render a Timeline matching legacy
        `workspace/regions/timeline.html` byte-for-byte: outer
        `dz-timeline-region`, `<ul class="dz-timeline-list">` of
        `<li class="dz-timeline-item">` rows. Each row carries a bullet
        SVG, formatted date, primary title, and optional secondary
        fields rendered as `<p class="dz-timeline-field">` lines.
        Optional overflow line "Showing N of M" when total exceeds
        the events count. Empty path renders the `dz-empty-dense`
        fallback inside the region wrapper.
        """
        # Coerce Phase 4A `(label, iso-date)` tuples to TimelineEvent
        # for rendering uniformity. New callers construct TimelineEvent
        # instances directly.
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

        # Legacy bullet always picks up `attention_classes(attn, 'bullet')`
        # which defaults to `dz-attn-bullet dz-attn-tone-default` when
        # the item has no `_attention` entry. The typed primitive
        # doesn't track per-row attention yet (Phase 4B follow-up); for
        # now, emit the default attention class so the no-attention
        # case is byte-equivalent to legacy.
        bullet_svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" '
            'fill="currentColor" '
            'class="dz-timeline-bullet dz-attn-bullet dz-attn-tone-default" '
            'aria-hidden="true">'
            '<circle cx="10" cy="10" r="6"/>'
            "</svg>"
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
                f'<li class="dz-timeline-item">'
                f'<span class="dz-timeline-bullet-wrap">{bullet_svg}</span>'
                f'<div class="dz-timeline-row">'
                f'<div class="dz-timeline-date">{ctx.escape(evt.date_label)}</div>'
                f'<div class="dz-timeline-content">'
                f'<p class="dz-timeline-title">{ctx.escape(evt.title)}</p>'
                f"{fields_html}"
                f"</div>"
                f"</div>"
                f"</li>"
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
                f'<div class="dz-diagram-scroll">'
                f'<pre class="mermaid dz-diagram-source">'
                f"{ctx.escape(d.mermaid_source)}"
                f"</pre>"
                f"</div>"
                f"{_DIAGRAM_MERMAID_SCRIPT}"
            )
        nodes_html = "".join(
            f'<li class="dz-diagram__node" data-dz-key="{ctx.escape_attr(name)}">'
            f"{ctx.escape(name)}</li>"
            for name in d.nodes
        )
        edges_html = "".join(
            f'<li class="dz-diagram__edge">'
            f'<span class="dz-diagram__edge-from">{ctx.escape(src)}</span>'
            f'<span class="dz-diagram__edge-arrow">→</span>'
            f'<span class="dz-diagram__edge-to">{ctx.escape(dst)}</span>'
            f"</li>"
            for src, dst in d.edges
        )
        return (
            f'<section class="dz-diagram">'
            f'<ul class="dz-diagram__nodes">{nodes_html}</ul>'
            f'<ul class="dz-diagram__edges">{edges_html}</ul>'
            f"</section>"
        )

    def _emit_time_series(self, t: TimeSeries, ctx: RenderContext) -> str:
        """Render line/area/sparkline as inline SVG plus optional `<dl>`
        annotation lists for reference lines and reference bands.

        Phase 4B.1.c replaced the semantic `<ol>` of points with an
        inline SVG produced by `dazzle.render.svg.time_series_svg` —
        byte-equivalent to the legacy `line_chart.html` template. The
        `<dl class="dz-timeseries__references">` block remains as the
        programmatic-data layer for screen-readers and tests; the SVG
        already carries the same data via `<title>` tooltips and is
        the visual layer.
        """
        from dazzle.render.svg import _series_color, time_series_svg

        # Phase 4B.4 wave 3: aligned with legacy template — strip the
        # `<section class="dz-timeseries">` chrome + `<h4>` + Phase 4B-
        # only `<dl>` references block. Wrapper class is per-view
        # (`dz-line-chart-region` for line, `dz-area-chart-region` for
        # area). Summary line emits `{count} buckets · peak {max_val}`.
        wrapper_class = "dz-area-chart-region" if t.view == "area" else "dz-line-chart-region"

        # Multi-series path (#1473): overlaid layers + a colour-keyed legend.
        if t.series:
            series_pairs = tuple((s.name, s.points) for s in t.series)
            axis_labels = {lbl for _n, pts in series_pairs for lbl, _v in pts}
            all_vals = [v for _n, pts in series_pairs for _l, v in pts]
            max_val = max(all_vals, default=1) or 1
            max_val_str = str(int(max_val)) if max_val == int(max_val) else str(max_val)
            svg = time_series_svg(
                t.label,
                (),
                view=t.view,
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
            legend = f'<ul class="dz-chart-legend">{legend_items}</ul>'
            summary = (
                f'<p class="dz-chart-summary">{len(axis_labels)} buckets · '
                f"{len(t.series)} series · peak {max_val_str}</p>"
            )
            return f'<div class="{wrapper_class}">{svg}{legend}{summary}</div>'

        if not t.points:
            return f'<div class="{wrapper_class}"></div>'

        max_val = max((v for _, v in t.points), default=1) or 1
        max_val_str = str(int(max_val)) if max_val == int(max_val) else str(max_val)

        svg = time_series_svg(
            t.label,
            t.points,
            view=t.view,
            reference_lines=t.reference_lines,
            reference_bands=t.reference_bands,
        )
        summary = f'<p class="dz-chart-summary">{len(t.points)} buckets · peak {max_val_str}</p>'
        return f'<div class="{wrapper_class}">{svg}{summary}</div>'

    def _emit_radar(self, r: Radar, ctx: RenderContext) -> str:
        """Render a polar/radar profile as inline SVG with concentric
        grid rings, spoke axis lines, data polygon, and spoke labels —
        byte-equivalent to `workspace/regions/radar.html` for the
        single-series case.

        Phase 4B.1.c (SVG arc, radar variant): replaces the prior
        `<ul>` of axes with the SVG produced by
        `dazzle.render.svg.radar_svg`. Outer `<section class="dz-radar">`
        + `<h4 class="dz-radar__label">` wrapper survives so existing
        CSS hooks keep working; the SVG sits in a new
        `<div class="dz-radar-region">` (the legacy class).
        """
        from dazzle.render.filters import _metric_number_filter
        from dazzle.render.svg import radar_svg

        # Phase 4B.4 wave 3: aligned with legacy template — strip the
        # `<section class="dz-radar">` + `<h4>` chrome. Summary uses
        # the legacy "N spokes · 1 series · peak {metric_number}" format
        # (single-series — multi-series Radar is a deferred primitive).
        svg = radar_svg(r.label, r.axes)
        max_val = max((v for _, v in r.axes), default=1) or 1
        max_for_filter = int(max_val) if max_val == int(max_val) else max_val
        max_val_str = _metric_number_filter(max_for_filter)
        summary = (
            f'<p class="dz-chart-summary">{len(r.axes)} spokes · 1 series · peak {max_val_str}</p>'
        )
        return f'<div class="dz-radar-region">{svg}{summary}</div>'

    def _emit_box_plot(self, b: BoxPlot, ctx: RenderContext) -> str:
        """Render a box-plot as inline SVG box+whisker glyphs — byte-
        equivalent to `workspace/regions/box_plot.html` for the common
        case (modulo the documented divergence in `box_plot_svg`).

        Phase 4B.4 wave 2: stripped the prior Phase 4B.1.c chrome
        (`<section class="dz-box-plot">` + `<h4>` + summary line +
        `<dl>` references block) for byte-equivalence with the legacy
        template, which emits only `<div class="dz-box-plot-region">`
        wrapping the SVG. The summary referenced legacy's `n` field
        (sum of samples across groups); the typed primitive doesn't
        carry `n`, so the summary can't be reproduced — dropped. The
        `<dl>` references block was a Phase 4B-only addition with no
        legacy counterpart; also dropped to match.

        Empty case renders `<p class="dz-empty-dense">…</p>` inside
        the region wrapper, matching the legacy `{% else %}` branch.
        """
        from dazzle.render.svg import box_plot_svg

        if not b.groups:
            empty_msg = "No data available."
            return (
                f'<div class="dz-box-plot-region">'
                f'<p class="dz-empty-dense" role="status">{empty_msg}</p>'
                f"</div>"
            )

        svg = box_plot_svg(
            b.label,
            b.groups,
            reference_lines=b.reference_lines,
            samples=b.samples,
        )
        # Summary line — matches legacy `{{ count }} groups · {{ sum(n) }} samples`.
        # When samples is empty, sum is 0 (legacy Jinja sum on missing
        # attribute returns 0 too).
        n_total = sum(b.samples) if b.samples else 0
        summary = f'<p class="dz-box-plot-summary">{len(b.groups)} groups · {n_total} samples</p>'
        return f'<div class="dz-box-plot-region">{svg}{summary}</div>'

    def _emit_bullet(self, b: Bullet, ctx: RenderContext) -> str:
        """Render a Bullet matching legacy
        `workspace/regions/bullet.html` byte-for-byte: outer
        `dz-bullet-region` wrapper, per-row label + track (bands behind,
        actual bar, optional target tick) + formatted value, summary
        line "N rows · scale 0–MAX".

        Empty path renders the `dz-empty-dense` fallback inside the
        region wrapper. Reference bands use the same colour map as the
        chart-family SVG helpers (`var(--colour-brand)` for `target`
        etc.); `from`/`to` positions are rendered as percentage of
        max_value.

        Numeric formatting matches the legacy Jinja `{{ value }}`
        rendering — whole-valued floats narrow to int repr (so 75.0
        renders as "75"), fractional values keep the trailing decimal.
        """
        from dazzle.render.svg import _BAND_COLORS

        if not b.rows or b.max_value <= 0:
            return (
                f'<div class="dz-bullet-region">'
                f'<p class="dz-empty-dense" role="status">'
                f"{ctx.escape(b.empty_message)}</p>"
                f"</div>"
            )

        # Match Jinja's `{{ value }}` rendering: whole floats render
        # without trailing `.0`. Used for tooltip numerics where the
        # legacy template did not apply `round()`.
        def _jinja_num(value: float) -> str:
            return str(int(value)) if value == int(value) else str(value)

        rows_html: list[str] = []
        for row in b.rows:
            actual_pct = round(row.actual / b.max_value * 100, 2)
            bands_html = ""
            for band in b.reference_bands:
                band_left = round(band.from_value / b.max_value * 100, 2)
                band_width = round((band.to_value - band.from_value) / b.max_value * 100, 2)
                colour = _BAND_COLORS.get(band.color, _BAND_COLORS["target"])
                bands_html += (
                    f'<span class="dz-bullet-band" '
                    f'style="left: {band_left}%; width: {band_width}%; '
                    f'background: {colour};" '
                    f'title="{ctx.escape_attr(band.label)}: '
                    f'{_jinja_num(band.from_value)}–{_jinja_num(band.to_value)}"></span>'
                )

            target_html = ""
            # `round(1)` for value display matches `{{ value | round(1) }}`;
            # but Jinja's round renders 75.0 as "75.0" only if the value
            # was already non-int. For ints, round(1) gives an int so
            # "75". Mirror that with _jinja_num after round.
            actual_rounded = round(row.actual, 1)
            value_html = _jinja_num(actual_rounded)
            if row.target is not None:
                target_pct = round(row.target / b.max_value * 100, 2)
                target_html = (
                    f'<span class="dz-bullet-target" '
                    f'style="left: {target_pct}%;" '
                    f'title="{ctx.escape_attr(row.label)} target: '
                    f'{_jinja_num(row.target)}"></span>'
                )
                target_rounded = round(row.target, 1)
                value_html += f" / {_jinja_num(target_rounded)}"

            rows_html.append(
                f'<div class="dz-bullet-row">'
                f'<span class="dz-bullet-label">{ctx.escape(row.label)}</span>'
                f'<div class="dz-bullet-track">'
                f"{bands_html}"
                f'<span class="dz-bullet-actual" '
                f'style="width: {actual_pct}%;" '
                f'title="{ctx.escape_attr(row.label)} actual: '
                f'{_jinja_num(row.actual)}"></span>'
                f"{target_html}"
                f"</div>"
                f'<span class="dz-bullet-value">{value_html}</span>'
                f"</div>"
            )

        return (
            f'<div class="dz-bullet-region">'
            f'<div class="dz-bullet-rows">{"".join(rows_html)}</div>'
            f'<p class="dz-bullet-summary">'
            f"{len(b.rows)} rows · scale 0–{_jinja_num(round(b.max_value, 1))}"
            f"</p>"
            f"</div>"
        )

    def _emit_sparkline(self, s: Sparkline, ctx: RenderContext) -> str:
        """Render a Sparkline matching legacy
        `workspace/regions/sparkline.html` byte-for-byte: outer
        `dz-sparkline-region`, headline showing the latest bucket
        (value + label), and a tiny 180×32 SVG with area fill +
        polyline. Single-point series omit the SVG entirely (matches
        legacy `{% if count > 1 %}` guard). Empty series renders the
        `dz-sparkline-empty` div with the empty message.
        """
        if not s.points:
            return (
                f'<div class="dz-sparkline-region">'
                f'<div class="dz-sparkline-empty">{ctx.escape(s.empty_message)}</div>'
                f"</div>"
            )

        last_label, last_value = s.points[-1]
        # Match Jinja's `{{ value }}` rendering — int repr for whole values.
        last_value_str = str(int(last_value)) if last_value == int(last_value) else str(last_value)
        max_val = max(v for _, v in s.points)
        if max_val <= 0:
            max_val = 1
        max_val_str = str(int(max_val)) if max_val == int(max_val) else str(max_val)
        count = len(s.points)

        headline = (
            f'<div class="dz-sparkline-headline">'
            f'<span class="dz-sparkline-value">{ctx.escape(last_value_str)}</span>'
            f'<span class="dz-sparkline-bucket-label">{ctx.escape(last_label)}</span>'
            f"</div>"
        )

        if count <= 1:
            return f'<div class="dz-sparkline-region">{headline}</div>'

        # 180×32 viewBox with 2px top/bottom padding (no left/right padding).
        w = 180
        h = 32
        pt = 2
        pb = 2
        plot_h = h - pt - pb
        step = w / (count - 1)
        pts = []
        for i, (_, v) in enumerate(s.points):
            x = round(i * step, 2)
            y = round(pt + plot_h - (v / max_val * plot_h), 2)
            pts.append(f"{x},{y}")
        pts_str = " ".join(pts)

        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {w} {h}" '
            f'class="dz-sparkline-svg" role="img" '
            f'aria-label="Sparkline — {count} points, latest '
            f'{last_value_str}, peak {max_val_str}">'
            f'<polygon points="0,{h} {pts_str} {w},{h}" '
            f'fill="var(--colour-brand)" fill-opacity="0.15" stroke="none" />'
            f'<polyline points="{pts_str}" fill="none" '
            f'stroke="var(--colour-brand)" stroke-width="1.25" '
            f'stroke-linejoin="round" stroke-linecap="round" />'
            f"</svg>"
        )
        return f'<div class="dz-sparkline-region">{headline}{svg}</div>'

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
        """Render a Funnel matching legacy
        `workspace/regions/funnel_chart.html` byte-for-byte: outer
        `dz-funnel-chart-region`, `dz-funnel-stages` of `dz-funnel-stage-row`
        items. Width is calculated from the first stage's count and
        clamped to a 20% minimum. `data-dz-funnel-step` is the stage
        index capped at 7.
        """
        if not f.stages:
            return (
                f'<div class="dz-funnel-chart-region">'
                f'<p class="dz-empty-dense" role="status">'
                f"{ctx.escape(f.empty_message)}</p>"
                f"</div>"
            )

        base = f.stages[0].count if f.stages[0].count > 0 else 1
        items: list[str] = []
        for i, stage in enumerate(f.stages):
            pct = int(stage.count / base * 100)
            width = pct if pct >= 20 else 20
            step = i if i < 8 else 7
            items.append(
                f'<div class="dz-funnel-stage-row">'
                f'<div class="dz-funnel-stage" '
                f'data-dz-funnel-step="{step}" '
                f'style="width: {width}%;">'
                f'<span class="dz-funnel-stage-label">{ctx.escape(stage.label)}</span> '
                f'<span class="dz-funnel-stage-count">({stage.count})</span>'
                f"</div>"
                f"</div>"
            )

        return (
            f'<div class="dz-funnel-chart-region">'
            f'<div class="dz-funnel-stages">{"".join(items)}</div>'
            f'<p class="dz-funnel-summary">{f.total} total</p>'
            f"</div>"
        )

    def _emit_heatmap(self, h: Heatmap, ctx: RenderContext) -> str:
        """Render a Heatmap matching legacy
        `workspace/regions/heatmap.html` byte-for-byte: outer
        `dz-heatmap-region` wrapping a `dz-heatmap-scroll` with a
        `<table class="dz-heatmap-grid">`. Headers row has an empty
        leading `<th></th>` followed by column labels. Each row carries
        a label `<td class="dz-heatmap-row-label">` then per-cell
        `<td class="dz-heatmap-cell">` with `data-dz-heatmap-tone`
        threshold-banded tone (bad / warn / good). Values formatted
        as `%.1f`. Optional overflow line.
        """
        if not h.rows:
            return (
                f'<div class="dz-heatmap-region">'
                f'<p class="dz-empty-dense" role="status">'
                f"{ctx.escape(h.empty_message)}</p>"
                f"</div>"
            )

        head_cols = "".join(f"<th>{ctx.escape(c)}</th>" for c in h.columns)
        thead = f"<thead><tr><th></th>{head_cols}</tr></thead>"

        def _tone_attr(value: float) -> str:
            n = len(h.thresholds)
            if n >= 2:
                if value < h.thresholds[0]:
                    return ' data-dz-heatmap-tone="bad"'
                if value < h.thresholds[1]:
                    return ' data-dz-heatmap-tone="warn"'
                return ' data-dz-heatmap-tone="good"'
            if n == 1:
                if value < h.thresholds[0]:
                    return ' data-dz-heatmap-tone="bad"'
                return ' data-dz-heatmap-tone="good"'
            return ""

        body_rows: list[str] = []
        for row in h.rows:
            cells_html = ""
            for cell in row.cells:
                cells_html += f'<td class="dz-heatmap-cell"{_tone_attr(cell)}> {cell:.1f} </td>'
            body_rows.append(
                f"<tr>"
                f'<td class="dz-heatmap-row-label">{ctx.escape(row.label)}</td>'
                f"{cells_html}"
                f"</tr>"
            )
        tbody = f"<tbody>{''.join(body_rows)}</tbody>"

        overflow_html = ""
        if h.total > len(h.rows):
            overflow_html = f'<p class="dz-heatmap-overflow">Showing {len(h.rows)} of {h.total}</p>'

        return (
            f'<div class="dz-heatmap-region">'
            f'<div class="dz-heatmap-scroll">'
            f'<table class="dz-heatmap-grid">{thead}{tbody}</table>'
            f"</div>"
            f"{overflow_html}"
            f"</div>"
        )

    def _emit_histogram(self, h: Histogram, ctx: RenderContext) -> str:
        """Render a Histogram matching legacy
        `workspace/regions/histogram.html` byte-for-byte: outer
        `dz-histogram-region` wrapping the SVG (via `histogram_svg`)
        and a `dz-histogram-summary` line "{count} bins · {total}
        samples · peak {max_count}". Empty path renders the
        `dz-empty-dense` fallback inside the region wrapper.
        """
        from dazzle.render.svg import histogram_svg

        if not h.bins:
            return (
                f'<div class="dz-histogram-region">'
                f'<p class="dz-empty-dense" role="status">'
                f"{ctx.escape(h.empty_message)}</p>"
                f"</div>"
            )

        svg_bins = tuple((b.label, b.count, b.low, b.high) for b in h.bins)
        svg = histogram_svg(h.label, svg_bins, reference_lines=h.reference_lines)
        total = sum(b.count for b in h.bins)
        max_count = max(b.count for b in h.bins) or 1
        summary = (
            f'<p class="dz-histogram-summary">'
            f"{len(h.bins)} bins · {total} samples · peak {max_count}"
            f"</p>"
        )
        return f'<div class="dz-histogram-region">{svg}{summary}</div>'
