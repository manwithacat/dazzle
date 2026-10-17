"""Phase 4B.1.c — `dazzle.render.svg` time-series helper tests.

Pins the geometry contract: viewBox dimensions, polyline point format,
reference-band rect attrs, reference-line dasharray, x-axis label
heuristic. These are the byte-level guarantees the SVG arc relies on
for dual-path validation against the legacy Jinja chart template.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pytest

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


_TWO_SERIES = (("high", (("W1", 2.0),)), ("low", (("W1", 1.0),)))


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(lambda: time_series_svg("x", ()), id="time-series-empty-points"),
    ],
)
def test_degenerate_input_renders_nothing(build: Callable[[], str]) -> None:
    assert build() == ""


@pytest.mark.parametrize(
    ("build", "present", "counts"),
    [
        pytest.param(
            lambda: time_series_svg("Revenue", (("Jan", 10.0), ("Feb", 20.0), ("Mar", 15.0))),
            # polyline line, polygon area fill, circle data points, text axis labels
            ('viewBox="0 0 400 120"', "<polyline ", "<polygon ", "<circle ", "<text "),
            {},
            id="line-emits-polyline-area-points-and-axis-labels",
        ),
        pytest.param(
            lambda: time_series_svg("x", (("Jan", 1.0), ("Feb", 2.0), ("Mar", 3.0))),
            (">Jan<", ">Feb<", ">Mar<"),
            {},
            id="axis-labels-in-text-elements",
        ),
        pytest.param(
            lambda: time_series_svg(
                "x",
                (("Jan", 50.0), ("Feb", 75.0)),
                reference_lines=(_Ref("Target", 100.0, style="dashed"),),
            ),
            ('stroke-dasharray="4,3"', "<title>Target: 100.0</title>"),
            {},
            id="reference-line-dashed",
        ),
        pytest.param(
            lambda: time_series_svg(
                "x", (("a", 1.0),), reference_lines=(_Ref("X", 1.0, style="wavy"),)
            ),
            ('stroke-dasharray=""',),
            {},
            id="reference-line-unknown-style-empty-dasharray",
        ),
        pytest.param(
            lambda: time_series_svg(
                "x",
                (("a", 1.0), ("b", 2.0)),
                reference_bands=(_Band("Healthy", 0.5, 1.5, color="positive"),),
            ),
            (
                "<rect ",
                'fill-opacity="0.12"',
                "hsl(145, 55%, 45%)",
                "<title>Healthy: 0.5–1.5</title>",
            ),
            {},
            id="reference-band-rect-with-fill-opacity",
        ),
        # v0.66.110: whole-valued floats int-narrow ("5" not "5.0").
        pytest.param(
            lambda: time_series_svg("Tickets", (("a", 1.0), ("b", 5.0), ("c", 3.0))),
            ('aria-label="Tickets time series — 3 buckets, peak 5"',),
            {},
            id="aria-label-count-and-peak",
        ),
        # First point at x = padding_left (8); last at width - padding_right.
        pytest.param(
            lambda: time_series_svg("x", (("a", 1.0), ("b", 2.0))),
            ('points="8,', " 392.0,"),
            {},
            id="polyline-points-respect-padding",
        ),
        # #1473 multi-series: one line + one area fill per series.
        pytest.param(
            lambda: time_series_svg(
                "Alerts",
                (),
                view="area",
                series=(
                    ("high", (("W1", 2.0), ("W2", 3.0))),
                    ("low", (("W1", 1.0), ("W2", 4.0))),
                ),
            ),
            (),
            {"<polyline ": 2, "<polygon ": 2},
            id="multi-series-polyline-and-polygon-per-series",
        ),
        pytest.param(
            lambda: time_series_svg("Alerts", (), view="area", series=_TWO_SERIES),
            (
                "<title>high · W1: 2</title>",
                "<title>low · W1: 1</title>",
                "var(--colour-brand)",
                "var(--colour-info)",
                "2 series",
            ),
            {},
            id="multi-series-named-tooltips-distinct-colours-aria-count",
        ),
        # The second series introduces W3 — the shared axis spans both.
        pytest.param(
            lambda: time_series_svg(
                "Alerts",
                (),
                view="area",
                series=(
                    ("high", (("W1", 2.0), ("W2", 3.0))),
                    ("low", (("W2", 1.0), ("W3", 4.0))),
                ),
            ),
            (">W1<", ">W2<", ">W3<"),
            {},
            id="multi-series-x-axis-is-ordered-union",
        ),
    ],
)
def test_svg_output(
    build: Callable[[], str], present: tuple[str, ...], counts: dict[str, int]
) -> None:
    svg = build()
    assert svg.startswith("<svg ") and svg.endswith("</svg>")
    assert [s for s in present if s not in svg] == []
    assert {s: svg.count(s) for s in counts} == counts
