"""Lightweight SVG rendering helpers for chart primitives — Phase 4B.1.c.

Pure-Python helpers that produce inline SVG matching the legacy Jinja
chart templates byte-for-byte. No vendored library; no JS runtime;
deterministic output (the same primitive renders the same SVG every
time, regardless of platform).

Each helper takes already-validated chart data (typically passed by
the renderer's `_emit_*` method from a Fragment primitive) and returns
a string of inline SVG markup. The geometry constants match the legacy
templates' viewBox dimensions, padding, and colour tokens.
"""

from html import escape as _escape

# Geometry — matches legacy `line_chart.html` exactly so dual-path
# validation (Phase 4B.3) produces byte-equivalent output.
DEFAULT_WIDTH = 400
DEFAULT_HEIGHT = 120
DEFAULT_PADDING_TOP = 8
DEFAULT_PADDING_RIGHT = 8
DEFAULT_PADDING_BOTTOM = 28  # bottom band reserved for x-axis tick labels
DEFAULT_PADDING_LEFT = 8


# Reference-line stroke styles — keys match `ReferenceLine.style`.
_LINE_DASHARRAY: dict[str, str] = {
    "solid": "",
    "dashed": "4,3",
    "dotted": "1,3",
}

# Reference-band fills — keys match `ReferenceBand.color`. Token-driven
# so the rendered SVG inherits the design palette.
_BAND_COLORS: dict[str, str] = {
    "target": "hsl(var(--primary))",
    "positive": "hsl(145, 55%, 45%)",
    "warning": "hsl(40, 90%, 55%)",
    "destructive": "hsl(var(--destructive))",
    "muted": "hsl(var(--muted-foreground))",
}


