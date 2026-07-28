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
            TimeSeriesPoint(label="3 Mar", value=42),
            TimeSeriesPoint(label="4 Mar", value=51),
            TimeSeriesPoint(label="5 Mar", value=48),
            TimeSeriesPoint(label="6 Mar", value=63),
            TimeSeriesPoint(label="7 Mar", value=71),
            TimeSeriesPoint(label="8 Mar", value=38),
            TimeSeriesPoint(label="9 Mar", value=35),
            TimeSeriesPoint(label="10 Mar", value=58),
            TimeSeriesPoint(label="11 Mar", value=66),
            TimeSeriesPoint(label="12 Mar", value=72),
            TimeSeriesPoint(label="13 Mar", value=80),
            TimeSeriesPoint(label="14 Mar", value=91),
            TimeSeriesPoint(label="15 Mar", value=47),
            TimeSeriesPoint(label="16 Mar", value=44),
        ],
        svg_html='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 120" class="dz-line-chart-svg dz-chart-svg" role="img" aria-label="Traffic time series — 14 buckets, peak 91"><line x1="8" y1="92" x2="392" y2="92" stroke="var(--colour-border)" stroke-width="1"/><polygon points="8,92 8.0,53.23 37.54,44.92 67.08,47.69 96.62,33.85 126.15,26.46 155.69,56.92 185.23,59.69 214.77,38.46 244.31,31.08 273.85,25.54 303.38,18.15 332.92,8.0 362.46,48.62 392.0,51.38 392,92" fill="var(--colour-brand)" fill-opacity="0.12" stroke="none"/><polyline points="8.0,53.23 37.54,44.92 67.08,47.69 96.62,33.85 126.15,26.46 155.69,56.92 185.23,59.69 214.77,38.46 244.31,31.08 273.85,25.54 303.38,18.15 332.92,8.0 362.46,48.62 392.0,51.38" fill="none" stroke="var(--colour-brand)" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/><circle cx="8.0" cy="53.23" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>3 Mar: 42</title></circle><circle cx="37.54" cy="44.92" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>4 Mar: 51</title></circle><circle cx="67.08" cy="47.69" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>5 Mar: 48</title></circle><circle cx="96.62" cy="33.85" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>6 Mar: 63</title></circle><circle cx="126.15" cy="26.46" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>7 Mar: 71</title></circle><circle cx="155.69" cy="56.92" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>8 Mar: 38</title></circle><circle cx="185.23" cy="59.69" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>9 Mar: 35</title></circle><circle cx="214.77" cy="38.46" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>10 Mar: 58</title></circle><circle cx="244.31" cy="31.08" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>11 Mar: 66</title></circle><circle cx="273.85" cy="25.54" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>12 Mar: 72</title></circle><circle cx="303.38" cy="18.15" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>13 Mar: 80</title></circle><circle cx="332.92" cy="8.0" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>14 Mar: 91</title></circle><circle cx="362.46" cy="48.62" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>15 Mar: 47</title></circle><circle cx="392.0" cy="51.38" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>16 Mar: 44</title></circle><text x="8.0" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">3 Mar</text><text x="96.62" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">6 Mar</text><text x="185.23" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">9 Mar</text><text x="273.85" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">12 Mar</text><text x="362.46" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">15 Mar</text><text x="392.0" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">16 Mar</text></svg>',
        peak_display="91",
    ),
    TimeSeries(
        label="Stacked",
        view="area",
        series=[
            TimeSeriesLayer(
                name="API",
                points=[
                    TimeSeriesPoint(label="W1", value=12),
                    TimeSeriesPoint(label="W2", value=14),
                    TimeSeriesPoint(label="W3", value=13),
                    TimeSeriesPoint(label="W4", value=18),
                    TimeSeriesPoint(label="W5", value=22),
                    TimeSeriesPoint(label="W6", value=20),
                    TimeSeriesPoint(label="W7", value=24),
                    TimeSeriesPoint(label="W8", value=26),
                ],
            ),
            TimeSeriesLayer(
                name="Webhooks",
                points=[
                    TimeSeriesPoint(label="W1", value=6),
                    TimeSeriesPoint(label="W2", value=8),
                    TimeSeriesPoint(label="W3", value=9),
                    TimeSeriesPoint(label="W4", value=7),
                    TimeSeriesPoint(label="W5", value=11),
                    TimeSeriesPoint(label="W6", value=12),
                    TimeSeriesPoint(label="W7", value=10),
                    TimeSeriesPoint(label="W8", value=14),
                ],
            ),
        ],
        svg_html='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 120" class="dz-line-chart-svg dz-chart-svg" role="img" aria-label="Traffic time series — 2 series, 8 buckets, peak 26"><line x1="8" y1="92" x2="392" y2="92" stroke="var(--colour-border)" stroke-width="1"/><polygon points="8,92 8.0,53.23 62.86,46.77 117.71,50.0 172.57,33.85 227.43,20.92 282.29,27.38 337.14,14.46 392.0,8.0 392,92" fill="var(--colour-brand)" fill-opacity="0.12" stroke="none"/><polyline points="8.0,53.23 62.86,46.77 117.71,50.0 172.57,33.85 227.43,20.92 282.29,27.38 337.14,14.46 392.0,8.0" fill="none" stroke="var(--colour-brand)" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/><circle cx="8.0" cy="53.23" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>API · W1: 12</title></circle><circle cx="62.86" cy="46.77" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>API · W2: 14</title></circle><circle cx="117.71" cy="50.0" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>API · W3: 13</title></circle><circle cx="172.57" cy="33.85" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>API · W4: 18</title></circle><circle cx="227.43" cy="20.92" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>API · W5: 22</title></circle><circle cx="282.29" cy="27.38" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>API · W6: 20</title></circle><circle cx="337.14" cy="14.46" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>API · W7: 24</title></circle><circle cx="392.0" cy="8.0" r="2.5" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"><title>API · W8: 26</title></circle><polygon points="8,92 8.0,72.62 62.86,66.15 117.71,62.92 172.57,69.38 227.43,56.46 282.29,53.23 337.14,59.69 392.0,46.77 392,92" fill="var(--colour-info)" fill-opacity="0.12" stroke="none"/><polyline points="8.0,72.62 62.86,66.15 117.71,62.92 172.57,69.38 227.43,56.46 282.29,53.23 337.14,59.69 392.0,46.77" fill="none" stroke="var(--colour-info)" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/><circle cx="8.0" cy="72.62" r="2.5" fill="var(--colour-info)" stroke="var(--colour-surface)" stroke-width="1"><title>Webhooks · W1: 6</title></circle><circle cx="62.86" cy="66.15" r="2.5" fill="var(--colour-info)" stroke="var(--colour-surface)" stroke-width="1"><title>Webhooks · W2: 8</title></circle><circle cx="117.71" cy="62.92" r="2.5" fill="var(--colour-info)" stroke="var(--colour-surface)" stroke-width="1"><title>Webhooks · W3: 9</title></circle><circle cx="172.57" cy="69.38" r="2.5" fill="var(--colour-info)" stroke="var(--colour-surface)" stroke-width="1"><title>Webhooks · W4: 7</title></circle><circle cx="227.43" cy="56.46" r="2.5" fill="var(--colour-info)" stroke="var(--colour-surface)" stroke-width="1"><title>Webhooks · W5: 11</title></circle><circle cx="282.29" cy="53.23" r="2.5" fill="var(--colour-info)" stroke="var(--colour-surface)" stroke-width="1"><title>Webhooks · W6: 12</title></circle><circle cx="337.14" cy="59.69" r="2.5" fill="var(--colour-info)" stroke="var(--colour-surface)" stroke-width="1"><title>Webhooks · W7: 10</title></circle><circle cx="392.0" cy="46.77" r="2.5" fill="var(--colour-info)" stroke="var(--colour-surface)" stroke-width="1"><title>Webhooks · W8: 14</title></circle><text x="8.0" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">W1</text><text x="117.71" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">W3</text><text x="227.43" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">W5</text><text x="337.14" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">W7</text><text x="392.0" y="112" text-anchor="middle" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">W8</text></svg>',
        legend_html='<ul class="dz-chart-legend"><li class="dz-chart-legend-item"><span class="dz-chart-legend-swatch" style="background:var(--colour-brand)"></span><span class="dz-chart-legend-name">API</span></li><li class="dz-chart-legend-item"><span class="dz-chart-legend-swatch" style="background:var(--colour-success)"></span><span class="dz-chart-legend-name">Webhooks</span></li></ul>',
        peak_display="26",
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
