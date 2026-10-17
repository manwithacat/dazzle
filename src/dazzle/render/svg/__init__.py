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

import math
from html import escape as _escape
from typing import Any

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
    "target": "var(--colour-brand)",
    "positive": "hsl(145, 55%, 45%)",
    "warning": "hsl(40, 90%, 55%)",
    "destructive": "var(--colour-danger)",
    "muted": "var(--colour-text-muted)",
}

# Multi-series palette (#1473) — overlaid series cycle through these
# design tokens so each series inherits a theme-aware colour. Five
# distinct tokens; series beyond the fifth wrap (modulo).
_SERIES_COLORS: tuple[str, ...] = (
    "var(--colour-brand)",
    "var(--colour-info)",
    "var(--colour-success)",
    "var(--colour-warning)",
    "var(--colour-danger)",
)


def _series_color(index: int) -> str:
    return _SERIES_COLORS[index % len(_SERIES_COLORS)]


def _fmt_value(val: float) -> str:
    """Int-narrow whole-valued floats — matches the single-series path."""
    return str(int(val)) if val == int(val) else str(val)


def time_series_svg(
    label: str,
    points: tuple[tuple[str, float], ...],
    *,
    view: str = "line",
    reference_lines: tuple[Any, ...] = (),
    reference_bands: tuple[Any, ...] = (),
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    series: tuple[tuple[str, tuple[tuple[str, float], ...]], ...] = (),
) -> str:
    """Produce inline SVG for a TimeSeries primitive.

    Single-series time series rendered as polyline + area fill + data
    points + reference overlays. Output matches the legacy
    `workspace/regions/line_chart.html` byte-for-byte for the basic
    case.

    `series` (#1473) carries the multi-series case: a tuple of
    `(name, points)` pairs. When non-empty it takes precedence over
    `points` and every series is drawn as an overlaid transparent layer
    on a shared label axis (the ordered union of all series' labels),
    each in its own palette colour. This is the rendering substrate for
    stacked `area_chart` and line-chart `overlay_series` (#883).

    `view` is currently informational; the same geometry covers line,
    area, and sparkline. A future ship can specialise sparkline to a
    smaller viewBox without axis labels.
    """
    if series:
        return _multi_series_svg(
            label,
            series,
            reference_lines=reference_lines,
            reference_bands=reference_bands,
            width=width,
            height=height,
        )
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
        return float(round(pt + plot_h - ((val - min_val) / value_range * plot_h), 2))

    # Int-narrowing for aria-label so whole-valued floats render without
    # the trailing `.0` (matches Jinja's `{{ max_val }}` behaviour).
    max_val_label = str(int(max_val)) if max_val == int(max_val) else str(max_val)
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" '
        f'class="dz-line-chart-svg dz-chart-svg" role="img" '
        f'aria-label="{_escape(label, quote=True)} time series — '
        f'{count} buckets, peak {max_val_label}">',
        # Baseline grid — single line at the bottom of the plot area.
        f'<line x1="{pl}" y1="{pt + plot_h}" '
        f'x2="{pl + plot_w}" y2="{pt + plot_h}" '
        f'stroke="var(--colour-border)" stroke-width="1"/>',
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
            f'stroke="var(--colour-text-muted)" '
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
        f'fill="var(--colour-brand)" fill-opacity="0.12" stroke="none"/>'
    )

    # The line itself
    parts.append(
        f'<polyline points="{line_points_str}" '
        f'fill="none" stroke="var(--colour-brand)" stroke-width="1.5" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
    )

    # Data points + accessible <title> tooltips
    for i, (lbl, val) in enumerate(points):
        px = round(pl + i * step, 2)
        py = _y(val)
        # Match Jinja `{{ b.value }}` — int repr for whole values.
        val_label = str(int(val)) if val == int(val) else str(val)
        parts.append(
            f'<circle cx="{px}" cy="{py}" r="2.5" '
            f'fill="var(--colour-brand)" stroke="var(--colour-surface)" '
            f'stroke-width="1">'
            f"<title>{_escape(lbl)}: {val_label}</title>"
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
                f'fill="var(--colour-text-muted)" '
                f"font-family=\"ui-monospace, 'SF Mono', Menlo, monospace\">"
                f"{_escape(lbl)}</text>"
            )

    parts.append("</svg>")
    return "".join(parts)


def _shared_axis(
    series: tuple[tuple[str, tuple[tuple[str, float], ...]], ...],
) -> tuple[list[str], list[dict[str, float]]]:
    """Ordered union of every series' labels + a label→value map per series."""
    axis_labels: list[str] = []
    seen: set[str] = set()
    series_maps: list[dict[str, float]] = []
    for _name, pts in series:
        smap: dict[str, float] = {}
        for lbl, val in pts:
            key = str(lbl)
            smap[key] = float(val)
            if key not in seen:
                seen.add(key)
                axis_labels.append(key)
        series_maps.append(smap)
    return axis_labels, series_maps


