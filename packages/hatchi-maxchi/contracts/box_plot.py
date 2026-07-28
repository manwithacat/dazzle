"""HYPERPART: box-plot — per-group quartile distribution chart.

Dual-lock unit is the region root. Whisker/quartile geometry is
server-computed SVG (``svg_html`` trusted); the summary line is derived
from group count + sample totals.
"""

from __future__ import annotations

import html

from pydantic import BaseModel, Field

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="box-plot",
    root="[data-dz-box-plot]",
    nodes=(
        Node(
            "[data-dz-box-plot]",
            attrs={"data-dz-box-plot": Present()},
        ),
    ),
)


class BoxPlotGroup(BaseModel):
    """One group five-number summary (+ optional sample count)."""

    label: str
    min: float = 0.0
    q1: float = 0.0
    median: float = 0.0
    q3: float = 0.0
    max: float = 0.0
    samples: int = 0


class BoxPlot(BaseModel):
    """Distribution box-plot.

    - ``groups`` → series data (summary is derived)
    - ``svg_html`` → trusted server-rendered SVG body (empty → no glyph)
    - ``label`` → chart title used by host SVG helpers (not always in DOM)
    """

    label: str = ""
    groups: list[BoxPlotGroup] = Field(default_factory=list)
    svg_html: str = Field(
        default="",
        description="Trusted inline SVG markup for the chart body.",
    )
    empty_message: str = "No data available."


