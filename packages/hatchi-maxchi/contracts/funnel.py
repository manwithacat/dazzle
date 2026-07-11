"""HYPERPART: funnel — stage-by-stage conversion chart.

The dual-lock unit is the whole funnel region. Stage widths are
server-computed percentages (inline style is intentional contract).
``data-dz-funnel-step`` tones stages in sequence (capped at 7).
"""

from __future__ import annotations

import html

from pydantic import BaseModel, Field, field_validator

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="funnel",
    root="[data-dz-funnel]",
    nodes=(
        Node(
            "[data-dz-funnel]",
            attrs={"data-dz-funnel": Present()},
        ),
    ),
)


class FunnelStage(BaseModel):
    """One funnel stage — label + absolute count."""

    label: str
    count: int = 0

    @field_validator("label")
    @classmethod
    def _label_nonempty(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("FunnelStage requires a non-empty label")
        return v


class Funnel(BaseModel):
    """Conversion funnel.

    Widths are relative to the first stage's count (min 20%).
    ``total`` is the summary line denominator (often first-stage count).
    """

    stages: list[FunnelStage] = Field(default_factory=list)
    total: int = 0
    empty_message: str = "No data available."


EXEMPLARS: list[Funnel] = [
    Funnel(
        stages=[
            FunnelStage(label="Visited", count=1204),
            FunnelStage(label="Signed up", count=746),
            FunnelStage(label="Subscribed", count=338),
        ],
        total=1204,
    ),
    Funnel(stages=[], empty_message="No funnel data"),
]


def render(f: Funnel) -> str:
    """Model → funnel chart region."""
    if not f.stages:
        return (
            f'<div class="dz-funnel-chart-region" data-dz-funnel>'
            f'<p class="dz-empty-dense" role="status">'
            f"{html.escape(f.empty_message)}</p>"
            f"</div>"
        )

    base = f.stages[0].count if f.stages[0].count > 0 else 1
    items: list[str] = []
    for i, stage in enumerate(f.stages):
        pct = int(stage.count / base * 100)
        width = pct if pct >= 20 else 20
        step = i if i < 8 else 7
        items.append(
            f'<div class="dz-funnel-stage-row">'
            f'<div class="dz-funnel-stage" '
            f'data-dz-funnel-step="{step}" '
            f'style="width: {width}%;">'
            f'<span class="dz-funnel-stage-label">{html.escape(stage.label)}</span> '
            f'<span class="dz-funnel-stage-count">({stage.count})</span>'
            f"</div>"
            f"</div>"
        )

    total = f.total if f.total else f.stages[0].count
    return (
        f'<div class="dz-funnel-chart-region" data-dz-funnel>'
        f'<div class="dz-funnel-stages">{"".join(items)}</div>'
        f'<p class="dz-funnel-summary">{total} total</p>'
        f"</div>"
    )


__all__ = [
    "DOM_CONTRACT",
    "FunnelStage",
    "Funnel",
    "EXEMPLARS",
    "render",
]
