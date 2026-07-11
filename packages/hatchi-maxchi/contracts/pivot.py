"""HYPERPART: pivot — cross-tab matrix of dimension + measure columns.

Dual-lock unit is the region root. Cell HTML is trusted SSR (badges, FK
labels, measure values) so host-specific rendering stays on the Dazzle
side while the table chrome is dual-locked.
"""

from __future__ import annotations

import html

from pydantic import BaseModel, Field

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="pivot",
    root="[data-dz-pivot]",
    nodes=(
        Node(
            "[data-dz-pivot]",
            attrs={"data-dz-pivot": Present()},
        ),
    ),
)


class PivotTable(BaseModel):
    """Cross-tab region.

    - ``dim_headers`` → leading dimension column titles
    - ``measure_headers`` → trailing measure column titles (``.is-measure``)
    - ``rows`` → list of rows; each row is a list of trusted cell HTML
      (one cell per dim + measure, in header order)
    """

    dim_headers: list[str] = Field(default_factory=list)
    measure_headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    empty_message: str = "No data to pivot."


EXEMPLARS: list[PivotTable] = [
    PivotTable(
        dim_headers=["System", "Severity"],
        measure_headers=["Count"],
        rows=[
            ["API", '<span class="dz-badge">Critical</span>', "3"],
            ["Dashboard", '<span class="dz-pivot-null">—</span>', "9"],
        ],
    ),
    PivotTable(dim_headers=[], measure_headers=[], rows=[], empty_message="Empty"),
]


def render(p: PivotTable) -> str:
    """Model → pivot table region."""
    if not p.rows:
        return (
            f'<div class="dz-pivot-region" data-dz-pivot>'
            f'<p class="dz-empty-dense" role="status">'
            f"{html.escape(p.empty_message)}</p>"
            f"</div>"
        )

    head_dim = "".join(f"<th>{html.escape(h)}</th>" for h in p.dim_headers)
    head_measure = "".join(
        f'<th class="is-measure">{html.escape(h)}</th>' for h in p.measure_headers
    )
    thead = f"<thead><tr>{head_dim}{head_measure}</tr></thead>"
    n_dim = len(p.dim_headers)
    body_parts: list[str] = []
    for row in p.rows:
        cells = ""
        for i, c in enumerate(row):
            if i >= n_dim:
                cells += f'<td class="is-measure">{c}</td>'
            else:
                cells += f"<td>{c}</td>"
        body_parts.append(f"<tr>{cells}</tr>")
    tbody = f"<tbody>{''.join(body_parts)}</tbody>"
    n = len(p.rows)
    suffix = "" if n == 1 else "s"
    summary = f'<p class="dz-pivot-summary">{n} row{suffix}</p>'
    return (
        f'<div class="dz-pivot-region" data-dz-pivot>'
        f'<div class="dz-pivot-scroll">'
        f'<table class="dz-pivot-grid">{thead}{tbody}</table>'
        f"</div>"
        f"{summary}"
        f"</div>"
    )


__all__ = [
    "DOM_CONTRACT",
    "PivotTable",
    "EXEMPLARS",
    "render",
]