EXEMPLARS: list[BoxPlot] = [
    BoxPlot(
        label="Latency",
        groups=[
            BoxPlotGroup(label="API", min=10, q1=20, median=30, q3=45, max=80, samples=120),
            BoxPlotGroup(label="Web", min=5, q1=15, median=25, q3=40, max=70, samples=98),
            BoxPlotGroup(label="Jobs", min=12, q1=22, median=35, q3=50, max=95, samples=64),
        ],
        svg_html='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 232 200" class="dz-box-plot-svg" role="img" aria-label="Latency box plot — 3 groups, range 5.0–95.0"><line x1="32" y1="168" x2="224" y2="168" stroke="var(--colour-border)" stroke-width="1"/><line x1="32" y1="8" x2="32" y2="168" stroke="var(--colour-border)" stroke-width="1"/><text x="28" y="172" text-anchor="end" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">5.0</text><text x="28" y="12" text-anchor="end" font-size="9" fill="var(--colour-text-muted)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">95.0</text><line class="dz-box-plot-whisker" x1="64.0" y1="159.11" x2="64.0" y2="141.33" stroke="var(--colour-text-muted)" stroke-width="1"/><line class="dz-box-plot-whisker" x1="64.0" y1="96.89" x2="64.0" y2="34.67" stroke="var(--colour-text-muted)" stroke-width="1"/><line class="dz-box-plot-whisker-cap" x1="55.0" y1="159.11" x2="73.0" y2="159.11" stroke="var(--colour-text-muted)" stroke-width="1"/><line class="dz-box-plot-whisker-cap" x1="55.0" y1="34.67" x2="73.0" y2="34.67" stroke="var(--colour-text-muted)" stroke-width="1"/><rect class="dz-box-plot-box" x="46.0" y="96.89" width="36" height="44.44" fill="var(--colour-brand)" fill-opacity="0.18" stroke="var(--colour-brand)" stroke-width="1"><title>API: Q1 20.0, median 30.0, Q3 45.0, n=120</title></rect><line class="dz-box-plot-median" x1="46.0" y1="123.56" x2="82.0" y2="123.56" stroke="var(--colour-brand)" stroke-width="1"/><g class="dz-box-plot-mark" data-dz-box-mark="max"><circle class="dz-box-plot-mark-hit" cx="64.0" cy="34.67" r="7" fill="transparent" stroke="none"/><circle class="dz-box-plot-mark-dot" cx="64.0" cy="34.67" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/><text class="dz-box-plot-mark-label" x="88.0" y="37.67" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">80</text><title>API max: 80</title></g><g class="dz-box-plot-mark" data-dz-box-mark="q3"><circle class="dz-box-plot-mark-hit" cx="64.0" cy="96.89" r="7" fill="transparent" stroke="none"/><circle class="dz-box-plot-mark-dot" cx="64.0" cy="96.89" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/><text class="dz-box-plot-mark-label" x="88.0" y="99.89" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">45</text><title>API q3: 45</title></g><g class="dz-box-plot-mark" data-dz-box-mark="median"><circle class="dz-box-plot-mark-hit" cx="64.0" cy="123.56" r="7" fill="transparent" stroke="none"/><circle class="dz-box-plot-mark-dot" cx="64.0" cy="123.56" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/><text class="dz-box-plot-mark-label" x="88.0" y="126.56" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">30</text><title>API median: 30</title></g><g class="dz-box-plot-mark" data-dz-box-mark="q1"><circle class="dz-box-plot-mark-hit" cx="64.0" cy="141.33" r="7" fill="transparent" stroke="none"/><circle class="dz-box-plot-mark-dot" cx="64.0" cy="141.33" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/><text class="dz-box-plot-mark-label" x="88.0" y="144.33" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">20</text><title>API q1: 20</title></g><g class="dz-box-plot-mark" data-dz-box-mark="min"><circle class="dz-box-plot-mark-hit" cx="64.0" cy="159.11" r="7" fill="transparent" stroke="none"/><circle class="dz-box-plot-mark-dot" cx="64.0" cy="159.11" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/><text class="dz-box-plot-mark-label" x="88.0" y="162.11" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">10</text><title>API min: 10</title></g><text x="64.0" y="192" text-anchor="middle" font-size="10" fill="var(--colour-text)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">API</text><line class="dz-box-plot-whisker" x1="128.0" y1="168.0" x2="128.0" y2="150.22" stroke="var(--colour-text-muted)" stroke-width="1"/><line class="dz-box-plot-whisker" x1="128.0" y1="105.78" x2="128.0" y2="52.44" stroke="var(--colour-text-muted)" stroke-width="1"/><line class="dz-box-plot-whisker-cap" x1="119.0" y1="168.0" x2="137.0" y2="168.0" stroke="var(--colour-text-muted)" stroke-width="1"/><line class="dz-box-plot-whisker-cap" x1="119.0" y1="52.44" x2="137.0" y2="52.44" stroke="var(--colour-text-muted)" stroke-width="1"/><rect class="dz-box-plot-box" x="110.0" y="105.78" width="36" height="44.44" fill="var(--colour-brand)" fill-opacity="0.18" stroke="var(--colour-brand)" stroke-width="1"><title>Web: Q1 15.0, median 25.0, Q3 40.0, n=98</title></rect><line class="dz-box-plot-median" x1="110.0" y1="132.44" x2="146.0" y2="132.44" stroke="var(--colour-brand)" stroke-width="1"/><g class="dz-box-plot-mark" data-dz-box-mark="max"><circle class="dz-box-plot-mark-hit" cx="128.0" cy="52.44" r="7" fill="transparent" stroke="none"/><circle class="dz-box-plot-mark-dot" cx="128.0" cy="52.44" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/><text class="dz-box-plot-mark-label" x="152.0" y="55.44" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">70</text><title>Web max: 70</title></g><g class="dz-box-plot-mark" data-dz-box-mark="q3"><circle class="dz-box-plot-mark-hit" cx="128.0" cy="105.78" r="7" fill="transparent" stroke="none"/><circle class="dz-box-plot-mark-dot" cx="128.0" cy="105.78" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/><text class="dz-box-plot-mark-label" x="152.0" y="108.78" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">40</text><title>Web q3: 40</title></g><g class="dz-box-plot-mark" data-dz-box-mark="median"><circle class="dz-box-plot-mark-hit" cx="128.0" cy="132.44" r="7" fill="transparent" stroke="none"/><circle class="dz-box-plot-mark-dot" cx="128.0" cy="132.44" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/><text class="dz-box-plot-mark-label" x="152.0" y="135.44" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">25</text><title>Web median: 25</title></g><g class="dz-box-plot-mark" data-dz-box-mark="q1"><circle class="dz-box-plot-mark-hit" cx="128.0" cy="150.22" r="7" fill="transparent" stroke="none"/><circle class="dz-box-plot-mark-dot" cx="128.0" cy="150.22" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/><text class="dz-box-plot-mark-label" x="152.0" y="153.22" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">15</text><title>Web q1: 15</title></g><g class="dz-box-plot-mark" data-dz-box-mark="min"><circle class="dz-box-plot-mark-hit" cx="128.0" cy="168.0" r="7" fill="transparent" stroke="none"/><circle class="dz-box-plot-mark-dot" cx="128.0" cy="168.0" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/><text class="dz-box-plot-mark-label" x="152.0" y="171.0" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">5</text><title>Web min: 5</title></g><text x="128.0" y="192" text-anchor="middle" font-size="10" fill="var(--colour-text)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">Web</text><line class="dz-box-plot-whisker" x1="192.0" y1="155.56" x2="192.0" y2="137.78" stroke="var(--colour-text-muted)" stroke-width="1"/><line class="dz-box-plot-whisker" x1="192.0" y1="88.0" x2="192.0" y2="8.0" stroke="var(--colour-text-muted)" stroke-width="1"/><line class="dz-box-plot-whisker-cap" x1="183.0" y1="155.56" x2="201.0" y2="155.56" stroke="var(--colour-text-muted)" stroke-width="1"/><line class="dz-box-plot-whisker-cap" x1="183.0" y1="8.0" x2="201.0" y2="8.0" stroke="var(--colour-text-muted)" stroke-width="1"/><rect class="dz-box-plot-box" x="174.0" y="88.0" width="36" height="49.78" fill="var(--colour-brand)" fill-opacity="0.18" stroke="var(--colour-brand)" stroke-width="1"><title>Jobs: Q1 22.0, median 35.0, Q3 50.0, n=64</title></rect><line class="dz-box-plot-median" x1="174.0" y1="114.67" x2="210.0" y2="114.67" stroke="var(--colour-brand)" stroke-width="1"/><g class="dz-box-plot-mark" data-dz-box-mark="max"><circle class="dz-box-plot-mark-hit" cx="192.0" cy="8.0" r="7" fill="transparent" stroke="none"/><circle class="dz-box-plot-mark-dot" cx="192.0" cy="8.0" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/><text class="dz-box-plot-mark-label" x="216.0" y="11.0" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">95</text><title>Jobs max: 95</title></g><g class="dz-box-plot-mark" data-dz-box-mark="q3"><circle class="dz-box-plot-mark-hit" cx="192.0" cy="88.0" r="7" fill="transparent" stroke="none"/><circle class="dz-box-plot-mark-dot" cx="192.0" cy="88.0" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/><text class="dz-box-plot-mark-label" x="216.0" y="91.0" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">50</text><title>Jobs q3: 50</title></g><g class="dz-box-plot-mark" data-dz-box-mark="median"><circle class="dz-box-plot-mark-hit" cx="192.0" cy="114.67" r="7" fill="transparent" stroke="none"/><circle class="dz-box-plot-mark-dot" cx="192.0" cy="114.67" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/><text class="dz-box-plot-mark-label" x="216.0" y="117.67" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">35</text><title>Jobs median: 35</title></g><g class="dz-box-plot-mark" data-dz-box-mark="q1"><circle class="dz-box-plot-mark-hit" cx="192.0" cy="137.78" r="7" fill="transparent" stroke="none"/><circle class="dz-box-plot-mark-dot" cx="192.0" cy="137.78" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/><text class="dz-box-plot-mark-label" x="216.0" y="140.78" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">22</text><title>Jobs q1: 22</title></g><g class="dz-box-plot-mark" data-dz-box-mark="min"><circle class="dz-box-plot-mark-hit" cx="192.0" cy="155.56" r="7" fill="transparent" stroke="none"/><circle class="dz-box-plot-mark-dot" cx="192.0" cy="155.56" r="2" fill="var(--colour-brand)" stroke="var(--colour-surface)" stroke-width="1"/><text class="dz-box-plot-mark-label" x="216.0" y="158.56" text-anchor="start" font-size="9" fill="var(--colour-text)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">12</text><title>Jobs min: 12</title></g><text x="192.0" y="192" text-anchor="middle" font-size="10" fill="var(--colour-text)" font-family="ui-monospace, \'SF Mono\', Menlo, monospace">Jobs</text></svg>',
    ),
    BoxPlot(groups=[], empty_message="No box-plot groups"),
]


def render(b: BoxPlot) -> str:
    """Model → box-plot region."""
    if not b.groups:
        return (
            f'<div class="dz-box-plot-region" data-dz-box-plot>'
            f'<p class="dz-empty-dense" role="status">'
            f"{html.escape(b.empty_message)}</p>"
            f"</div>"
        )
    n_total = sum(g.samples for g in b.groups)
    summary = f'<p class="dz-box-plot-summary">{len(b.groups)} groups · {n_total} samples</p>'
    return f'<div class="dz-box-plot-region" data-dz-box-plot>{b.svg_html}{summary}</div>'


__all__ = [
    "DOM_CONTRACT",
    "BoxPlotGroup",
    "BoxPlot",
    "EXEMPLARS",
    "render",
]
