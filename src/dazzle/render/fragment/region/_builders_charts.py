"""Chart-family region builders.

Houses the 10 chart builders that share the `_parse_reference_lines` /
`_parse_reference_bands` helpers and the same Surface-wrapping pattern:

  - _build_radar        radar polar profile (≥3 axes)
  - _build_box_plot     quartile boxplot
  - _build_time_series  line / area / sparkline
  - _build_diagram      Mermaid ER diagram (with structural fallback)
  - _build_bar_track    labelled ARIA progressbars
  - _build_bullet       Stephen Few bullet rows
  - _build_funnel_chart funnel stages
  - _build_histogram    continuous-axis bars
  - _build_heatmap      threshold-tinted matrix
  - _build_bar_chart    classic categorical bars

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

from dazzle.render.fragment import (
    BarChart,
    BarTrack,
    BoxPlot,
    Bullet,
    BulletRow,
    Diagram,
    EmptyState,
    Fragment,
    Funnel,
    FunnelStage,
    Heatmap,
    HeatmapRow,
    Histogram,
    HistogramBin,
    Radar,
    RawHTML,
    ReferenceBand,
    ReferenceLine,
    Sparkline,
    Stack,
    Surface,
    Text,
    TimeSeries,
)
from dazzle.render.fragment.format_cell import format_cell
from dazzle.render.fragment.region._context import RegionContext
from dazzle.render.fragment.region._shared import (
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
        formatted = format_cell(raw_value, "text") if raw_value is not None else "—"
        outlier = entry.get("outlier")
        if outlier in ("low", "high"):
            formatted = f"{formatted} ⚠ {outlier}"
        fill_pct = max(0.0, min(100.0, fraction * 100.0))
        rows.append((label, value, formatted, fill_pct))
    return rows


class _BuildersChartsMixin:
    """Mixin adding the 10 chart-family `_build_*` methods to
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
                    axes.append((str(entry[0]), float(entry[1])))
                except (TypeError, ValueError):
                    continue
            elif isinstance(entry, dict):
                label = str(entry.get("axis") or entry.get("label") or "")
                try:
                    val = float(entry.get("value") or 0)
                except (TypeError, ValueError):
                    val = 0.0
                if label:
                    axes.append((label, val))

        body: Fragment
        # Radar primitive requires ≥3 axes; fewer collapses to a line.
        # Adapter degrades to EmptyState rather than crashing.
        if len(axes) < 3:
            body = EmptyState(
                title="No data",
                description=getattr(region, "empty_message", None)
                or "Radar requires at least 3 axes.",
            )
        else:
            body = Radar(label=chart_label, axes=tuple(axes))

        return _wrap_surface(title, "report", body)

    def _build_box_plot(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: box_plot` regions render as a BoxPlot quartile table.

        ctx shape:
            groups: list of dicts {"label": str, "min": float, "q1": float,
                                   "median": float, "q3": float, "max": float}
                or 6-tuples (label, min, q1, median, q3, max)
            chart_label: optional override
        """
        title = _region_title(region)
        chart_label = str(ctx.get("chart_label") or title or "Distribution")
        raw_groups = ctx.get("groups") or []
        groups: list[tuple[str, float, float, float, float, float]] = []
        # Phase 4B.4 wave 2: thread per-group sample counts through to
        # the primitive when supplied (legacy `box_plot_stats[i].n`),
        # so the renderer can match the legacy `n=N` tooltip suffix.
        samples: list[int] = []
        any_sample = False
        for entry in raw_groups:
            label = ""
            mn = q1 = med = q3 = mx = 0.0
            n_value = 0
            n_present = False
            if isinstance(entry, (list, tuple)) and len(entry) == 6:
                try:
                    label = str(entry[0])
                    mn, q1, med, q3, mx = (float(v) for v in entry[1:6])
                except (TypeError, ValueError):
                    continue
            elif isinstance(entry, dict):
                label = str(entry.get("label") or "")
                try:
                    mn = float(entry.get("min") or 0)
                    q1 = float(entry.get("q1") or 0)
                    med = float(entry.get("median") or 0)
                    q3 = float(entry.get("q3") or 0)
                    mx = float(entry.get("max") or 0)
                except (TypeError, ValueError):
                    continue
                if "n" in entry:
                    try:
                        n_value = int(entry.get("n") or 0)
                        n_present = True
                    except (TypeError, ValueError):
                        n_present = False
            else:
                continue
            # Drop groups with non-monotonic quartiles — BoxPlot's
            # __post_init__ would raise; the adapter is permissive.
            if label and mn <= q1 <= med <= q3 <= mx:
                groups.append((label, mn, q1, med, q3, mx))
                samples.append(n_value if n_present else 0)
                if n_present:
                    any_sample = True

        body: Fragment
        if not groups:
            body = EmptyState(
                title="No data",
                description=getattr(region, "empty_message", None)
                or "No box-plot groups to render.",
            )
        else:
            body = BoxPlot(
                label=chart_label,
                groups=tuple(groups),
                samples=tuple(samples) if any_sample else (),
                reference_lines=_parse_reference_lines(ctx.get("reference_lines")),
                reference_bands=_parse_reference_bands(ctx.get("reference_bands")),
            )

        return _wrap_surface(title, "report", body)

    def _build_time_series(
        self,
        region: Any,
        ctx: RegionContext,
        view: Literal["line", "area", "sparkline"],
    ) -> Surface:
        """Render a TimeSeries primitive (line / area / sparkline).

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
        chart_label = str(ctx.get("chart_label") or title or view.title())
        raw_points = ctx.get("points") or []
        points: list[tuple[str, float]] = []
        for entry in raw_points:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                try:
                    points.append((str(entry[0]), float(entry[1])))
                except (TypeError, ValueError):
                    continue
            elif isinstance(entry, dict):
                label = str(entry.get("label") or entry.get("x") or "")
                try:
                    val = float(entry.get("value") or entry.get("y") or 0)
                except (TypeError, ValueError):
                    val = 0.0
                if label:
                    points.append((label, val))

        body: Fragment

        # Sparkline is a structurally distinct shape (180×32 viewBox,
        # headline + tiny SVG, no axis labels, no reference overlays);
        # Phase 4B.4 wave 2 routes it to a dedicated `Sparkline`
        # primitive rather than overloading TimeSeries' SVG output.
        if view == "sparkline":
            empty_msg = ctx.get("empty_message") or getattr(region, "empty_message", None) or "—"
            body = Sparkline(points=tuple(points), empty_message=str(empty_msg))
            return _wrap_surface(title, "report", body)

        if not points:
            body = EmptyState(
                title="No data",
                description=getattr(region, "empty_message", None) or "No points to plot.",
            )
            return _wrap_surface(title, "report", body)

        ref_lines = _parse_reference_lines(ctx.get("reference_lines"))
        ref_bands = _parse_reference_bands(ctx.get("reference_bands"))

        body = TimeSeries(
            label=chart_label,
            points=tuple(points),
            view=view,
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

    def _build_bar_track(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: bar_track` renders one labelled, filled track per
        row with ARIA progressbar semantics + a summary line. Phase
        4B.1.b — uses the typed `BarTrack` primitive (replaced the
        prior alias to `_build_progress` which produced the simpler
        Stack-of-Row(Text, Badge) shape).

        ctx shape:
            bar_track_rows: list of dicts {"label": str, "value": float,
                "formatted_value": str, "fill_pct": float (0..100)}
                — pre-computed by the runtime per `track_format` Python
                format spec
            bar_track_max: float — scale endpoint for aria-valuemax
                + summary line
            (legacy fallback) `items` with `{label, percent}` shape from
                Phase 4A is still accepted; `formatted_value` is filled
                in as `"<percent>%"`, `value` mirrors `percent`,
                `bar_track_max` defaults to 100.

        Empty rows degrade to EmptyState; rows with malformed shapes or
        out-of-range fill_pct silently drop rather than tripping the
        BarTrack primitive's invariants.
        """
        title = _region_title(region)
        raw_rows = ctx.get("bar_track_rows") or []
        max_value: float
        try:
            max_value = float(ctx.get("bar_track_max") or 100.0)
        except (TypeError, ValueError):
            max_value = 100.0
        if max_value <= 0:
            max_value = 100.0

        rows: list[tuple[str, float, str, float]] = []
        # Primary path — pre-computed bar_track_rows from the runtime
        for entry in raw_rows:
            if not isinstance(entry, dict):
                continue
            label = str(entry.get("label") or "")
            if not label:
                continue
            try:
                value = float(entry.get("value") or 0)
                fill_pct = float(entry.get("fill_pct") or 0)
            except (TypeError, ValueError):
                continue
            fill_pct = max(0.0, min(100.0, fill_pct))
            formatted = str(entry.get("formatted_value") or value)
            rows.append((label, value, formatted, fill_pct))

        # Legacy fallback — Phase 4A `items` with `{label, percent}` shape
        if not rows:
            for entry in ctx.get("items") or []:
                if not isinstance(entry, dict):
                    continue
                label = str(entry.get("label") or entry.get("name") or "")
                if not label:
                    continue
                try:
                    percent = float(entry.get("percent") or entry.get("value") or 0)
                except (TypeError, ValueError):
                    percent = 0.0
                percent = max(0.0, min(100.0, percent))
                rows.append((label, percent, f"{percent:g}%", percent))

        body: Fragment
        if not rows:
            body = EmptyState(
                title="No data",
                description=getattr(region, "empty_message", None) or "No data available.",
            )
        else:
            body = BarTrack(
                rows=tuple(rows),
                max_value=max_value,
                reference_lines=_parse_reference_lines(ctx.get("reference_lines")),
                reference_bands=_parse_reference_bands(ctx.get("reference_bands")),
            )

        return _wrap_surface(title, "report", body)

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
                title="No data",
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

    def _build_bullet(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: bullet` renders Stephen Few bullet rows — label +
        track (bands behind, actual bar, optional target tick) +
        formatted value. Phase 4B.4 wave 2: dedicated `Bullet` primitive
        replaces prior Stack+Row+Badge composition for byte-equivalence
        with `workspace/regions/bullet.html`.

        ctx shape (primary):
            bullet_rows: list of dicts {label, actual, target}
            bullet_max_value: float — denominator for percentage scale
            reference_bands: optional list[dict] for comparative zones
            empty_message: optional empty-state fallback
        """
        title = _region_title(region)
        raw_rows = ctx.get("bullet_rows") or []
        try:
            max_value = float(ctx.get("bullet_max_value") or 0)
        except (TypeError, ValueError):
            max_value = 0.0

        rows: list[BulletRow] = []
        if isinstance(raw_rows, list):
            for entry in raw_rows:
                if not isinstance(entry, dict):
                    continue
                label = str(entry.get("label") or entry.get("name") or "")
                if not label:
                    continue
                try:
                    actual = float(entry.get("actual", 0))
                except (TypeError, ValueError):
                    continue
                target_raw = entry.get("target")
                target: float | None = None
                if target_raw is not None:
                    try:
                        target = float(target_raw)
                    except (TypeError, ValueError):
                        target = None
                rows.append(BulletRow(label=label, actual=actual, target=target))

        empty_msg = (
            ctx.get("empty_message")
            or getattr(region, "empty_message", None)
            or "No data available."
        )
        body: Fragment = Bullet(
            rows=tuple(rows),
            max_value=max_value if rows else 1.0,  # invariant guard for empty
            reference_bands=_parse_reference_bands(ctx.get("reference_bands")),
            empty_message=str(empty_msg),
        )
        return _wrap_surface(title, "report", body)

    def _build_funnel_chart(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: funnel_chart` regions render as a `Funnel` primitive.

        Phase 4B.4 wave 3: dedicated builder (replaces prior bar_chart
        routing) for byte-equivalence with `workspace/regions/funnel_chart.html`.
        Width is calculated relative to the FIRST stage's count (not max),
        and clamped to a 20% minimum. Stages are ordered as supplied —
        funnel rendering preserves the declared kanban_columns order.

        ctx shape (production runtime):
            kanban_columns: ordered list of stage keys
            items: source rows (counted per stage via group_by)
            group_by: field name on each item carrying the stage value
            total: pre-computed total item count
            (legacy alt) buckets: pre-sorted [(label, count)] tuples
            (legacy alt) metrics: list[{label, value}] fallback
            empty_message: optional empty-state fallback
        """
        title = _region_title(region)
        items = ctx.get("items") or []
        kanban_columns = ctx.get("kanban_columns") or []
        group_by = ctx.get("group_by")
        try:
            total = int(ctx.get("total") or 0)
        except (TypeError, ValueError):
            total = 0

        stages: list[FunnelStage] = []
        if kanban_columns and items and group_by:
            counts: dict[str, int] = {str(s): 0 for s in kanban_columns}
            for item in items:
                if isinstance(item, dict):
                    key = str(item.get(group_by) or "Unknown")
                    if key in counts:
                        counts[key] += 1
            for stage in kanban_columns:
                key = str(stage)
                stages.append(FunnelStage(label=key, count=counts.get(key, 0)))
        else:
            # Legacy fallbacks: pre-sorted buckets, or metrics list.
            for entry in ctx.get("buckets") or []:
                if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                    try:
                        stages.append(FunnelStage(label=str(entry[0]), count=int(entry[1])))
                    except (TypeError, ValueError):
                        continue
            if not stages:
                for m in ctx.get("metrics") or []:
                    if isinstance(m, dict):
                        try:
                            stages.append(
                                FunnelStage(
                                    label=str(m.get("label") or ""),
                                    count=int(m.get("value") or 0),
                                )
                            )
                        except (TypeError, ValueError):
                            continue

        empty_msg = (
            ctx.get("empty_message")
            or getattr(region, "empty_message", None)
            or "No data available."
        )
        body: Fragment = Funnel(
            stages=tuple(stages),
            total=total,
            empty_message=str(empty_msg),
        )
        return _wrap_surface(title, "report", body)

    def _build_histogram(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: histogram` regions render as a `Histogram` primitive
        — continuous-axis SVG bar chart with optional vertical reference
        lines. Phase 4B.4 wave 3: dedicated builder (replaces prior alias
        to `_build_bar_chart`) for byte-equivalence with
        `workspace/regions/histogram.html`.

        ctx shape:
            histogram_bins: list of `{label, count, low, high}` dicts —
                pre-computed by the runtime's `_compute_histogram_bins`
                from the already-fetched items
            reference_lines: optional list of `{value, label, style}`
                dicts (vertical overlays at x-position)
            empty_message: optional empty-state fallback
        """
        title = _region_title(region)
        chart_label = str(ctx.get("chart_label") or title or "Histogram")
        raw_bins = ctx.get("histogram_bins") or []

        bins: list[HistogramBin] = []
        for entry in raw_bins:
            if not isinstance(entry, dict):
                continue
            label = str(entry.get("label") or "")
            if not label:
                continue
            try:
                count = int(entry.get("count") or 0)
                low = float(entry.get("low", 0))
                high = float(entry.get("high", 0))
            except (TypeError, ValueError):
                continue
            bins.append(HistogramBin(label=label, count=count, low=low, high=high))

        empty_msg = (
            ctx.get("empty_message")
            or getattr(region, "empty_message", None)
            or "No data available."
        )
        body: Fragment = Histogram(
            label=chart_label,
            bins=tuple(bins),
            reference_lines=_parse_reference_lines(ctx.get("reference_lines")),
            empty_message=str(empty_msg),
        )
        return _wrap_surface(title, "report", body)

    def _build_heatmap(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: heatmap` regions render as a `Heatmap` primitive
        — threshold-tinted matrix matching `workspace/regions/heatmap.html`
        byte-for-byte. Phase 4B.4 wave 4: dedicated builder (replaces
        alias to pivot_table).

        ctx shape (production runtime):
            heatmap_matrix: list of dicts {row, row_id, cells:[{col, value}]}
            heatmap_col_values: ordered list of column labels
            heatmap_thresholds: 0/1/2 ascending floats for tone bands
            total: int — overflow indicator denominator
            items: list — for total > items.length overflow check
            empty_message: optional empty-state fallback
        """
        title = _region_title(region)
        matrix = ctx.get("heatmap_matrix") or []
        col_values = ctx.get("heatmap_col_values") or []
        thresholds_raw = ctx.get("heatmap_thresholds") or []
        try:
            total = int(ctx.get("total") or 0)
        except (TypeError, ValueError):
            total = 0
        # Legacy template's overflow check is `total > items|length`,
        # not `total > rows|length` — but typically items==rows count.
        items = ctx.get("items") or []
        if total < len(items):
            total = len(items)

        thresholds: list[float] = []
        for t in thresholds_raw:
            try:
                thresholds.append(float(t))
            except (TypeError, ValueError):
                continue

        rows: list[HeatmapRow] = []
        for row_dict in matrix:
            if not isinstance(row_dict, dict):
                continue
            row_label = str(row_dict.get("row") or "")
            cells_raw = row_dict.get("cells") or []
            cell_values: list[float] = []
            for cell in cells_raw:
                if isinstance(cell, dict):
                    try:
                        cell_values.append(float(cell.get("value") or 0))
                    except (TypeError, ValueError):
                        cell_values.append(0.0)
            rows.append(
                HeatmapRow(
                    label=row_label,
                    cells=tuple(cell_values),
                    row_id=str(row_dict.get("row_id") or ""),
                )
            )

        empty_msg = (
            ctx.get("empty_message")
            or getattr(region, "empty_message", None)
            or "No data available."
        )
        body: Fragment = Heatmap(
            columns=tuple(str(c) for c in col_values),
            rows=tuple(rows),
            thresholds=tuple(thresholds),
            total=total,
            empty_message=str(empty_msg),
        )
        return _wrap_surface(title, "report", body)

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
                    buckets.append((str(entry[0]), int(entry[1])))
                except (TypeError, ValueError):
                    continue
            elif isinstance(entry, dict):
                key = str(entry.get("label") or entry.get("key") or "")
                try:
                    val = int(entry.get("value") or entry.get("count") or 0)
                except (TypeError, ValueError):
                    val = 0
                if key:
                    buckets.append((key, val))

        body: Fragment
        if not buckets:
            body = EmptyState(
                title="No data",
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
