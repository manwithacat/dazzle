"""Phase 4B.1.c — `dazzle.render.svg` time-series helper tests.

Pins the geometry contract: viewBox dimensions, polyline point format,
reference-band rect attrs, reference-line dasharray, x-axis label
heuristic. These are the byte-level guarantees the SVG arc relies on
for dual-path validation against the legacy Jinja chart template.
"""

from __future__ import annotations

from dataclasses import dataclass

from dazzle.render.svg import box_plot_svg, radar_svg, time_series_svg


@dataclass
class _Ref:
    label: str
    value: float
    style: str = "solid"


@dataclass
class _Band:
    label: str
    from_value: float
    to_value: float
    color: str = "target"


def test_empty_points_renders_nothing() -> None:
    assert time_series_svg("x", ()) == ""


def test_basic_line_emits_svg_with_polyline() -> None:
    svg = time_series_svg("Revenue", (("Jan", 10.0), ("Feb", 20.0), ("Mar", 15.0)))
    assert svg.startswith("<svg ")
    assert 'viewBox="0 0 400 120"' in svg
    assert "<polyline " in svg
    assert "<polygon " in svg  # area fill
    assert "<circle " in svg  # data points
    assert svg.endswith("</svg>")


def test_axis_labels_appear_in_text_elements() -> None:
    svg = time_series_svg("x", (("Jan", 1.0), ("Feb", 2.0), ("Mar", 3.0)))
    assert "<text " in svg
    assert ">Jan<" in svg and ">Feb<" in svg and ">Mar<" in svg


def test_reference_line_renders_with_dasharray() -> None:
    svg = time_series_svg(
        "x",
        (("Jan", 50.0), ("Feb", 75.0)),
        reference_lines=(_Ref("Target", 100.0, style="dashed"),),
    )
    assert 'stroke-dasharray="4,3"' in svg
    assert "<title>Target: 100.0</title>" in svg


def test_reference_band_renders_with_fill_opacity() -> None:
    svg = time_series_svg(
        "x",
        (("a", 1.0), ("b", 2.0)),
        reference_bands=(_Band("Healthy", 0.5, 1.5, color="positive"),),
    )
    assert "<rect " in svg
    assert 'fill-opacity="0.12"' in svg
    assert "hsl(145, 55%, 45%)" in svg  # positive colour
    assert "<title>Healthy: 0.5–1.5</title>" in svg


def test_unknown_reference_line_style_falls_back_to_empty_dasharray() -> None:
    svg = time_series_svg(
        "x",
        (("a", 1.0),),
        reference_lines=(_Ref("X", 1.0, style="wavy"),),
    )
    assert 'stroke-dasharray=""' in svg


def test_aria_label_includes_count_and_peak() -> None:
    """v0.66.110: int-narrowing in aria-label so whole-valued floats
    render as "5" not "5.0" (matches Jinja's `{{ max_val }}`)."""
    svg = time_series_svg("Tickets", (("a", 1.0), ("b", 5.0), ("c", 3.0)))
    assert 'aria-label="Tickets time series — 3 buckets, peak 5"' in svg


def test_polyline_points_use_padding_left() -> None:
    """First point sits at x = padding_left (8); last at width - padding_right."""
    svg = time_series_svg("x", (("a", 1.0), ("b", 2.0)))
    assert 'points="8,' in svg
    assert " 392.0," in svg


# === time_series_svg multi-series (#1473) ===


def test_multi_series_emits_one_polyline_and_polygon_per_series() -> None:
    svg = time_series_svg(
        "Alerts",
        (),
        view="area",
        series=(
            ("high", (("W1", 2.0), ("W2", 3.0))),
            ("low", (("W1", 1.0), ("W2", 4.0))),
        ),
    )
    assert svg.startswith("<svg ") and svg.endswith("</svg>")
    assert svg.count("<polyline ") == 2  # one line per series
    assert svg.count("<polygon ") == 2  # one area fill per series


def test_multi_series_tooltips_name_their_series() -> None:
    svg = time_series_svg(
        "Alerts",
        (),
        view="area",
        series=(
            ("high", (("W1", 2.0),)),
            ("low", (("W1", 1.0),)),
        ),
    )
    assert "<title>high · W1: 2</title>" in svg
    assert "<title>low · W1: 1</title>" in svg


def test_multi_series_colours_each_series_distinctly() -> None:
    svg = time_series_svg(
        "Alerts",
        (),
        view="area",
        series=(
            ("high", (("W1", 2.0),)),
            ("low", (("W1", 1.0),)),
        ),
    )
    assert "var(--colour-brand)" in svg  # series 0
    assert "var(--colour-info)" in svg  # series 1


def test_multi_series_shares_x_axis_as_ordered_union_of_labels() -> None:
    # Second series introduces W3, which the first lacks — the axis spans both.
    svg = time_series_svg(
        "Alerts",
        (),
        view="area",
        series=(
            ("high", (("W1", 2.0), ("W2", 3.0))),
            ("low", (("W2", 1.0), ("W3", 4.0))),
        ),
    )
    assert ">W1<" in svg and ">W2<" in svg and ">W3<" in svg


