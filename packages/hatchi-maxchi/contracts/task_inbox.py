"""HYPERPART: task-inbox — chips + urgency-flagged task list.

Dual-lock unit is the region root. Chip/item HTML is host-owned
(icons, drill URLs, urgency).
"""

from __future__ import annotations

import html

from pydantic import BaseModel, Field

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="task-inbox",
    root="[data-dz-task-inbox]",
    nodes=(
        Node(
            "[data-dz-task-inbox]",
            attrs={"data-dz-task-inbox": Present()},
        ),
    ),
)


class TaskInbox(BaseModel):
    """Task inbox region shell.

    - ``region_name`` → data-dz-region-name (host identity)
    - ``body_html`` → trusted chips + items / empty paragraph
    """

    region_name: str = ""
    body_html: str = Field(
        default="",
        description="Trusted chips + items (or empty-state paragraph).",
    )


EXEMPLARS: list[TaskInbox] = [
    TaskInbox(
        region_name="inbox",
        body_html=(
            '<div class="dz-task-inbox-chips">'
            '<div class="dz-task-inbox-chip" data-dz-chip-id="all">'
            '<span class="dz-task-inbox-chip-count">6</span>'
            '<span class="dz-task-inbox-chip-label">All</span></div></div>'
            '<ul class="dz-task-inbox-items">'
            '<li class="dz-task-inbox-item" data-dz-urgency="overdue" data-dz-item-id="t1">'
            '<div class="dz-task-inbox-item-title">Approve refund</div></li></ul>'
        ),
    ),
    TaskInbox(region_name="empty", body_html='<p class="dz-task-inbox-empty">All caught up.</p>'),
]


def render(t: TaskInbox) -> str:
    """Model → task-inbox region root."""
    rname = html.escape(t.region_name, quote=True)
    return (
        f'<div class="dz-task-inbox-region" data-dz-task-inbox '
        f'data-dz-region-name="{rname}">{t.body_html}</div>'
    )


__all__ = [
    "DOM_CONTRACT",
    "TaskInbox",
    "EXEMPLARS",
    "render",
]