def _reference_overlay_parts(
    reference_bands: tuple[Any, ...],
    reference_lines: tuple[Any, ...],
    y_of: Any,
    pl: int,
    plot_w: int,
) -> list[str]:
    """Shaded bands + annotation lines, drawn under the data layers."""
    parts: list[str] = []
    for band in reference_bands:
        band_top_y = y_of(band.to_value)
        band_h = round(y_of(band.from_value) - band_top_y, 2)
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
    for ref in reference_lines:
        ref_y = y_of(ref.value)
        dasharray = _LINE_DASHARRAY.get(ref.style, "")
        parts.append(
            f'<line x1="{pl}" y1="{ref_y}" '
            f'x2="{pl + plot_w}" y2="{ref_y}" '
            f'stroke="var(--colour-text-muted)" '
            f'stroke-width="1" stroke-dasharray="{dasharray}">'
            f"<title>{_escape(ref.label)}: {ref.value}</title>"
            f"</line>"
        )
    return parts


def _series_layer_parts(
    s_idx: int,
    s_name: str,
    smap: dict[str, float],
    axis_labels: list[str],
    xs: list[float],
    base_y: float,
    y_of: Any,
    pl: int,
    plot_w: int,
) -> list[str]:
    """One series' translucent area + line + titled data points."""
    color = _series_color(s_idx)
    coords = [(xs[i], y_of(smap.get(lbl, 0.0))) for i, lbl in enumerate(axis_labels)]
    line_points_str = " ".join(f"{px},{py}" for px, py in coords)
    parts = [
        f'<polygon points="{pl},{base_y} {line_points_str} '
        f'{pl + plot_w},{base_y}" '
        f'fill="{color}" fill-opacity="0.12" stroke="none"/>',
        f'<polyline points="{line_points_str}" '
        f'fill="none" stroke="{color}" stroke-width="1.5" '
        f'stroke-linejoin="round" stroke-linecap="round"/>',
    ]
    for i, lbl in enumerate(axis_labels):
        px, py = coords[i]
        val_label = _fmt_value(smap.get(lbl, 0.0))
        parts.append(
            f'<circle cx="{px}" cy="{py}" r="2.5" '
            f'fill="{color}" stroke="var(--colour-surface)" '
            f'stroke-width="1">'
            f"<title>{_escape(s_name)} · {_escape(lbl)}: {val_label}</title>"
            f"</circle>"
        )
    return parts


def _axis_label_parts(axis_labels: list[str], xs: list[float], height: int) -> list[str]:
    """X-axis tick labels — every Nth bucket to avoid collisions."""
    count = len(axis_labels)
    show_every = 1 if count <= 5 else max(1, (count + 4) // 5)
    parts: list[str] = []
    for i, lbl in enumerate(axis_labels):
        if i == 0 or i == count - 1 or i % show_every == 0:
            parts.append(
                f'<text x="{xs[i]}" y="{height - 8}" '
                f'text-anchor="middle" font-size="9" '
                f'fill="var(--colour-text-muted)" '
                f"font-family=\"ui-monospace, 'SF Mono', Menlo, monospace\">"
                f"{_escape(lbl)}</text>"
            )
    return parts


def _multi_series_svg(
    label: str,
    series: tuple[tuple[str, tuple[tuple[str, float], ...]], ...],
    *,
    reference_lines: tuple[Any, ...] = (),
    reference_bands: tuple[Any, ...] = (),
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> str:
    """Render N overlaid series sharing one label axis (#1473).

    Each series is drawn from the baseline as a translucent area + line
    + data points, one design-palette colour per series. Missing
    (series, label) cells read as 0 — for time-bucket stacked areas an
    absent bucket genuinely means a zero count.
    """
    axis_labels, series_maps = _shared_axis(series)
    if not axis_labels:
        return ""

    pt, pl = DEFAULT_PADDING_TOP, DEFAULT_PADDING_LEFT
    plot_w = width - pl - DEFAULT_PADDING_RIGHT
    plot_h = height - pt - DEFAULT_PADDING_BOTTOM
    count = len(axis_labels)

    # Y-range spans every series value (0-filled) plus reference overlays.
    all_values = [m.get(lbl, 0.0) for m in series_maps for lbl in axis_labels]
    candidates = (
        all_values + [r.value for r in reference_lines] + [b.to_value for b in reference_bands]
    )
    max_val = max(candidates) if candidates else 1
    if max_val <= 0:
        max_val = 1
    min_val = min([0, *(b.from_value for b in reference_bands)])
    value_range = (max_val - min_val) or 1

    def _y(val: float) -> float:
        return float(round(pt + plot_h - ((val - min_val) / value_range * plot_h), 2))

    step = plot_w / (count - 1) if count > 1 else 0
    xs = [round(pl + i * step, 2) for i in range(count)]
    base_y = pt + plot_h

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" '
        f'class="dz-line-chart-svg dz-chart-svg" role="img" '
        f'aria-label="{_escape(label, quote=True)} time series — '
        f'{len(series)} series, {count} buckets, peak {_fmt_value(max_val)}">',
        f'<line x1="{pl}" y1="{base_y}" x2="{pl + plot_w}" y2="{base_y}" '
        f'stroke="var(--colour-border)" stroke-width="1"/>',
    ]
    parts += _reference_overlay_parts(reference_bands, reference_lines, _y, pl, plot_w)
    for s_idx, (s_name, _pts) in enumerate(series):
        parts += _series_layer_parts(
            s_idx, s_name, series_maps[s_idx], axis_labels, xs, base_y, _y, pl, plot_w
        )
    parts += _axis_label_parts(axis_labels, xs, height)
    parts.append("</svg>")
    return "".join(parts)


__all__ = ["box_plot_svg", "histogram_svg", "time_series_svg"]
