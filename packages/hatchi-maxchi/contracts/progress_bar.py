"""HYPERPART: progress — toned determinate bar.

Dual-lock unit is the root ``.dz-progress`` progressbar. Fill is owned by
``.dz-progress__bar`` via ``--dz-progress-value``; optional ``data-dz-tone``
tints success / warning / destructive.
"""

from __future__ import annotations

import html
from typing import Literal

from pydantic import BaseModel, Field

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="progress",
    root=".dz-progress",
    nodes=(Node(".dz-progress", attrs={}),),
)

Tone = Literal["", "success", "warning", "destructive"]


class ProgressBarModel(BaseModel):
    """Single determinate progress track (0..max_value)."""

    value: float = 0.0
    label: str = "Progress"
    tone: Tone = ""
    max_value: float = Field(default=100.0, gt=0)


EXEMPLARS: list[ProgressBarModel] = [
    ProgressBarModel(value=62, label="Storage used"),
    ProgressBarModel(value=100, label="Upload progress", tone="success"),
    ProgressBarModel(value=38, label="Urgent queue", tone="warning"),
]


def _pct_str(value: float, max_value: float) -> str:
    pct = max(0.0, min(100.0, (float(value) / float(max_value)) * 100.0))
    return str(int(pct)) if pct == int(pct) else f"{pct:.1f}".rstrip("0").rstrip(".")


def render(p: ProgressBarModel) -> str:
    """Model → dual-lock progress bar markup."""
    pct = _pct_str(p.value, p.max_value)
    now = (
        str(int(p.value))
        if float(p.value) == int(p.value)
        else f"{float(p.value):.1f}".rstrip("0").rstrip(".")
    )
    max_s = (
        str(int(p.max_value))
        if float(p.max_value) == int(p.max_value)
        else f"{float(p.max_value):.1f}".rstrip("0").rstrip(".")
    )
    label = html.escape(p.label or "Progress", quote=True)
    tone_attr = f' data-dz-tone="{html.escape(p.tone, quote=True)}"' if p.tone else ""
    return (
        f'<div class="dz-progress" role="progressbar" aria-label="{label}" '
        f'aria-valuenow="{now}" aria-valuemin="0" aria-valuemax="{max_s}"{tone_attr}>'
        f'<div class="dz-progress__bar" style="--dz-progress-value:{pct}%"></div>'
        f"</div>"
    )


__all__ = [
    "DOM_CONTRACT",
    "Tone",
    "ProgressBarModel",
    "EXEMPLARS",
    "render",
]
