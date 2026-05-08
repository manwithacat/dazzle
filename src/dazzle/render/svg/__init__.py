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


__all__ = ["time_series_svg"]
