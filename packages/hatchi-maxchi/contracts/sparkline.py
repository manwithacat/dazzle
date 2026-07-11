"""HYPERPART: sparkline — headline number + optional tiny area glyph.

The dual-lock unit is the whole sparkline region. ``points`` is the series
data; SVG geometry is derived server-side (glyph is decoration; numbers are
content).
"""

from __future__ import annotations

import html

from pydantic import BaseModel, Field

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="sparkline",
    root="[data-dz-sparkline]",
    nodes=(
        Node(
            "[data-dz-sparkline]",
            attrs={"data-dz-sparkline": Present()},
        ),
    ),
)


class Sparkline(BaseModel):
    """Compact time-series for KPI tiles.

    - ``points`` → ``(label, value)`` pairs (latest is the headline)
    - ``empty_message`` → shown when series is empty
    Single-point series omit the SVG (headline only).
    """

    points: list[tuple[str, float]] = Field(default_factory=list)
    empty_message: str = "—"


EXEMPLARS: list[Sparkline] = [
    Sparkline(
        points=[
            ("12:00", 120.0),
            ("12:15", 140.0),
            ("12:30", 100.0),
            ("12:45", 160.0),
            ("13:00", 184.0),
        ]
    ),
    Sparkline(points=[("now", 42.0)]),
    Sparkline(points=[], empty_message="No samples"),
]


def render(s: Sparkline) -> str:
    """Model → sparkline region (matches Dazzle emitter geometry)."""
    if not s.points:
        return (
            f'<div class="dz-sparkline-region" data-dz-sparkline>'
            f'<div class="dz-sparkline-empty">{html.escape(s.empty_message)}</div>'
            f"</div>"
        )

    last_label, last_value = s.points[-1]
    last_value_str = str(int(last_value)) if last_value == int(last_value) else str(last_value)
    max_val = max(v for _, v in s.points)
    if max_val <= 0:
        max_val = 1.0
    max_val_str = str(int(max_val)) if max_val == int(max_val) else str(max_val)
    count = len(s.points)

    headline = (
        f'<div class="dz-sparkline-headline">'
        f'<span class="dz-sparkline-value">{html.escape(last_value_str)}</span>'
        f'<span class="dz-sparkline-bucket-label">{html.escape(last_label)}</span>'
        f"</div>"
    )

    if count <= 1:
        return f'<div class="dz-sparkline-region" data-dz-sparkline>{headline}</div>'

    w, h, pt, pb = 180, 32, 2, 2
    plot_h = h - pt - pb
    step = w / (count - 1)
    pts = []
    for i, (_, v) in enumerate(s.points):
        x = round(i * step, 2)
        y = round(pt + plot_h - (v / max_val * plot_h), 2)
        pts.append(f"{x},{y}")
    pts_str = " ".join(pts)

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {w} {h}" '
        f'class="dz-sparkline-svg" role="img" '
        f'aria-label="Sparkline — {count} points, latest '
        f'{html.escape(last_value_str)}, peak {html.escape(max_val_str)}">'
        f'<polygon points="0,{h} {pts_str} {w},{h}" '
        f'fill="var(--colour-brand)" fill-opacity="0.15" stroke="none" />'
        f'<polyline points="{pts_str}" fill="none" '
        f'stroke="var(--colour-brand)" stroke-width="1.25" '
        f'stroke-linejoin="round" stroke-linecap="round" />'
        f"</svg>"
    )
    return f'<div class="dz-sparkline-region" data-dz-sparkline>{headline}{svg}</div>'


__all__ = [
    "DOM_CONTRACT",
    "Sparkline",
    "EXEMPLARS",
    "render",
]
