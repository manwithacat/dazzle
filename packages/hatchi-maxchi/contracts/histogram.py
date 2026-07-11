"""HYPERPART: histogram — continuous-axis distribution chart.

Dual-lock unit is the region root. Bin geometry is server-computed SVG
(``svg_html`` trusted); the summary line is derived from bin counts.
"""

from __future__ import annotations

import html

from pydantic import BaseModel, Field

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="histogram",
    root="[data-dz-histogram]",
    nodes=(
        Node(
            "[data-dz-histogram]",
            attrs={"data-dz-histogram": Present()},
        ),
    ),
)


class HistogramBin(BaseModel):
    """One continuous bin — label + count + range."""

    label: str
    count: int = 0
    low: float = 0.0
    high: float = 0.0


class Histogram(BaseModel):
    """Distribution histogram.

    - ``bins`` → series data (summary is derived)
    - ``svg_html`` → trusted server-rendered SVG body (empty → no glyph)
    - ``label`` → chart title used by host SVG helpers (not always in DOM)
    """

    label: str = ""
    bins: list[HistogramBin] = Field(default_factory=list)
    svg_html: str = Field(
        default="",
        description="Trusted inline SVG markup for the chart body.",
    )
    empty_message: str = "No data available."


EXEMPLARS: list[Histogram] = [
    Histogram(
        label="Latency",
        bins=[
            HistogramBin(label="0-10", count=12, low=0, high=10),
            HistogramBin(label="10-20", count=30, low=10, high=20),
            HistogramBin(label="20-30", count=42, low=20, high=30),
        ],
        svg_html=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 48" '
            'role="img" aria-label="Histogram — 3 buckets, 84 samples">'
            '<rect x="4" y="30" width="50" height="18" fill="var(--colour-brand)" '
            'fill-opacity="0.7"/>'
            '<rect x="62" y="14" width="50" height="34" fill="var(--colour-brand)" '
            'fill-opacity="0.7"/>'
            '<rect x="120" y="6" width="50" height="42" fill="var(--colour-brand)" '
            'fill-opacity="0.7"/>'
            "</svg>"
        ),
    ),
    Histogram(bins=[], empty_message="No samples"),
]


def render(h: Histogram) -> str:
    """Model → histogram region."""
    if not h.bins:
        return (
            f'<div class="dz-histogram-region" data-dz-histogram>'
            f'<p class="dz-empty-dense" role="status">'
            f"{html.escape(h.empty_message)}</p>"
            f"</div>"
        )
    total = sum(b.count for b in h.bins)
    max_count = max(b.count for b in h.bins) or 1
    summary = (
        f'<p class="dz-histogram-summary">'
        f"{len(h.bins)} bins · {total} samples · peak {max_count}"
        f"</p>"
    )
    return f'<div class="dz-histogram-region" data-dz-histogram>{h.svg_html}{summary}</div>'


__all__ = [
    "DOM_CONTRACT",
    "HistogramBin",
    "Histogram",
    "EXEMPLARS",
    "render",
]
