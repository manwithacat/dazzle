"""HYPERPART: radar — polar multi-axis profile chart.

Dual-lock unit is the region root. Spoke/polygon geometry is
server-computed SVG (``svg_html`` trusted); the summary line is derived
from axis count + peak value.
"""

from __future__ import annotations

import html

from pydantic import BaseModel, Field

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="radar",
    root="[data-dz-radar]",
    nodes=(
        Node(
            "[data-dz-radar]",
            attrs={"data-dz-radar": Present()},
        ),
    ),
)


class RadarAxis(BaseModel):
    """One named spoke on the radar."""

    label: str
    value: float = 0.0


class Radar(BaseModel):
    """Polar profile chart.

    - ``axes`` → spoke labels + values (summary is derived)
    - ``svg_html`` → trusted server-rendered SVG body
    - ``label`` → chart title used by host SVG helpers (not always in DOM)
    - ``peak_display`` → optional host-formatted peak for the summary line
      (when empty, a plain numeric peak is used)
    """

    label: str = ""
    axes: list[RadarAxis] = Field(default_factory=list)
    svg_html: str = Field(
        default="",
        description="Trusted inline SVG markup for the chart body.",
    )
    peak_display: str = ""
    empty_message: str = "No data available."


EXEMPLARS: list[Radar] = [
    Radar(
        label="Coverage",
        axes=[
            RadarAxis(label="Auth", value=80),
            RadarAxis(label="API", value=65),
            RadarAxis(label="UI", value=90),
        ],
        svg_html=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" '
            'role="img" aria-label="Radar — 3 spokes">'
            '<polygon points="60,20 100,90 20,90" fill="var(--colour-brand)" '
            'fill-opacity="0.25" stroke="var(--colour-brand)"/>'
            "</svg>"
        ),
        peak_display="90",
    ),
    Radar(axes=[], empty_message="No axes"),
]


def render(r: Radar) -> str:
    """Model → radar region."""
    if not r.axes:
        return (
            f'<div class="dz-radar-region" data-dz-radar>'
            f'<p class="dz-empty-dense" role="status">'
            f"{html.escape(r.empty_message)}</p>"
            f"</div>"
        )
    peak = r.peak_display
    if not peak:
        max_val = max((a.value for a in r.axes), default=0) or 0
        peak = str(int(max_val)) if max_val == int(max_val) else str(max_val)
    summary = (
        f'<p class="dz-chart-summary">'
        f"{len(r.axes)} spokes · 1 series · peak {html.escape(peak)}"
        f"</p>"
    )
    return f'<div class="dz-radar-region" data-dz-radar>{r.svg_html}{summary}</div>'


__all__ = [
    "DOM_CONTRACT",
    "RadarAxis",
    "Radar",
    "EXEMPLARS",
    "render",
]
