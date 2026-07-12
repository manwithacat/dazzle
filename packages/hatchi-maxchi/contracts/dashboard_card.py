"""HYPERPART: dashboard-card — workspace dashboard grid card chrome.

Dual-lock unit is the outer card wrapper. Header, notice, HTMX body
skeleton, and resize handle are host-owned trusted HTML.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="dashboard-card",
    root="[data-dz-dashboard-card]",
    nodes=(
        Node(
            "[data-dz-dashboard-card]",
            attrs={"data-dz-dashboard-card": Present()},
        ),
    ),
)


class DashboardCard(BaseModel):
    """Dashboard card wrapper shell.

    - ``attrs`` → trusted attribute string for the outer ``div``
      (id, data-card-*, class, style, tabindex) — without dual-lock attr
    - ``body_html`` → trusted article + resize handle markup
    """

    attrs: str = Field(
        default="",
        description="Trusted outer-div attributes (excluding data-dz-dashboard-card).",
    )
    body_html: str = Field(
        default="",
        description="Trusted article + resize-handle markup.",
    )


EXEMPLARS: list[DashboardCard] = [
    DashboardCard(
        attrs=(
            'id="card-tasks-card-0" data-card-id="card-0" data-card-region="tasks" '
            'data-card-col-span="1" data-card-row-order="0" '
            'class="dz-card-wrapper is-animating" '
            'style="grid-column: span 1 / span 1;" tabindex="0"'
        ),
        body_html=(
            '<article class="dz-card" role="article" aria-labelledby="card-title-card-0">'
            '<div class="dz-card-header"><div class="dz-card-titles">'
            '<h3 id="card-title-card-0" class="dz-card-title">Tasks</h3>'
            "</div></div>"
            '<div class="dz-card-body" id="region-tasks-card-0" data-display="list">'
            '<div class="dz-card-skeleton">'
            '<div class="dz-card-skeleton-line w-3-4"></div></div></div>'
            "</article>"
            '<div class="dz-card-resize" aria-hidden="true"></div>'
        ),
    ),
    DashboardCard(attrs='class="dz-card-wrapper"', body_html=""),
]


def render(d: DashboardCard) -> str:
    """Model → dashboard card wrapper."""
    attrs = d.attrs.strip()
    prefix = f"{attrs} " if attrs else ""
    return f"<div {prefix}data-dz-dashboard-card>{d.body_html}</div>"


__all__ = [
    "DOM_CONTRACT",
    "DashboardCard",
    "EXEMPLARS",
    "render",
]
