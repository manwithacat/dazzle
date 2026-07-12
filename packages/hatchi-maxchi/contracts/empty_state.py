"""HYPERPART: empty-state — icon + title + description + action slot.

Dual-lock unit is the region root. Icon markup and action HTML are
host-owned; the chrome root is schema+DOM dual-locked.
"""

from __future__ import annotations

import html

from pydantic import BaseModel, Field

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="empty-state",
    root="[data-dz-empty-state]",
    nodes=(
        Node(
            "[data-dz-empty-state]",
            attrs={"data-dz-empty-state": Present()},
        ),
    ),
)


class EmptyState(BaseModel):
    """Empty-state placeholder.

    - ``title`` / ``description`` → heading + body copy
    - ``icon_html`` → trusted icon markup (empty = no icon)
    - ``action_html`` → trusted action slot (button/link)
    """

    title: str = ""
    description: str = ""
    icon_html: str = Field(
        default="",
        description="Trusted icon markup for .dz-empty-state__icon slot.",
    )
    action_html: str = Field(
        default="",
        description="Trusted action markup for .dz-empty-state__action.",
    )


EXEMPLARS: list[EmptyState] = [
    EmptyState(
        title="No invoices yet",
        description="Create your first invoice to get started.",
        icon_html='<span class="dz-empty-state__icon" aria-hidden="true">∅</span>',
        action_html='<a class="dz-button" data-dz-variant="primary" href="#">New Invoice</a>',
    ),
    EmptyState(title="Empty", description="Nothing here."),
]


def render(e: EmptyState) -> str:
    """Model → empty-state region."""
    title = html.escape(e.title)
    desc = html.escape(e.description)
    return (
        f'<div class="dz-empty-state" data-dz-empty-state>'
        f"{e.icon_html}"
        f'<h3 class="dz-empty-state__title">{title}</h3>'
        f'<p class="dz-empty-state__description">{desc}</p>'
        f'<div class="dz-empty-state__action">{e.action_html}</div>'
        f"</div>"
    )


__all__ = [
    "DOM_CONTRACT",
    "EmptyState",
    "EXEMPLARS",
    "render",
]
