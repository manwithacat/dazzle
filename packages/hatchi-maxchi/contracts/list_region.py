"""HYPERPART: list-region — in-card table (actions + scroll table + overflow).

Dual-lock unit is the region root. Table rows, CSV wiring, empty state,
and overflow copy are host-owned trusted HTML (or Dazzle FragmentRenderer
cells); the chrome root is schema+DOM dual-locked.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="list-region",
    root="[data-dz-list-region]",
    nodes=(
        Node(
            "[data-dz-list-region]",
            attrs={"data-dz-list-region": Present()},
        ),
    ),
)


class ListRegion(BaseModel):
    """List region shell.

    - ``body_html`` → trusted markup for actions row + empty/table/overflow
      (host owns row cells, CSV attrs, drill URLs)
    """

    body_html: str = Field(
        default="",
        description="Trusted inner markup (actions + table or empty + overflow).",
    )


EXEMPLARS: list[ListRegion] = [
    ListRegion(
        body_html=(
            '<div class="dz-list-actions">'
            '<div class="dz-list-action-group">'
            '<button type="button" class="dz-list-csv-button" '
            'title="Export CSV" aria-label="Export CSV">CSV</button>'
            "</div></div>"
            '<div class="dz-list-scroll">'
            '<table class="dz-list-table">'
            "<thead><tr><th>Name</th><th>Owner</th></tr></thead>"
            "<tbody>"
            '<tr class="dz-list-row "><td>Quarterly audit</td><td>M. Reyes</td></tr>'
            "</tbody></table></div>"
            '<p class="dz-list-overflow">Showing 1 of 14</p>'
        ),
    ),
    ListRegion(body_html=""),
]


def render(lr: ListRegion) -> str:
    """Model → list-region root wrapper."""
    return f'<div class="dz-list-region" data-dz-list-region>{lr.body_html}</div>'


__all__ = [
    "DOM_CONTRACT",
    "ListRegion",
    "EXEMPLARS",
    "render",
]
