"""HYPERPART: day-timeline — vertical chronological slot spine.

Dual-lock unit is the region root. Slot cards are host-owned HTML.
"""

from __future__ import annotations

import html

from pydantic import BaseModel, Field

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="day-timeline",
    root="[data-dz-day-timeline]",
    nodes=(
        Node(
            "[data-dz-day-timeline]",
            attrs={"data-dz-day-timeline": Present()},
        ),
    ),
)


class DayTimeline(BaseModel):
    """Day timeline region shell.

    - ``region_name`` → data-dz-region-name
    - ``body_html`` → trusted slots list or empty paragraph
    """

    region_name: str = ""
    body_html: str = Field(
        default="",
        description="Trusted slots (or empty-state) markup.",
    )


EXEMPLARS: list[DayTimeline] = [
    DayTimeline(
        region_name="today",
        body_html=(
            '<ol class="dz-day-timeline-slots">'
            '<div class="dz-day-timeline-slot is-active" data-dz-position="active" '
            'data-slot-id="p3">'
            '<div class="dz-day-timeline-slot-label">Period 3</div></div></ol>'
        ),
    ),
    DayTimeline(
        region_name="empty",
        body_html='<p class="dz-day-timeline-empty">No scheduled slots today.</p>',
    ),
]


def render(d: DayTimeline) -> str:
    """Model → day-timeline region root."""
    rname = html.escape(d.region_name, quote=True)
    return (
        f'<div class="dz-day-timeline-region" data-dz-day-timeline '
        f'data-dz-region-name="{rname}">{d.body_html}</div>'
    )


__all__ = [
    "DOM_CONTRACT",
    "DayTimeline",
    "EXEMPLARS",
    "render",
]
