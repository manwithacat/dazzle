"""HYPERPART: metrics — KPI / metric-tile strip unit.

One tile is the dual-lock unit. The packing grid (``data-dz-tile-count``)
is layout furniture; validate tiles with ``require_root`` on the tile root.

``data-dz-metric-key`` is the stable anchor (tests/telemetry). Optional
``data-dz-tone`` tints the surface. Delta block carries direction/sentiment
attrs when present.
"""

from __future__ import annotations

import html
import re
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator

from contracts._kit import DomContract, Node, Present

Tone = Literal["", "positive", "warning", "destructive", "accent", "neutral"]
DeltaDir = Literal["", "up", "down", "flat"]
DeltaSent = Literal["", "positive_up", "positive_down"]
_TONES = ("", "positive", "warning", "destructive", "accent", "neutral")

DOM_CONTRACT = DomContract(
    part="metrics",
    root="[data-dz-metric-key]",
    nodes=(
        Node(
            "[data-dz-metric-key]",
            attrs={"data-dz-metric-key": Present()},
        ),
    ),
)


def _slug_key(label: str) -> str:
    return re.sub(r"_+", "_", label.lower().replace(" ", "_")).strip("_") or "metric"


class MetricTile(BaseModel):
    """One KPI tile.

    - ``label`` / ``value`` → display (value already formatted by the host)
    - ``metric_key`` → stable ``data-dz-metric-key`` (defaults from label)
    - ``tone`` → optional surface tint
    - delta fields → optional delta block (direction drives presence)
    """

    label: str
    value: str
    metric_key: str = ""
    tone: Tone = ""
    delta_direction: DeltaDir = ""
    delta_sentiment: DeltaSent = ""
    delta_value: str = ""
    delta_pct: float = 0.0
    delta_period_label: str = ""

    @field_validator("label")
    @classmethod
    def _label_nonempty(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("MetricTile requires a non-empty label")
        return v

    @model_validator(mode="after")
    def _default_key(self) -> MetricTile:
        if not self.metric_key:
            self.metric_key = _slug_key(self.label)
        return self


EXEMPLARS: list[MetricTile] = [
    MetricTile(label="Outstanding", value="£12,450", metric_key="outstanding"),
    MetricTile(
        label="Paid this month",
        value="£48,900",
        metric_key="paid",
        tone="positive",
        delta_direction="up",
        delta_sentiment="positive_up",
        delta_value="12%",
        delta_pct=12.0,
        delta_period_label="last month",
    ),
    MetricTile(
        label="Overdue",
        value="3",
        metric_key="overdue",
        tone="warning",
    ),
]


def render(tile: MetricTile) -> str:
    """Model → one metric tile."""
    key = html.escape(tile.metric_key, quote=True)
    label = html.escape(tile.label)
    value = html.escape(tile.value)
    tone_attr = ""
    if tile.tone:
        tone_attr = f' data-dz-tone="{html.escape(tile.tone, quote=True)}"'

    delta_html = ""
    if tile.delta_direction:
        is_good = (tile.delta_direction == "up" and tile.delta_sentiment == "positive_up") or (
            tile.delta_direction == "down" and tile.delta_sentiment == "positive_down"
        )
        is_bad = (tile.delta_direction == "down" and tile.delta_sentiment == "positive_up") or (
            tile.delta_direction == "up" and tile.delta_sentiment == "positive_down"
        )
        delta_tone = "positive" if is_good else ("destructive" if is_bad else "neutral")
        arrow = (
            "↑"
            if tile.delta_direction == "up"
            else ("↓" if tile.delta_direction == "down" else "→")
        )
        sign = "+" if tile.delta_direction == "up" else ""
        pct_html = (
            f'<span class="dz-metric-delta-pct">({tile.delta_pct}%)</span>'
            if tile.delta_pct
            else ""
        )
        period_html = (
            f'<span class="dz-metric-delta-period">vs {html.escape(tile.delta_period_label)}</span>'
        )
        delta_html = (
            f'<div class="dz-metric-delta" '
            f'data-dz-delta-tone="{delta_tone}" '
            f'data-dz-delta-direction="{html.escape(tile.delta_direction, quote=True)}" '
            f'data-dz-delta-sentiment="{html.escape(tile.delta_sentiment, quote=True)}">'
            f'<span aria-hidden="true">{arrow}</span>'
            f'<span class="dz-metric-delta-value">{sign}{html.escape(tile.delta_value)}</span>'
            f"{pct_html}"
            f"{period_html}"
            f"</div>"
        )

    return (
        f'<div class="dz-metric-tile" data-dz-metric-key="{key}"{tone_attr}>'
        f'<div class="dz-metric-label">{label}</div>'
        f'<div class="dz-metric-value">{value}</div>'
        f"{delta_html}"
        f"</div>"
    )


__all__ = [
    "DOM_CONTRACT",
    "MetricTile",
    "EXEMPLARS",
    "render",
    "Tone",
]
