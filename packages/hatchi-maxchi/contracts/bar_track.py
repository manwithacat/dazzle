"""HYPERPART: bar-track — value-against-capacity progress rows.

Dual-lock unit is the region root. Each track is a real
``role=progressbar`` with numeric aria values.
"""

from __future__ import annotations

import html

from pydantic import BaseModel, Field, field_validator

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="bar-track",
    root="[data-dz-bar-track]",
    nodes=(
        Node(
            "[data-dz-bar-track]",
            attrs={"data-dz-bar-track": Present()},
        ),
    ),
)


class BarTrackRow(BaseModel):
    """One capacity row.

    - ``label`` → row label
    - ``value`` → raw numeric (aria-valuenow)
    - ``formatted`` → display string (may be percent-formatted by host)
    - ``fill_pct`` → 0–100 track fill
    """

    label: str
    value: float = 0.0
    formatted: str = ""
    fill_pct: float = 0.0

    @field_validator("fill_pct")
    @classmethod
    def _clamp_fill(cls, v: float) -> float:
        if not (0.0 <= v <= 100.0):
            raise ValueError(f"fill_pct={v} outside [0, 100]")
        return v


class BarTrack(BaseModel):
    """Resource-usage track list."""

    rows: list[BarTrackRow] = Field(default_factory=list)
    max_value: float = 100.0


EXEMPLARS: list[BarTrack] = [
    BarTrack(
        max_value=100.0,
        rows=[
            BarTrackRow(label="Storage", value=62.0, formatted="62%", fill_pct=62.0),
            BarTrackRow(label="Compute", value=38.0, formatted="38%", fill_pct=38.0),
        ],
    ),
]


def _num(v: float) -> str:
    return str(int(v)) if v == int(v) else str(v)


def render(b: BarTrack) -> str:
    """Model → bar-track region (references block is host-local)."""
    if not b.rows:
        return '<div class="dz-bar-track-region" data-dz-bar-track></div>'

    max_str = _num(b.max_value)
    rows_html = "".join(
        f'<div class="dz-bar-track-row">'
        f'<span class="dz-bar-track-label" title="{html.escape(row.label, quote=True)}">'
        f"{html.escape(row.label)}</span>"
        f'<div class="dz-bar-track" role="progressbar" '
        f'aria-valuemin="0" '
        f'aria-valuemax="{max_str}" '
        f'aria-valuenow="{_num(row.value)}" '
        f'aria-label="{html.escape(row.label, quote=True)}: '
        f'{html.escape(row.formatted or _num(row.value), quote=True)}">'
        f'<span class="dz-bar-track-fill" '
        f'style="width: {_num(round(row.fill_pct, 2))}%;" '
        f'title="{html.escape(row.label, quote=True)}: '
        f'{html.escape(row.formatted or _num(row.value), quote=True)}"></span>'
        f"</div>"
        f'<span class="dz-bar-track-value">'
        f"{html.escape(row.formatted or _num(row.value))}</span>"
        f"</div>"
        for row in b.rows
    )
    max_rounded = round(b.max_value, 2)
    max_summary = str(int(max_rounded)) if max_rounded == int(max_rounded) else str(max_rounded)
    return (
        f'<div class="dz-bar-track-region" data-dz-bar-track>'
        f'<div class="dz-bar-track-rows">{rows_html}</div>'
        f'<p class="dz-bar-track-summary">'
        f"{len(b.rows)} rows · scale 0–{max_summary}"
        f"</p>"
        f"</div>"
    )


__all__ = [
    "DOM_CONTRACT",
    "BarTrackRow",
    "BarTrack",
    "EXEMPLARS",
    "render",
]
