"""HYPERPART: heatmap — threshold-toned matrix.

Dual-lock unit is the region root. Cell tones ride
``data-dz-heatmap-tone`` (bad/warn/good); the numeric value is always
in the cell so tone is reinforcement, not the only signal.
"""

from __future__ import annotations

import html

from pydantic import BaseModel, Field

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="heatmap",
    root="[data-dz-heatmap]",
    nodes=(
        Node(
            "[data-dz-heatmap]",
            attrs={"data-dz-heatmap": Present()},
        ),
    ),
)


class HeatmapRow(BaseModel):
    """One matrix row — label + ordered cell values."""

    label: str
    cells: list[float] = Field(default_factory=list)


class Heatmap(BaseModel):
    """Threshold-tinted matrix.

    ``thresholds``: 0 / 1 / 2 ascending cut-points → tone bands.
    """

    columns: list[str] = Field(default_factory=list)
    rows: list[HeatmapRow] = Field(default_factory=list)
    thresholds: list[float] = Field(default_factory=list)
    total: int = 0
    empty_message: str = "No data available."


EXEMPLARS: list[Heatmap] = [
    Heatmap(
        columns=["Mon", "Tue", "Wed"],
        rows=[
            HeatmapRow(label="API", cells=[99.9, 99.7, 97.2]),
            HeatmapRow(label="Webhooks", cells=[96.1, 89.4, 99.2]),
        ],
        thresholds=[90.0, 98.0],
        total=2,
    ),
    Heatmap(columns=[], rows=[], empty_message="No matrix"),
]


def _tone_attr(value: float, thresholds: list[float]) -> str:
    n = len(thresholds)
    if n >= 2:
        if value < thresholds[0]:
            return ' data-dz-heatmap-tone="bad"'
        if value < thresholds[1]:
            return ' data-dz-heatmap-tone="warn"'
        return ' data-dz-heatmap-tone="good"'
    if n == 1:
        if value < thresholds[0]:
            return ' data-dz-heatmap-tone="bad"'
        return ' data-dz-heatmap-tone="good"'
    return ""


def render(h: Heatmap) -> str:
    """Model → heatmap region."""
    if not h.rows:
        return (
            f'<div class="dz-heatmap-region" data-dz-heatmap>'
            f'<p class="dz-empty-dense" role="status">'
            f"{html.escape(h.empty_message)}</p>"
            f"</div>"
        )

    head_cols = "".join(f"<th>{html.escape(c)}</th>" for c in h.columns)
    thead = f"<thead><tr><th></th>{head_cols}</tr></thead>"
    body_rows: list[str] = []
    for row in h.rows:
        cells_html = ""
        for cell in row.cells:
            cells_html += (
                f'<td class="dz-heatmap-cell"{_tone_attr(cell, h.thresholds)}> {cell:.1f} </td>'
            )
        body_rows.append(
            f'<tr><td class="dz-heatmap-row-label">{html.escape(row.label)}</td>{cells_html}</tr>'
        )
    tbody = f"<tbody>{''.join(body_rows)}</tbody>"
    overflow_html = ""
    if h.total > len(h.rows):
        overflow_html = f'<p class="dz-heatmap-overflow">Showing {len(h.rows)} of {h.total}</p>'
    return (
        f'<div class="dz-heatmap-region" data-dz-heatmap>'
        f'<div class="dz-heatmap-scroll">'
        f'<table class="dz-heatmap-grid">{thead}{tbody}</table>'
        f"</div>"
        f"{overflow_html}"
        f"</div>"
    )


__all__ = ["DOM_CONTRACT", "HeatmapRow", "Heatmap", "EXEMPLARS", "render"]
