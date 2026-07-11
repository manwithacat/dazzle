"""HYPERPART: bullet — actual-vs-target on qualitative bands.

Dual-lock unit is the region root. Geometry is server-computed inline
percentages (same contract class as funnel widths).
"""

from __future__ import annotations

import html
from typing import Literal

from pydantic import BaseModel, Field

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="bullet",
    root="[data-dz-bullet]",
    nodes=(
        Node(
            "[data-dz-bullet]",
            attrs={"data-dz-bullet": Present()},
        ),
    ),
)

BandColor = Literal["target", "positive", "warning", "destructive", "muted"]
_BAND_COLORS: dict[str, str] = {
    "target": "var(--colour-brand)",
    "positive": "hsl(145, 55%, 45%)",
    "warning": "hsl(40, 90%, 55%)",
    "destructive": "var(--colour-danger)",
    "muted": "var(--colour-text-muted)",
}


class BulletBand(BaseModel):
    """Qualitative range behind the actual bar."""

    from_value: float
    to_value: float
    label: str = ""
    color: BandColor = "target"


class BulletRow(BaseModel):
    """One bullet row — label, actual, optional target."""

    label: str
    actual: float
    target: float | None = None


class Bullet(BaseModel):
    """Stephen Few bullet chart."""

    rows: list[BulletRow] = Field(default_factory=list)
    max_value: float = 100.0
    bands: list[BulletBand] = Field(default_factory=list)
    empty_message: str = "No data available."


EXEMPLARS: list[Bullet] = [
    Bullet(
        max_value=100.0,
        bands=[
            BulletBand(from_value=0, to_value=60, label="Poor", color="destructive"),
            BulletBand(from_value=60, to_value=85, label="OK", color="warning"),
            BulletBand(from_value=85, to_value=100, label="Good", color="positive"),
        ],
        rows=[BulletRow(label="Revenue", actual=72.0, target=80.0)],
    ),
    Bullet(rows=[], max_value=0, empty_message="No bullets"),
]


def _jinja_num(value: float) -> str:
    return str(int(value)) if value == int(value) else str(value)


def render(b: Bullet) -> str:
    """Model → bullet chart region."""
    if not b.rows or b.max_value <= 0:
        return (
            f'<div class="dz-bullet-region" data-dz-bullet>'
            f'<p class="dz-empty-dense" role="status">'
            f"{html.escape(b.empty_message)}</p>"
            f"</div>"
        )

    rows_html: list[str] = []
    for row in b.rows:
        actual_pct = round(row.actual / b.max_value * 100, 2)
        bands_html = ""
        for band in b.bands:
            band_left = round(band.from_value / b.max_value * 100, 2)
            band_width = round((band.to_value - band.from_value) / b.max_value * 100, 2)
            colour = _BAND_COLORS.get(band.color, _BAND_COLORS["target"])
            bands_html += (
                f'<span class="dz-bullet-band" '
                f'style="left: {band_left}%; width: {band_width}%; '
                f'background: {colour};" '
                f'title="{html.escape(band.label, quote=True)}: '
                f'{_jinja_num(band.from_value)}–{_jinja_num(band.to_value)}"></span>'
            )

        actual_rounded = round(row.actual, 1)
        value_html = _jinja_num(actual_rounded)
        target_html = ""
        if row.target is not None:
            target_pct = round(row.target / b.max_value * 100, 2)
            target_html = (
                f'<span class="dz-bullet-target" '
                f'style="left: {target_pct}%;" '
                f'title="{html.escape(row.label, quote=True)} target: '
                f'{_jinja_num(row.target)}"></span>'
            )
            target_rounded = round(row.target, 1)
            value_html += f" / {_jinja_num(target_rounded)}"

        rows_html.append(
            f'<div class="dz-bullet-row">'
            f'<span class="dz-bullet-label">{html.escape(row.label)}</span>'
            f'<div class="dz-bullet-track">'
            f"{bands_html}"
            f'<span class="dz-bullet-actual" '
            f'style="width: {actual_pct}%;" '
            f'title="{html.escape(row.label, quote=True)} actual: '
            f'{_jinja_num(row.actual)}"></span>'
            f"{target_html}"
            f"</div>"
            f'<span class="dz-bullet-value">{value_html}</span>'
            f"</div>"
        )

    return (
        f'<div class="dz-bullet-region" data-dz-bullet>'
        f'<div class="dz-bullet-rows">{"".join(rows_html)}</div>'
        f'<p class="dz-bullet-summary">'
        f"{len(b.rows)} rows · scale 0–{_jinja_num(round(b.max_value, 1))}"
        f"</p>"
        f"</div>"
    )


__all__ = [
    "DOM_CONTRACT",
    "BulletBand",
    "BulletRow",
    "Bullet",
    "EXEMPLARS",
    "render",
]
