"""HYPERPART: entity-card — composite single-entity 360° view.

Dual-lock unit is the region root. Sections are host-owned HTML.
"""

from __future__ import annotations

import html

from pydantic import BaseModel, Field

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="entity-card",
    root="[data-dz-entity-card]",
    nodes=(
        Node(
            "[data-dz-entity-card]",
            attrs={"data-dz-entity-card": Present()},
        ),
    ),
)


class EntityCard(BaseModel):
    """Entity card region shell.

    - ``region_name`` → data-dz-region-name
    - ``body_html`` → trusted heading + sections (or empty)
    """

    region_name: str = ""
    body_html: str = Field(
        default="",
        description="Trusted heading + sections markup.",
    )


EXEMPLARS: list[EntityCard] = [
    EntityCard(
        region_name="customer_360",
        body_html=(
            '<h3 class="dz-entity-card-heading">Acme Corp</h3>'
            '<div class="dz-entity-card-sections">'
            '<section class="dz-entity-card-section" data-section-id="halo" '
            'data-dz-mode="halo" data-dz-column="main">'
            '<header class="dz-entity-card-section-label">Profile</header>'
            '<div class="dz-entity-card-section-body">…</div></section></div>'
        ),
    ),
    EntityCard(
        region_name="empty",
        body_html='<p class="dz-entity-card-empty">No record context available.</p>',
    ),
]


def render(e: EntityCard) -> str:
    """Model → entity-card region root."""
    rname = html.escape(e.region_name, quote=True)
    return (
        f'<div class="dz-entity-card-region" data-dz-entity-card '
        f'data-dz-region-name="{rname}">{e.body_html}</div>'
    )


__all__ = [
    "DOM_CONTRACT",
    "EntityCard",
    "EXEMPLARS",
    "render",
]