def test_multi_series_aria_label_reports_series_count() -> None:
    svg = time_series_svg(
        "Alerts",
        (),
        view="area",
        series=(
            ("high", (("W1", 2.0),)),
            ("low", (("W1", 1.0),)),
        ),
    )
    assert "2 series" in svg


# === box_plot_svg ===


def test_box_plot_empty_groups_renders_nothing() -> None:
    assert box_plot_svg("x", ()) == ""


def test_box_plot_emits_svg_with_box_and_whiskers() -> None:
    svg = box_plot_svg(
        "Latency",
        (("p50", 0.0, 1.0, 2.0, 3.0, 4.0), ("p99", 5.0, 6.0, 7.0, 8.0, 9.0)),
    )
    assert svg.startswith("<svg ")
    assert "<rect " in svg  # box bodies
    # 2 boxes → 6 whisker lines (stem + 2 caps each), 2 medians, 2 baselines, 2 ticks
    assert svg.count("<line ") >= 8
    # Group labels
    assert ">p50<" in svg and ">p99<" in svg
    # Median tooltip carries quartile data
    assert "<title>p50: Q1 1.0, median 2.0, Q3 3.0</title>" in svg
    assert svg.endswith("</svg>")


def test_box_plot_width_caps_at_460() -> None:
    """Many groups → width caps at 460 (legacy contract)."""
    groups = tuple((f"g{i}", 0.0, 1.0, 2.0, 3.0, 4.0) for i in range(20))
    svg = box_plot_svg("x", groups)
    assert 'viewBox="0 0 460 200"' in svg


def test_box_plot_width_scales_below_cap() -> None:
    """Few groups → 56*count + 64 px wide."""
    svg = box_plot_svg("x", (("a", 0.0, 1.0, 2.0, 3.0, 4.0),))
    assert 'viewBox="0 0 120 200"' in svg  # 56*1 + 64 = 120


def test_box_plot_aria_label_includes_range() -> None:
    svg = box_plot_svg(
        "Latency",
        (("p50", 0.0, 1.0, 2.0, 3.0, 4.0), ("p99", 5.0, 6.0, 7.0, 8.0, 9.0)),
    )
    assert 'aria-label="Latency box plot — 2 groups, range 0.0–9.0"' in svg


# === radar_svg ===


def test_radar_under_three_axes_renders_nothing() -> None:
    """Radar with <3 axes is degenerate (legacy falls back to a list)."""
    assert radar_svg("x", (("a", 1.0), ("b", 2.0))) == ""


def test_radar_emits_svg_with_grid_polygon_and_data_polygon() -> None:
    svg = radar_svg(
        "Skills",
        (("Python", 9.0), ("Go", 7.0), ("Rust", 5.0), ("JavaScript", 6.0)),
    )
    assert svg.startswith("<svg ")
    assert 'viewBox="0 0 320 320"' in svg
    # 4 grid rings + 1 data polygon = 5 polygons total
    assert svg.count("<polygon ") == 5
    # 4 spoke axis lines
    assert svg.count("<line ") == 4
    # 4 vertex circles
    assert svg.count("<circle ") == 4
    # Spoke labels in <text>
    assert ">Python<" in svg and ">Go<" in svg
    # v0.66.110: tooltip format aligned with legacy macro
    # `{{ label }} {{ series_name }}: {{ value | metric_number }}` —
    # for single-series default series_name="value", and whole-valued
    # floats render via int-narrow.
    assert "<title>Python value: 9</title>" in svg
    assert svg.endswith("</svg>")


def test_radar_aria_label_includes_count_and_peak() -> None:
    """v0.66.110: peak goes through metric_number filter with int-narrow
    so whole-valued floats render as "5" not "5.0"."""
    svg = radar_svg("x", (("a", 3.0), ("b", 5.0), ("c", 1.0)))
    assert 'aria-label="x radar — 3 spokes, peak 5"' in svg


def test_radar_first_spoke_at_top_clockwise() -> None:
    """Spoke 0 should be at 12 o'clock (cx=160, cy=160-r_max=32)."""
    svg = radar_svg("x", (("top", 1.0), ("right", 1.0), ("bottom", 1.0), ("left", 1.0)))
    # Spoke 0 (top) endpoint: cx=160, cy = 160 - 128 = 32. The full-ring
    # 100% polygon should contain "160.0,32.0" as its first vertex.
    assert "160.0,32.0" in svg


def test_box_plot_reference_line_clipped_to_y_range() -> None:
    """Reference lines outside [y_min, y_max] are dropped (legacy behaviour)."""
    svg = box_plot_svg(
        "x",
        (("a", 0.0, 1.0, 2.0, 3.0, 4.0),),
        reference_lines=(
            _Ref("InRange", 2.5, style="dashed"),
            _Ref("OutOfRange", 100.0, style="solid"),
        ),
    )
    assert "InRange" in svg
    assert "OutOfRange" not in svg
