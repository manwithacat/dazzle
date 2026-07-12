"""HYPERPART: cohort-strip — lens toggle + horizontal member cells.

Dual-lock unit is the region root. Lens bar and cells are host-owned.
"""

from __future__ import annotations

import html

from pydantic import BaseModel, Field

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="cohort-strip",
    root="[data-dz-cohort-strip]",
    nodes=(
        Node(
            "[data-dz-cohort-strip]",
            attrs={"data-dz-cohort-strip": Present()},
        ),
    ),
)


class CohortStrip(BaseModel):
    """Cohort strip region shell.

    - ``region_name`` → data-dz-region-name
    - ``body_html`` → trusted lens bar + cells body
    """

    region_name: str = ""
    body_html: str = Field(
        default="",
        description="Trusted lenses + cells (or empty message) markup.",
    )


EXEMPLARS: list[CohortStrip] = [
    CohortStrip(
        region_name="class_roll",
        body_html=(
            '<div class="dz-cohort-strip-lenses" role="tablist" aria-label="Lens toggle">'
            '<button type="button" role="tab" class="dz-cohort-strip-lens is-active" '
            'aria-pressed="true" data-lens-id="grade">Grade</button></div>'
            '<div class="dz-cohort-strip-body" id="region-class_roll-body">'
            '<div class="dz-cohort-strip-cells">'
            '<div class="dz-cohort-strip-cell" data-member-id="m1">'
            '<div class="dz-cohort-strip-cell-name">Ada</div></div></div></div>'
        ),
    ),
    CohortStrip(
        region_name="empty",
        body_html='<p class="dz-cohort-strip-empty">No members in this view.</p>',
    ),
]


def render(c: CohortStrip) -> str:
    """Model → cohort-strip region root."""
    rname = html.escape(c.region_name, quote=True)
    return (
        f'<div class="dz-cohort-strip-region" data-dz-cohort-strip '
        f'data-dz-region-name="{rname}">{c.body_html}</div>'
    )


__all__ = [
    "DOM_CONTRACT",
    "CohortStrip",
    "EXEMPLARS",
    "render",
]
