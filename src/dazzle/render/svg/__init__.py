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


def _with_unit(shown: str, unit_suffix: str = "") -> str:
    """Append a measure unit when the host named a ``*_ms`` (etc.) field."""
    return f"{shown}{unit_suffix}" if unit_suffix else shown


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


def box_plot_svg(
    label: str,
    groups: tuple[tuple[str, float, float, float, float, float], ...],
    *,
    reference_lines: tuple[Any, ...] = (),
    samples: tuple[int, ...] = (),
    unit_suffix: str = "",
) -> str:
    """Produce inline SVG for a BoxPlot primitive.

    One column per group (label, min, q1, median, q3, max). Renders:

    - **Whiskers** outside the IQR only (min→Q1 and Q3→max) with end caps
    - **Box** body for Q1–Q3
    - **Hairline median** (stroke-width 1)
    - **Hover marks** at the five-number points (``.dz-box-plot-mark``) —
      CSS reveals the numeric figure on hover; ``<title>`` for SR/native
      tooltips

    Width scales with group count (56px per box, capped at 460px). Y-axis
    spans the global min/max of all whiskers so boxes are comparable.

    Known limits vs full Tukey diagrams: min/max are the whisker fences
    (no separate 1.5×IQR fences / outlier list on the primitive). Pass
    ``samples`` for ``n=N`` on the box overview tooltip. Outliers remain
    a future ship when the typed primitive carries them.
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

    def _y_raw(val: float) -> float:
        """Cartesian y for a value, NOT rounded — for derived calcs."""
        return pt + plot_h - ((val - y_min) / y_range * plot_h)

    def _y(val: float) -> float:
        """Rounded cartesian y for direct emission as an SVG coord."""
        return round(_y_raw(val), 2)

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {w} {h}" '
        f'class="dz-box-plot-svg" role="img" '
        f'aria-label="{_escape(label, quote=True)} box plot — '
        f"{count} groups, range {_with_unit(str(round(y_min, 1)), unit_suffix)}"
        f'–{_with_unit(str(round(y_max, 1)), unit_suffix)}">',
        # Baseline + Y-axis lines.
        f'<line x1="{pl}" y1="{pt + plot_h}" '
        f'x2="{pl + plot_w}" y2="{pt + plot_h}" '
        f'stroke="var(--colour-border)" stroke-width="1"/>',
        f'<line x1="{pl}" y1="{pt}" '
        f'x2="{pl}" y2="{pt + plot_h}" '
        f'stroke="var(--colour-border)" stroke-width="1"/>',
        # Y-axis tick labels: min (bottom), max (top).
        f'<text x="{pl - 4}" y="{pt + plot_h + 4}" '
        f'text-anchor="end" font-size="9" '
        f'fill="var(--colour-text-muted)" '
        f"font-family=\"ui-monospace, 'SF Mono', Menlo, monospace\">"
        f"{_with_unit(str(round(y_min, 1)), unit_suffix)}</text>",
        f'<text x="{pl - 4}" y="{pt + 4}" '
        f'text-anchor="end" font-size="9" '
        f'fill="var(--colour-text-muted)" '
        f"font-family=\"ui-monospace, 'SF Mono', Menlo, monospace\">"
        f"{_with_unit(str(round(y_max, 1)), unit_suffix)}</text>",
    ]

    def _fmt_stat(val: float) -> str:
        """Compact numeric for labels/tooltips (int-narrow when whole)."""
        return str(int(val)) if val == int(val) else str(round(val, 1))

    def _hover_mark(
        *,
        role: str,
        group_label: str,
        value: float,
        cx: float,
        cy: float,
        label_dx: float,
    ) -> str:
        """Key-point hit target + figure shown on hover (CSS, no JS)."""
        shown = _with_unit(_fmt_stat(value), unit_suffix)
        role_title = role.replace("_", " ")
        lx = round(cx + label_dx, 2)
        ly = round(cy + 3, 2)
        return (
            f'<g class="dz-box-plot-mark" data-dz-box-mark="{_escape(role, quote=True)}">'
            f'<circle class="dz-box-plot-mark-hit" cx="{cx}" cy="{cy}" r="7" '
            f'fill="transparent" stroke="none"/>'
            f'<circle class="dz-box-plot-mark-dot" cx="{cx}" cy="{cy}" r="2" '
            f'fill="var(--colour-brand)" stroke="var(--colour-surface)" '
            f'stroke-width="1"/>'
            f'<text class="dz-box-plot-mark-label" x="{lx}" y="{ly}" '
            f'text-anchor="start" font-size="9" '
            f'fill="var(--colour-text)" '
            f"font-family=\"ui-monospace, 'SF Mono', Menlo, monospace\">"
            f"{shown}</text>"
            f"<title>{_escape(group_label)} {role_title}: {shown}</title>"
            f"</g>"
        )

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
        label_dx = box_half + 6

        # Whiskers only outside the IQR box (min→Q1, Q3→max).
        parts.append(
            f'<line class="dz-box-plot-whisker" x1="{col_x}" y1="{whisker_low_y}" '
            f'x2="{col_x}" y2="{q1_y}" '
            f'stroke="var(--colour-text-muted)" stroke-width="1"/>'
        )
        parts.append(
            f'<line class="dz-box-plot-whisker" x1="{col_x}" y1="{q3_y}" '
            f'x2="{col_x}" y2="{whisker_high_y}" '
            f'stroke="var(--colour-text-muted)" stroke-width="1"/>'
        )
        parts.append(
            f'<line class="dz-box-plot-whisker-cap" x1="{col_x - cap_half}" '
            f'y1="{whisker_low_y}" x2="{col_x + cap_half}" y2="{whisker_low_y}" '
            f'stroke="var(--colour-text-muted)" stroke-width="1"/>'
        )
        parts.append(
            f'<line class="dz-box-plot-whisker-cap" x1="{col_x - cap_half}" '
            f'y1="{whisker_high_y}" x2="{col_x + cap_half}" y2="{whisker_high_y}" '
            f'stroke="var(--colour-text-muted)" stroke-width="1"/>'
        )
        box_h = round(_y_raw(q1) - _y_raw(q3), 2)
        n_suffix = f", n={samples[i]}" if i < len(samples) else ""
        parts.append(
            f'<rect class="dz-box-plot-box" x="{col_x - box_half}" y="{q3_y}" '
            f'width="{round(box_w, 2)}" height="{box_h}" '
            f'fill="var(--colour-brand)" fill-opacity="0.18" '
            f'stroke="var(--colour-brand)" stroke-width="1">'
            f"<title>{_escape(group_label)}: "
            f"Q1 {_with_unit(str(round(q1, 1)), unit_suffix)}, "
            f"median {_with_unit(str(round(median, 1)), unit_suffix)}, "
            f"Q3 {_with_unit(str(round(q3, 1)), unit_suffix)}"
            f"{n_suffix}</title>"
            f"</rect>"
        )
        parts.append(
            f'<line class="dz-box-plot-median" x1="{col_x - box_half}" y1="{median_y}" '
            f'x2="{col_x + box_half}" y2="{median_y}" '
            f'stroke="var(--colour-brand)" stroke-width="1"/>'
        )
        for role, val, cy in (
            ("max", mx, whisker_high_y),
            ("q3", q3, q3_y),
            ("median", median, median_y),
            ("q1", q1, q1_y),
            ("min", mn, whisker_low_y),
        ):
            parts.append(
                _hover_mark(
                    role=role,
                    group_label=group_label,
                    value=val,
                    cx=col_x,
                    cy=cy,
                    label_dx=label_dx,
                )
            )
        parts.append(
            f'<text x="{col_x}" y="{h - 8}" '
            f'text-anchor="middle" font-size="10" '
            f'fill="var(--colour-text)" '
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
            f'stroke="var(--colour-text-muted)" '
            f'stroke-width="1" stroke-dasharray="{dasharray}">'
            f"<title>{_escape(ref.label)}: {_with_unit(_fmt_stat(ref.value), unit_suffix)}</title>"
            f"</line>"
        )

    parts.append("</svg>")
    return "".join(parts)


def _radar_polar_xy(
    index: int, count: int, ratio: float, cx: float, cy: float, r_max: float
) -> tuple[float, float]:
    """Polar → cartesian for radar spokes. Spoke 0 at 12 o'clock,
    going clockwise. `ratio` is the value as a fraction of r_max
    (0.0 = centre, 1.0 = spoke endpoint).

    Mirrors the `radar_polar_xy` Jinja global registered in
    `template_renderer.py` byte-for-byte — returns full-precision
    floats, NOT rounded. Jinja's `{{ v.x }}` emits the full repr;
    rounding here causes byte-equivalence drift on every vertex.
    """
    theta = -math.pi / 2 + 2 * math.pi * index / count
    return (
        cx + ratio * r_max * math.cos(theta),
        cy + ratio * r_max * math.sin(theta),
    )


def radar_svg(
    label: str,
    axes: tuple[tuple[str, float], ...],
) -> str:
    """Produce inline SVG for a Radar primitive.

    Single-series polar profile. Centre + radius leave 32px padding
    for spoke labels around the edge. Geometry: 320×320 viewBox,
    cx=cy=160, r_max=128. 4 concentric grid rings (25/50/75/100% of
    r_max) drawn as N-vertex polygons. N spoke axis lines from centre
    to spoke endpoints. Single data polygon with vertices at the
    value/max_val ratio along each spoke, plus circle markers at
    each vertex carrying `<title>` tooltips.

    Output matches `workspace/regions/radar.html` for the single-
    series case. Multi-series overlay (legacy supports up to 5
    palette colours) is deferred until the Radar primitive's `axes`
    schema gains a per-series dimension — currently single-series.
    """
    count = len(axes)
    if count < 3:
        return ""

    side = 320
    cx = side / 2
    cy = side / 2
    r_max = (side / 2) - 32

    values = [v for _, v in axes]
    max_val = max(values)
    if max_val <= 0:
        max_val = 1

    # Match Jinja's `{{ max_val | metric_number }}` rendering — K/M
    # suffixes for large values, plain int repr otherwise. Late import
    # to avoid the SVG module pulling dazzle.page at module load.
    # Pre-narrow to int when whole so the filter renders "9" not "9.0".
    from dazzle.render.filters import _metric_number_filter

    max_for_label = int(max_val) if max_val == int(max_val) else max_val
    max_val_label = _metric_number_filter(max_for_label)
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {side} {side}" '
        f'class="dz-radar-svg dz-chart-svg" role="img" '
        f'aria-label="{_escape(label, quote=True)} radar — '
        f'{count} spokes, peak {max_val_label}">'
    ]

    # Concentric polar grid rings.
    for ring_pct in (0.25, 0.5, 0.75, 1.0):
        ring_pts = " ".join(
            f"{x},{y}"
            for x, y in (_radar_polar_xy(i, count, ring_pct, cx, cy, r_max) for i in range(count))
        )
        parts.append(
            f'<polygon points="{ring_pts}" '
            f'fill="none" stroke="var(--colour-border)" '
            f'stroke-width="0.5" stroke-opacity="0.6"/>'
        )

    # Spoke axis lines.
    for i in range(count):
        ax_x, ax_y = _radar_polar_xy(i, count, 1.0, cx, cy, r_max)
        parts.append(
            f'<line x1="{cx}" y1="{cy}" '
            f'x2="{ax_x}" y2="{ax_y}" '
            f'stroke="var(--colour-border)" '
            f'stroke-width="0.5" stroke-opacity="0.7"/>'
        )

    # Data polygon — vertices at value/max_val ratio.
    poly_pts = []
    vertices: list[tuple[float, float, str, float]] = []
    for i, (axis_label, value) in enumerate(axes):
        ratio = value / max_val
        vx, vy = _radar_polar_xy(i, count, ratio, cx, cy, r_max)
        poly_pts.append(f"{vx},{vy}")
        vertices.append((vx, vy, axis_label, value))
    parts.append(
        f'<polygon points="{" ".join(poly_pts)}" '
        f'fill="var(--colour-brand)" fill-opacity="0.15" '
        f'stroke="var(--colour-brand)" stroke-width="1.5" '
        f'stroke-linejoin="round"/>'
    )

    # Vertex markers. Tooltip format matches legacy
    # `{{ v.label }} {{ series_name }}: {{ v.value | metric_number }}`
    # — for single-series default, series_name = "value".
    for vx, vy, axis_label, value in vertices:
        val_for_label = int(value) if value == int(value) else value
        val_label = _metric_number_filter(val_for_label)
        parts.append(
            f'<circle cx="{vx}" cy="{vy}" r="3" '
            f'fill="var(--colour-brand)" stroke="var(--colour-surface)" '
            f'stroke-width="1">'
            f"<title>{_escape(axis_label)} value: {val_label}</title>"
            f"</circle>"
        )

    # Spoke labels — placed slightly outside r_max so they don't
    # collide with the outermost ring.
    for i, (axis_label, _) in enumerate(axes):
        lx, ly = _radar_polar_xy(i, count, 1.0, cx, cy, r_max + 14)
        parts.append(
            f'<text x="{lx}" y="{ly}" '
            f'text-anchor="middle" dominant-baseline="middle" '
            f'font-size="10" fill="var(--colour-text)" '
            f"font-family=\"ui-monospace, 'SF Mono', Menlo, monospace\">"
            f"{_escape(axis_label)}</text>"
        )

    parts.append("</svg>")
    return "".join(parts)


def histogram_svg(
    label: str,
    bins: tuple[tuple[str, int, float, float], ...],
    *,
    reference_lines: tuple[Any, ...] = (),
    unit_suffix: str = "",
) -> str:
    """Produce inline SVG for a Histogram primitive.

    Continuous-axis bar chart matching the legacy
    `workspace/regions/histogram.html` template byte-for-byte. 400×140
    viewBox with 8/8/28/8 padding (top/right/bottom/left for x-axis
    tick labels). Bars are equal-width with a 1px gap between adjacent
    bins; vertical reference lines overlay at their x-position with a
    label hugging the top of the chart.

    Each `bins` entry is `(label, count, low, high)` — count drives
    bar height (relative to max_count), low/high define the continuous
    x-axis position. show_every heuristic for x-axis tick labels:
    every Nth bin where N = ceil(count/5), plus first + last always.
    """
    if not bins:
        return ""

    count = len(bins)
    max_count = max(b[1] for b in bins)
    if max_count <= 0:
        max_count = 1
    total = sum(b[1] for b in bins)
    x_min = bins[0][2]
    x_max = bins[-1][3]
    x_range = x_max - x_min
    if x_range <= 0:
        x_range = 1

    w = 400
    h = 140
    pt = 8
    pr = 8
    pb = 28
    pl = 8
    plot_w = w - pl - pr
    plot_h = h - pt - pb
    bar_w = plot_w / count

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {w} {h}" '
        f'class="dz-histogram-svg" role="img" '
        f'aria-label="{_escape(label, quote=True)} histogram — '
        f'{count} bins, {total} samples, peak {max_count}">',
        # Baseline.
        f'<line x1="{pl}" y1="{pt + plot_h}" '
        f'x2="{pl + plot_w}" y2="{pt + plot_h}" '
        f'stroke="var(--colour-border)" stroke-width="1"/>',
    ]

    # Bars.
    for i, (_lbl, cnt, _low, _high) in enumerate(bins):
        x = round(pl + i * bar_w, 2)
        bar_h = round(cnt / max_count * plot_h, 2)
        y = round(pt + plot_h - bar_h, 2)
        parts.append(
            f'<rect x="{x}" y="{y}" '
            f'width="{round(bar_w - 1, 2)}" height="{bar_h}" '
            f'fill="var(--colour-brand)" fill-opacity="0.6">'
            f"<title>{_escape(bins[i][0])}: {cnt}</title>"
            f"</rect>"
        )

    # Reference lines (clipped to x range).
    for ref in reference_lines:
        if ref.value < x_min or ref.value > x_max:
            continue
        ref_x = round(pl + (ref.value - x_min) / x_range * plot_w, 2)
        dasharray = _LINE_DASHARRAY.get(ref.style, "")
        # Match Jinja `{{ ref.value }}` — int-narrow whole values.
        ref_value_str = str(int(ref.value)) if ref.value == int(ref.value) else str(ref.value)
        parts.append(
            f'<line x1="{ref_x}" y1="{pt}" '
            f'x2="{ref_x}" y2="{pt + plot_h}" '
            f'stroke="var(--colour-text-muted)" '
            f'stroke-width="1" stroke-dasharray="{dasharray}">'
            f"<title>{_escape(ref.label)}: {_with_unit(ref_value_str, unit_suffix)}</title>"
            f"</line>"
        )
        parts.append(
            f'<text x="{ref_x}" y="{pt + 8}" '
            f'text-anchor="middle" font-size="9" '
            f'fill="var(--colour-text-muted)" '
            f"font-family=\"ui-monospace, 'SF Mono', Menlo, monospace\">"
            f"{_escape(ref.label)}</text>"
        )

    # X-axis tick labels — first, last, and every Nth.
    if count <= 5:
        show_every = 1
    else:
        # Match Jinja `(count / 5) | round(0, 'ceil') | int` — ceil division.
        show_every = -(-count // 5)
    for i, (_lbl, _cnt, low, _high) in enumerate(bins):
        if i == 0 or i == count - 1 or i % show_every == 0:
            lx = round(pl + i * bar_w + bar_w / 2, 2)
            low_str = (
                str(int(round(low, 1)))
                if round(low, 1) == int(round(low, 1))
                else str(round(low, 1))
            )
            parts.append(
                f'<text x="{lx}" y="{h - 8}" '
                f'text-anchor="middle" font-size="9" '
                f'fill="var(--colour-text-muted)" '
                f"font-family=\"ui-monospace, 'SF Mono', Menlo, monospace\">"
                f"{_with_unit(low_str, unit_suffix)}</text>"
            )

    parts.append("</svg>")
    return "".join(parts)


__all__ = ["box_plot_svg", "histogram_svg", "radar_svg", "time_series_svg"]
