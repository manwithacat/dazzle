"""HYPERPART: grid-region — card-grid of cells (title + field lines).

Dual-lock unit is the region root. Cell HTML is host-owned.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="grid-region",
    root="[data-dz-grid-region]",
    nodes=(
        Node(
            "[data-dz-grid-region]",
            attrs={"data-dz-grid-region": Present()},
        ),
    ),
)


class GridRegion(BaseModel):
    """Grid region shell.

    - ``body_html`` → trusted empty-state or grid-list cells
    """

    body_html: str = Field(
        default="",
        description="Trusted empty-state or .dz-grid-list markup.",
    )


EXEMPLARS: list[GridRegion] = [
    GridRegion(
        body_html=(
            '<div class="dz-grid-list">'
            '<div class="dz-grid-cell ">'
            '<h4 class="dz-grid-cell-title">Alpha</h4>'
            '<p class="dz-grid-cell-field">'
            '<span class="dz-grid-cell-field-label">Owner:</span> Ada</p></div></div>'
        ),
    ),
    GridRegion(body_html='<p class="dz-empty-dense" role="status">No items found.</p>'),
]


def render(g: GridRegion) -> str:
    """Model → grid-region root."""
    return f'<div class="dz-grid-region" data-dz-grid-region>{g.body_html}</div>'


__all__ = [
    "DOM_CONTRACT",
    "GridRegion",
    "EXEMPLARS",
    "render",
]
