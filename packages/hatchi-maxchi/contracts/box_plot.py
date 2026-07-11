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
            BoxPlotGroup(label="API", min=10, q1=20, median=30, q3=45, max=80, samples=40),
            BoxPlotGroup(label="Web", min=5, q1=15, median=25, q3=40, max=70, samples=30),
        ],
        svg_html=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 48" '
            'role="img" aria-label="Box plot — 2 groups">'
            '<line x1="40" y1="8" x2="40" y2="40" stroke="var(--colour-text-muted)"/>'
            '<rect x="28" y="16" width="24" height="16" fill="var(--colour-brand)" '
            'fill-opacity="0.25" stroke="var(--colour-brand)"/>'
            '<line x1="28" y1="24" x2="52" y2="24" stroke="var(--colour-brand)" '
            'stroke-width="2"/>'
            '<line x1="120" y1="6" x2="120" y2="42" stroke="var(--colour-text-muted)"/>'
            '<rect x="108" y="14" width="24" height="20" fill="var(--colour-brand)" '
            'fill-opacity="0.25" stroke="var(--colour-brand)"/>'
            '<line x1="108" y1="22" x2="132" y2="22" stroke="var(--colour-brand)" '
            'stroke-width="2"/>'
            "</svg>"
        ),
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
