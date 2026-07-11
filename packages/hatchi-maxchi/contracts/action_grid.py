"""HYPERPART: action-grid — tone-tinted CTA cards (dashboard work surface).

One card is the dual-lock unit (label + tone + optional icon/count/url).
The grid wrapper (``dz-action-grid-region`` / ``dz-action-grid``) is layout
furniture; validate cards with ``require_root`` on the card root.

``icon_html`` is trusted SSR for the icon slot (Lucide ``<svg>``, …). Empty
string → spacer so label-only cards keep row height (zero-paint gate).
"""

from __future__ import annotations

import html
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from contracts._kit import DomContract, Node, OneOf, Present

Tone = Literal["neutral", "positive", "warning", "destructive", "accent"]
_TONES = ("neutral", "positive", "warning", "destructive", "accent")

DOM_CONTRACT = DomContract(
    part="action-grid",
    root="[data-dz-action-card]",
    nodes=(
        Node(
            "[data-dz-action-card]",
            attrs={
                "data-dz-action-card": Present(),
                "data-dz-tone": OneOf(*_TONES),
            },
        ),
    ),
)


class ActionCard(BaseModel):
    """One CTA tile the action-grid region emits.

    - ``label`` → primary line (required)
    - ``tone`` → surface tint via ``data-dz-tone`` (and count badge when set)
    - ``url`` → non-empty makes the card an ``<a>``; empty → static ``<div>``
    - ``count`` → ``None`` omits badge; ``0`` still renders a badge
    - ``icon_html`` → trusted HTML for the icon slot; empty → spacer
    """

    label: str
    tone: Tone = "neutral"
    url: str = ""
    count: int | None = None
    icon_html: str = Field(
        default="",
        description="Trusted HTML for the icon slot (already escaped/SSR-safe).",
    )

    @field_validator("label")
    @classmethod
    def _label_nonempty(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("ActionCard requires a non-empty label")
        return v


EXEMPLARS: list[ActionCard] = [
    ActionCard(
        label="Overdue invoices",
        tone="warning",
        url="#",
        count=3,
        icon_html='<span class="dz-action-card-icon" aria-hidden="true">!</span>',
    ),
    ActionCard(
        label="Awaiting approval",
        tone="accent",
        url="/app/invoices?status=pending",
        count=12,
    ),
    ActionCard(
        label="Nothing else today",
        tone="neutral",
    ),
    ActionCard(
        label="Zero still badges",
        tone="positive",
        count=0,
    ),
]


def render(card: ActionCard) -> str:
    """Model → one action card (anchor when url set, else div)."""
    tone = html.escape(card.tone, quote=True)
    label = html.escape(card.label)
    if card.icon_html.strip():
        icon_html = card.icon_html
    else:
        icon_html = '<span class="dz-action-card-icon-spacer"></span>'
    count_html = ""
    if card.count is not None:
        count_html = (
            f'<span class="dz-action-card-count" data-dz-tone-badge="{tone}">{card.count}</span>'
        )
    body = (
        f'<div class="dz-action-card-row">{icon_html}{count_html}</div>'
        f'<span class="dz-action-card-label">{label}</span>'
    )
    root_open = f'class="dz-action-card" data-dz-action-card data-dz-tone="{tone}"'
    if card.url:
        href = html.escape(card.url, quote=True)
        return f'<a href="{href}" {root_open}>{body}</a>'
    return f"<div {root_open}>{body}</div>"


__all__ = [
    "DOM_CONTRACT",
    "ActionCard",
    "EXEMPLARS",
    "render",
    "Tone",
]
