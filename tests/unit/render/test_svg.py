"""Phase 4B.1.c — `dazzle.render.svg` time-series helper tests.

Pins the geometry contract: viewBox dimensions, polyline point format,
reference-band rect attrs, reference-line dasharray, x-axis label
heuristic. These are the byte-level guarantees the SVG arc relies on
for dual-path validation against the legacy Jinja chart template.
"""

from __future__ import annotations

from dataclasses import dataclass

from dazzle.render.svg import time_series_svg


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
