"""HYPERPART: pagination — list/table page footer (summary + page buttons).

Dual-lock unit is the region root. Page buttons are host-trusted HTML
(htmx hrefs, current markers). Grid selection reads ``data-dz-grid-total``
and ``data-dz-grid-pagination`` on the same root.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="pagination",
    root="[data-dz-pagination]",
    nodes=(
        Node(
            "[data-dz-pagination]",
            attrs={
                "data-dz-pagination": Present(),
                "data-dz-grid-pagination": Present(),
                "data-dz-grid-total": Present(),
            },
        ),
    ),
)


class Pagination(BaseModel):
    """Pagination footer.

    - ``total`` → matched row count (also ``data-dz-grid-total``)
    - ``pages_html`` → trusted page-button row body (ellipsis + buttons)
    - when ``total`` is 0 or host omits pages, render may return empty string
      (Dazzle returns \"\" when total <= page_size)
    """

    total: int = 0
    pages_html: str = Field(
        default="",
        description="Trusted markup for .dz-pagination-pages children.",
    )
    rows_label: str = "rows"  # "row" / "rows"


EXEMPLARS: list[Pagination] = [
    Pagination(
        total=42,
        rows_label="rows",
        pages_html=(
            '<button class="dz-pagination-page is-current" aria-current="page">1</button>'
            '<button class="dz-pagination-page">2</button>'
            '<span class="dz-pagination-ellipsis" aria-hidden="true">…</span>'
            '<button class="dz-pagination-page">9</button>'
        ),
    ),
    Pagination(total=0, pages_html=""),
]


def render(p: Pagination) -> str:
    """Model → pagination footer. Empty total + empty pages → \"\"."""
    if p.total <= 0 and not p.pages_html:
        return ""
    if not p.pages_html:
        return ""
    label = p.rows_label or ("row" if p.total == 1 else "rows")
    return (
        f'<div class="dz-pagination" data-dz-pagination data-dz-grid-pagination '
        f'data-dz-grid-total="{p.total}">'
        f'<span class="dz-pagination-summary">'
        f'<span class="dz-bulk-summary-selected">'
        f"<span data-dz-bulk-count-target>0</span> of {p.total} selected"
        f"</span>"
        f'<span class="dz-bulk-summary-rows">{p.total} {label}</span>'
        f"</span>"
        f'<div class="dz-pagination-pages">{p.pages_html}</div>'
        f"</div>"
    )


__all__ = [
    "DOM_CONTRACT",
    "Pagination",
    "EXEMPLARS",
    "render",
]
