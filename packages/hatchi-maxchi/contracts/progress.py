"""HYPERPART: progress-region — native progress bar + stage chips.

Dual-lock unit is the region root. Stage chips carry
``data-dz-stage-tone`` (complete / active / empty); the header uses a
native ``<progress data-dz-progress>`` for the overall percent.
"""

from __future__ import annotations

import html
from typing import Literal

from pydantic import BaseModel, Field

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="progress-region",
    root="[data-dz-progress-region]",
    nodes=(
        Node(
            "[data-dz-progress-region]",
            attrs={"data-dz-progress-region": Present()},
        ),
    ),
)

StageTone = Literal["complete", "active", "empty"]


class ProgressStage(BaseModel):
    """One workflow stage chip.

    Tone is derived at render time from ``complete`` + ``count`` when not
    pre-set by the host; the dual-lock DOM only requires the root.
    """

    name: str
    count: int = 0
    complete: bool = False


class Progress(BaseModel):
    """Progress region — bar + stage chips + optional summary.

    - ``stages`` → chip list
    - ``complete_pct`` → header ``<progress value>`` + percent readout
    - ``complete_count`` / ``total`` → ``N of M complete`` summary (when total > 0)
    """

    stages: list[ProgressStage] = Field(default_factory=list)
    complete_pct: float = 0.0
    complete_count: int = 0
    total: int = 0


def _stage_tone(stage: ProgressStage) -> StageTone:
    if stage.complete:
        return "complete"
    if stage.count > 0:
        return "active"
    return "empty"


def _pct_str(pct: float) -> str:
    """Match Jinja-ish whole-number rendering for round percentages."""
    return str(int(pct)) if pct == int(pct) else str(pct)


EXEMPLARS: list[Progress] = [
    Progress(
        stages=[
            ProgressStage(name="Draft", count=4, complete=True),
            ProgressStage(name="Review", count=2, complete=False),
            ProgressStage(name="Published", count=0, complete=False),
        ],
        complete_pct=33.0,
        complete_count=1,
        total=3,
    ),
    Progress(stages=[], complete_pct=0.0, complete_count=0, total=0),
]


def render(p: Progress) -> str:
    """Model → progress region."""
    pct_str = _pct_str(p.complete_pct)
    chips_html = "".join(
        f'<span class="dz-progress-chip" data-dz-stage-tone="{_stage_tone(s)}">'
        f"{html.escape(s.name)} ({s.count})"
        f"</span>"
        for s in p.stages
    )
    summary_html = (
        f'<p class="dz-progress-summary">{p.complete_count} of {p.total} complete</p>'
        if p.total > 0
        else ""
    )
    return (
        f'<div class="dz-progress-region" data-dz-progress-region>'
        f'<div class="dz-progress-header">'
        f'<progress data-dz-progress value="{pct_str}" max="100"></progress>'
        f"<span>{pct_str}%</span>"
        f"</div>"
        f'<div class="dz-progress-stages">{chips_html}</div>'
        f"{summary_html}"
        f"</div>"
    )


__all__ = [
    "DOM_CONTRACT",
    "StageTone",
    "ProgressStage",
    "Progress",
    "EXEMPLARS",
    "render",
]