def time_series_svg(
    label: str,
    points: tuple[tuple[str, float], ...],
    *,
    view: str = "line",
    reference_lines: tuple = (),
    reference_bands: tuple = (),
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> str:
    """Produce inline SVG for a TimeSeries primitive.

    Single-series time series rendered as polyline + area fill + data
    points + reference overlays. Output matches the legacy
    `workspace/regions/line_chart.html` byte-for-byte for the basic
    case (no overlay_series_data — that remains a future extension
    once the runtime threads multi-series data through ctx).

    `view` is currently informational; the same geometry covers line,
    area, and sparkline. A future ship can specialise sparkline to a
    smaller viewBox without axis labels.
    """
    if not points:
        return ""

    pt = DEFAULT_PADDING_TOP
    pr = DEFAULT_PADDING_RIGHT
    pb = DEFAULT_PADDING_BOTTOM
    pl = DEFAULT_PADDING_LEFT
    plot_w = width - pl - pr
    plot_h = height - pt - pb
    count = len(points)

    # Y-axis range includes reference lines/bands so all visual elements
    # stay inside the plot area (#883). Bands also widen the floor below 0.
    point_values = [v for _, v in points]
    line_values = [r.value for r in reference_lines]
    band_tops = [b.to_value for b in reference_bands]
    band_bottoms = [b.from_value for b in reference_bands]
    candidates = point_values + line_values + band_tops
    max_val = max(candidates) if candidates else 1
    if max_val <= 0:
        max_val = 1
    min_val = min([0, *band_bottoms])
    if min_val >= 0:
        min_val = 0
    value_range = max_val - min_val
    if value_range <= 0:
        value_range = 1

    def _y(val: float) -> float:
        return round(pt + plot_h - ((val - min_val) / value_range * plot_h), 2)

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" '
        f'class="dz-line-chart-svg dz-chart-svg" role="img" '
        f'aria-label="{_escape(label, quote=True)} time series — '
        f'{count} buckets, peak {max_val}">',
        # Baseline grid — single line at the bottom of the plot area.
        f'<line x1="{pl}" y1="{pt + plot_h}" '
        f'x2="{pl + plot_w}" y2="{pt + plot_h}" '
        f'stroke="hsl(var(--border))" stroke-width="1" />',
    ]

    # Reference bands — render before data so the line/area sit on top.
    for band in reference_bands:
        band_top_y = _y(band.to_value)
        band_bot_y = _y(band.from_value)
        band_h = round(band_bot_y - band_top_y, 2)
        if band_h > 0:
            color = _BAND_COLORS.get(band.color, _BAND_COLORS["target"])
            parts.append(
                f'<rect x="{pl}" y="{band_top_y}" '
                f'width="{plot_w}" height="{band_h}" '
                f'fill="{color}" fill-opacity="0.12" stroke="none">'
                f"<title>{_escape(band.label)}: "
                f"{band.from_value}–{band.to_value}</title>"
                f"</rect>"
            )

    # Reference lines — render before data so circles + line sit above.
    for ref in reference_lines:
        ref_y = _y(ref.value)
        dasharray = _LINE_DASHARRAY.get(ref.style, "")
        parts.append(
            f'<line x1="{pl}" y1="{ref_y}" '
            f'x2="{pl + plot_w}" y2="{ref_y}" '
            f'stroke="hsl(var(--muted-foreground))" '
            f'stroke-width="1" stroke-dasharray="{dasharray}">'
            f"<title>{_escape(ref.label)}: {ref.value}</title>"
            f"</line>"
        )

    # Polyline geometry
    step = plot_w / (count - 1) if count > 1 else 0
    line_points = []
    for i, (_, val) in enumerate(points):
        px = round(pl + i * step, 2)
        py = _y(val)
        line_points.append(f"{px},{py}")
    line_points_str = " ".join(line_points)

    # Area polygon (closes back to baseline)
    base_y = pt + plot_h
    parts.append(
        f'<polygon points="{pl},{base_y} {line_points_str} '
        f'{pl + plot_w},{base_y}" '
        f'fill="hsl(var(--primary))" fill-opacity="0.12" stroke="none" />'
    )

    # The line itself
    parts.append(
        f'<polyline points="{line_points_str}" '
        f'fill="none" stroke="hsl(var(--primary))" stroke-width="1.5" '
        f'stroke-linejoin="round" stroke-linecap="round" />'
    )

    # Data points + accessible <title> tooltips
    for i, (lbl, val) in enumerate(points):
        px = round(pl + i * step, 2)
        py = _y(val)
        parts.append(
            f'<circle cx="{px}" cy="{py}" r="2.5" '
            f'fill="hsl(var(--primary))" stroke="hsl(var(--card))" '
            f'stroke-width="1">'
            f"<title>{_escape(lbl)}: {val}</title>"
            f"</circle>"
        )

    # X-axis labels — show every Nth bucket to avoid collisions on wide series.
    show_every = 1 if count <= 5 else max(1, (count + 4) // 5)
    for i, (lbl, _) in enumerate(points):
        if i == 0 or i == count - 1 or i % show_every == 0:
            px = round(pl + i * step, 2)
            parts.append(
                f'<text x="{px}" y="{height - 8}" '
                f'text-anchor="middle" font-size="9" '
                f'fill="hsl(var(--muted-foreground))" '
                f"font-family=\"ui-monospace, 'SF Mono', Menlo, monospace\">"
                f"{_escape(lbl)}</text>"
            )

    parts.append("</svg>")
    return "".join(parts)


def box_plot_svg(
    label: str,
    groups: tuple[tuple[str, float, float, float, float, float], ...],
    *,
    reference_lines: tuple = (),
) -> str:
    """Produce inline SVG for a BoxPlot primitive.

    One column per group (label, min, q1, median, q3, max). Renders
    whisker stem + caps, Q1–Q3 box body, median line. Width scales
    with group count (56px per box, capped at 460px). Y-axis spans
    the global min/max of all whiskers so boxes are directly
    comparable.

    Output matches legacy `workspace/regions/box_plot.html` for the
    common case. Known divergence: the primitive carries 6 stats per
    group (label, min, q1, median, q3, max) — no separate Tukey
    whisker fences (whisker_low/high), no outlier list, no sample
    count `n`. So the SVG renders min/max as the whisker fences (no
    1.5×IQR clipping), no outlier dots, and tooltips drop the n=N
    suffix. The runtime's `_compute_box_plot_stats` continues to
    compute the full set; routing those into the typed primitive is
    a future ship if/when needed.
    """
    if not groups:
        return ""

    count = len(groups)
    h = 200
    pt = 8
    pr = 8
    pb = 32
    pl = 32
    natural_w = count * 56 + 64
    w = natural_w if natural_w < 460 else 460
    plot_w = w - pl - pr
    plot_h = h - pt - pb
    col_w = plot_w / count
    box_w = (col_w * 0.6) if (col_w * 0.6) < 36 else 36

    # Y-range = global whisker span.
    lows = [mn for _, mn, _, _, _, _ in groups]
    highs = [mx for _, _, _, _, _, mx in groups]
    y_min = min(lows)
    y_max = max(highs)
    y_range = y_max - y_min
    if y_range <= 0:
        y_range = 1

    def _y(val: float) -> float:
        return round(pt + plot_h - ((val - y_min) / y_range * plot_h), 2)

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {w} {h}" '
        f'class="dz-box-plot-svg" role="img" '
        f'aria-label="{_escape(label, quote=True)} box plot — '
        f'{count} groups, range {round(y_min, 1)}–{round(y_max, 1)}">',
        # Baseline + Y-axis lines.
        f'<line x1="{pl}" y1="{pt + plot_h}" '
        f'x2="{pl + plot_w}" y2="{pt + plot_h}" '
        f'stroke="hsl(var(--border))" stroke-width="1" />',
        f'<line x1="{pl}" y1="{pt}" '
        f'x2="{pl}" y2="{pt + plot_h}" '
        f'stroke="hsl(var(--border))" stroke-width="1" />',
        # Y-axis tick labels: min (bottom), max (top).
        f'<text x="{pl - 4}" y="{pt + plot_h + 4}" '
        f'text-anchor="end" font-size="9" '
        f'fill="hsl(var(--muted-foreground))" '
        f"font-family=\"ui-monospace, 'SF Mono', Menlo, monospace\">"
        f"{round(y_min, 1)}</text>",
        f'<text x="{pl - 4}" y="{pt + 4}" '
        f'text-anchor="end" font-size="9" '
        f'fill="hsl(var(--muted-foreground))" '
        f"font-family=\"ui-monospace, 'SF Mono', Menlo, monospace\">"
        f"{round(y_max, 1)}</text>",
    ]

    # Per-group box.
    for i, (group_label, mn, q1, median, q3, mx) in enumerate(groups):
        col_x = round(pl + (i + 0.5) * col_w, 2)
        q1_y = _y(q1)
        q3_y = _y(q3)
        median_y = _y(median)
        whisker_low_y = _y(mn)
        whisker_high_y = _y(mx)
        cap_half = round(box_w / 4, 2)
        box_half = round(box_w / 2, 2)

        # Whisker stem.
        parts.append(
            f'<line x1="{col_x}" y1="{whisker_low_y}" '
            f'x2="{col_x}" y2="{whisker_high_y}" '
            f'stroke="hsl(var(--muted-foreground))" stroke-width="1" />'
        )
        # Whisker caps.
        parts.append(
            f'<line x1="{col_x - cap_half}" y1="{whisker_low_y}" '
            f'x2="{col_x + cap_half}" y2="{whisker_low_y}" '
            f'stroke="hsl(var(--muted-foreground))" stroke-width="1" />'
        )
        parts.append(
            f'<line x1="{col_x - cap_half}" y1="{whisker_high_y}" '
            f'x2="{col_x + cap_half}" y2="{whisker_high_y}" '
            f'stroke="hsl(var(--muted-foreground))" stroke-width="1" />'
        )
        # Box body.
        box_h = round(q1_y - q3_y, 2)
        parts.append(
            f'<rect x="{col_x - box_half}" y="{q3_y}" '
            f'width="{round(box_w, 2)}" height="{box_h}" '
            f'fill="hsl(var(--primary))" fill-opacity="0.18" '
            f'stroke="hsl(var(--primary))" stroke-width="1">'
            f"<title>{_escape(group_label)}: Q1 {round(q1, 1)}, "
            f"median {round(median, 1)}, Q3 {round(q3, 1)}</title>"
            f"</rect>"
        )
        # Median line.
        parts.append(
            f'<line x1="{col_x - box_half}" y1="{median_y}" '
            f'x2="{col_x + box_half}" y2="{median_y}" '
            f'stroke="hsl(var(--primary))" stroke-width="1.5" />'
        )
        # Group label below the axis.
        parts.append(
            f'<text x="{col_x}" y="{h - 8}" '
            f'text-anchor="middle" font-size="10" '
            f'fill="hsl(var(--foreground))" '
            f"font-family=\"ui-monospace, 'SF Mono', Menlo, monospace\">"
            f"{_escape(group_label)}</text>"
        )

    # Reference lines (clipped to plot range — out-of-range lines drop).
    for ref in reference_lines:
        if ref.value < y_min or ref.value > y_max:
            continue
        ref_y = _y(ref.value)
        dasharray = _LINE_DASHARRAY.get(ref.style, "")
        parts.append(
            f'<line x1="{pl}" y1="{ref_y}" '
            f'x2="{pl + plot_w}" y2="{ref_y}" '
            f'stroke="hsl(var(--muted-foreground))" '
            f'stroke-width="1" stroke-dasharray="{dasharray}">'
            f"<title>{_escape(ref.label)}: {ref.value}</title>"
            f"</line>"
        )

    parts.append("</svg>")
    return "".join(parts)


__all__ = ["box_plot_svg", "time_series_svg"]
