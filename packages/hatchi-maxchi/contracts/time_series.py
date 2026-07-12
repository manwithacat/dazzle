"""HYPERPART: time-series — line / area sequential charts.

Dual-lock unit is the region root (``data-dz-time-series``). Geometry is
server-computed SVG (``svg_html`` trusted). Multi-series legends ride
trusted ``legend_html``. Wrapper class remains view-specific
(``dz-line-chart-region`` / ``dz-area-chart-region``) for CSS.
"""

from __future__ import annotations

import html
from typing import Literal

from pydantic import BaseModel, Field

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="time-series",
    root="[data-dz-time-series]",
    nodes=(
        Node(
            "[data-dz-time-series]",
            attrs={"data-dz-time-series": Present()},
        ),
    ),
)

TimeSeriesView = Literal["line", "area"]


class TimeSeriesPoint(BaseModel):
    """One (label, value) sample on the shared axis."""

    label: str
    value: float = 0.0


class TimeSeriesLayer(BaseModel):
    """One named series in a multi-series chart."""

    name: str
    points: list[TimeSeriesPoint] = Field(default_factory=list)


class TimeSeries(BaseModel):
    """Line or area chart.

    - ``view`` → ``line`` | ``area`` (wrapper class + SVG style)
    - ``points`` → single-series samples
    - ``series`` → multi-series layers (takes precedence when non-empty)
    - ``svg_html`` → trusted server-rendered SVG body
    - ``legend_html`` → trusted multi-series legend markup (optional)
    - ``peak_display`` → host-formatted peak for the summary line
    """

    label: str = ""
    view: TimeSeriesView = "line"
    points: list[TimeSeriesPoint] = Field(default_factory=list)
    series: list[TimeSeriesLayer] = Field(default_factory=list)
    svg_html: str = Field(
        default="",
        description="Trusted inline SVG markup for the chart body.",
    )
    legend_html: str = ""
    peak_display: str = ""
    # Empty default matches legacy emit: bare wrapper, no empty-state copy.
    empty_message: str = ""


EXEMPLARS: list[TimeSeries] = [
    TimeSeries(
        label="Traffic",
        view="line",
        points=[
            TimeSeriesPoint(label="Mon", value=12),
            TimeSeriesPoint(label="Tue", value=18),
            TimeSeriesPoint(label="Wed", value=9),
        ],
        svg_html=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 48" '
            'role="img" aria-label="Line chart — 3 buckets">'
            '<polyline points="4,30 90,10 176,34" fill="none" '
            'stroke="var(--colour-brand)" stroke-width="2"/>'
            "</svg>"
        ),
        peak_display="18",
    ),
    TimeSeries(
        label="Stacked",
        view="area",
        series=[
            TimeSeriesLayer(
                name="A",
                points=[
                    TimeSeriesPoint(label="Q1", value=10),
                    TimeSeriesPoint(label="Q2", value=14),
                ],
            ),
            TimeSeriesLayer(
                name="B",
                points=[
                    TimeSeriesPoint(label="Q1", value=6),
                    TimeSeriesPoint(label="Q2", value=8),
                ],
            ),
        ],
        svg_html=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 48" '
            'role="img" aria-label="Area chart — 2 series">'
            '<polygon points="4,40 90,20 176,28 176,48 4,48" '
            'fill="var(--colour-brand)" fill-opacity="0.3"/>'
            "</svg>"
        ),
        legend_html=(
            '<ul class="dz-chart-legend">'
            '<li class="dz-chart-legend-item">'
            '<span class="dz-chart-legend-swatch" style="background:var(--colour-brand)"></span>'
            '<span class="dz-chart-legend-name">A</span></li>'
            '<li class="dz-chart-legend-item">'
            '<span class="dz-chart-legend-swatch" style="background:var(--colour-success)"></span>'
            '<span class="dz-chart-legend-name">B</span></li>'
            "</ul>"
        ),
        peak_display="14",
    ),
    TimeSeries(points=[]),
]


def _wrapper_class(view: TimeSeriesView) -> str:
    return "dz-area-chart-region" if view == "area" else "dz-line-chart-region"


def render(t: TimeSeries) -> str:
    """Model → line/area chart region."""
    cls = _wrapper_class(t.view)
    if not t.points and not t.series:
        if t.empty_message:
            return (
                f'<div class="{cls}" data-dz-time-series>'
                f'<p class="dz-empty-dense" role="status">'
                f"{html.escape(t.empty_message)}</p>"
                f"</div>"
            )
        return f'<div class="{cls}" data-dz-time-series></div>'

    if t.series:
        axis_labels = {p.label for layer in t.series for p in layer.points}
        peak = t.peak_display
        if not peak:
            vals = [p.value for layer in t.series for p in layer.points]
            max_val = max(vals, default=0) or 0
            peak = str(int(max_val)) if max_val == int(max_val) else str(max_val)
        summary = (
            f'<p class="dz-chart-summary">{len(axis_labels)} buckets · '
            f"{len(t.series)} series · peak {html.escape(peak)}</p>"
        )
        return f'<div class="{cls}" data-dz-time-series>{t.svg_html}{t.legend_html}{summary}</div>'

    peak = t.peak_display
    if not peak:
        max_val = max((p.value for p in t.points), default=0) or 0
        peak = str(int(max_val)) if max_val == int(max_val) else str(max_val)
    summary = f'<p class="dz-chart-summary">{len(t.points)} buckets · peak {html.escape(peak)}</p>'
    return f'<div class="{cls}" data-dz-time-series>{t.svg_html}{summary}</div>'


__all__ = [
    "DOM_CONTRACT",
    "TimeSeriesView",
    "TimeSeriesPoint",
    "TimeSeriesLayer",
    "TimeSeries",
    "EXEMPLARS",
    "render",
]
