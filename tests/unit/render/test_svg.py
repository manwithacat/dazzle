"""Phase 4B.1.c — `dazzle.render.svg` time-series helper tests.

Pins the geometry contract: viewBox dimensions, polyline point format,
reference-band rect attrs, reference-line dasharray, x-axis label
heuristic. These are the byte-level guarantees the SVG arc relies on
for dual-path validation against the legacy Jinja chart template.
"""

from __future__ import annotations

from dataclasses import dataclass

from dazzle.render.svg import box_plot_svg, time_series_svg


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
    svg = time_series_svg("Tickets", (("a", 1.0), ("b", 5.0), ("c", 3.0)))
    assert 'aria-label="Tickets time series — 3 buckets, peak 5.0"' in svg


def test_polyline_points_use_padding_left() -> None:
    """First point sits at x = padding_left (8); last at width - padding_right."""
    svg = time_series_svg("x", (("a", 1.0), ("b", 2.0)))
    assert 'points="8,' in svg
    assert " 392.0," in svg


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
