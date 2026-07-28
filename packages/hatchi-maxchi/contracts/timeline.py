"""HYPERPART: timeline — dated event row unit.

One item is the dual-lock unit. Region chrome / overflow are layout furniture;
validate items with ``require_root`` on the item root.

``fields_html`` is trusted SSR for secondary field lines. ``bullet_html`` is
trusted SVG (or empty → default neutral bullet).
"""

from __future__ import annotations

import html

from pydantic import BaseModel, Field, field_validator

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="timeline",
    root="[data-dz-timeline-item]",
    nodes=(
        Node(
            "[data-dz-timeline-item]",
            attrs={"data-dz-timeline-item": Present()},
        ),
    ),
)

_DEFAULT_BULLET = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" '
    'fill="currentColor" '
    'class="dz-timeline-bullet dz-attn-bullet dz-attn-tone-default" '
    'aria-hidden="true">'
    '<circle cx="10" cy="10" r="6"/>'
    "</svg>"
)


class TimelineEvent(BaseModel):
    """One timeline list item.

    - ``title`` → primary line (required)
    - ``date_label`` → already-formatted date/time column
    - ``fields_html`` → trusted secondary field lines
    - ``bullet_html`` → trusted bullet SVG; empty uses default neutral tone
    - ``drill_url`` → when set, title becomes an ``<a href>`` hub drill
      (same class as queue row / kanban #1303; host gates EDIT paths)
    """

    title: str
    date_label: str = ""
    fields_html: str = Field(
        default="",
        description="Trusted HTML for secondary field lines.",
    )
    bullet_html: str = Field(
        default="",
        description="Trusted SVG for the bullet; empty → default tone.",
    )
    drill_url: str = Field(
        default="",
        description="Optional hub URL (/app/<slug>/{id} or …/edit); title becomes a link.",
    )

    @field_validator("title")
    @classmethod
    def _title_nonempty(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("TimelineEvent requires a non-empty title")
        return v


EXEMPLARS: list[TimelineEvent] = [
    TimelineEvent(
        title="Payment failed — retry scheduled",
        date_label="Today",
        fields_html='<p class="dz-timeline-field">Card declined (insufficient funds)</p>',
        bullet_html=(
            '<svg class="dz-timeline-bullet dz-attn-bullet dz-attn-tone-critical" '
            'fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">'
            '<circle cx="10" cy="10" r="6"/></svg>'
        ),
    ),
    TimelineEvent(
        title="Invoice sent",
        date_label="Mon",
    ),
]


def render(evt: TimelineEvent) -> str:
    """Model → one ``<li>`` timeline item."""
    title = html.escape(evt.title)
    if evt.drill_url:
        href = html.escape(evt.drill_url, quote=True)
        # Keep p + class for dual-lock/CSS; wrap title text in hub drill
        # (queue/kanban pattern; empty drill_url stays byte-stable plain p).
        title_html = (
            f'<p class="dz-timeline-title"><a href="{href}" data-dz-timeline-drill>{title}</a></p>'
        )
    else:
        title_html = f'<p class="dz-timeline-title">{title}</p>'
    date = html.escape(evt.date_label)
    bullet = evt.bullet_html.strip() or _DEFAULT_BULLET
    return (
        f'<li class="dz-timeline-item" data-dz-timeline-item>'
        f'<span class="dz-timeline-bullet-wrap">{bullet}</span>'
        f'<div class="dz-timeline-row">'
        f'<div class="dz-timeline-date">{date}</div>'
        f'<div class="dz-timeline-content">'
        f"{title_html}"
        f"{evt.fields_html}"
        f"</div>"
        f"</div>"
        f"</li>"
    )


__all__ = [
    "DOM_CONTRACT",
    "TimelineEvent",
    "EXEMPLARS",
    "render",
]
