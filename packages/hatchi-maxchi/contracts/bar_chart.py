"""HYPERPART: bar-chart — categorical label / track / value rows.

The dual-lock unit is the whole chart region. ``label_html`` on each row
is trusted SSR (Dazzle may inject status badges); empty falls back to
escaped ``label`` text.
"""

from __future__ import annotations

import html

from pydantic import BaseModel, Field, field_validator

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="bar-chart",
    root="[data-dz-bar-chart]",
    nodes=(
        Node(
            "[data-dz-bar-chart]",
            attrs={"data-dz-bar-chart": Present()},
        ),
    ),
)


class BarChartRow(BaseModel):
    """One bar row.

    - ``label`` → plain text (used when ``label_html`` empty)
    - ``count`` → right-hand value
    - ``width_pct`` → fill width 0–100
    - ``label_html`` → trusted label cell (badge etc.)
    """

    label: str
    count: int = 0
    width_pct: int = 0
    label_html: str = Field(
        default="",
        description="Trusted HTML for the label cell; empty → escape label.",
    )

    @field_validator("label")
    @classmethod
    def _label_nonempty(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("BarChartRow requires a non-empty label")
        return v


class BarChart(BaseModel):
    """Bar chart of categorical buckets."""

    rows: list[BarChartRow] = Field(default_factory=list)


EXEMPLARS: list[BarChart] = [
    BarChart(
        rows=[
            BarChartRow(label="API", count=126, width_pct=84),
            BarChartRow(label="Dashboard", count=84, width_pct=56),
            BarChartRow(label="Mobile", count=42, width_pct=28),
        ]
    ),
    BarChart(rows=[]),
]


def render(chart: BarChart) -> str:
    """Model → bar chart region."""
    if not chart.rows:
        return '<div class="dz-bar-chart-region" data-dz-bar-chart></div>'

    rows_html = "".join(
        f'<div class="dz-bar-chart-row">'
        f'<span class="dz-bar-chart-label">'
        f"{(row.label_html if row.label_html.strip() else html.escape(row.label))}"
        f"</span>"
        f'<div class="dz-bar-chart-track">'
        f'<div class="dz-bar-chart-fill" '
        f'style="width: {max(0, min(100, row.width_pct))}%"></div>'
        f"</div>"
        f'<span class="dz-bar-chart-value">{row.count}</span>'
        f"</div>"
        for row in chart.rows
    )
    return (
        f'<div class="dz-bar-chart-region" data-dz-bar-chart>'
        f'<div class="dz-bar-chart-bars">{rows_html}</div>'
        f"</div>"
    )


__all__ = [
    "DOM_CONTRACT",
    "BarChartRow",
    "BarChart",
    "EXEMPLARS",
    "render",
]
