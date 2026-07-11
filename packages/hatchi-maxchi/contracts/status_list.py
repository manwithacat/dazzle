"""HYPERPART: status-list — icon + title + caption + state-pill rows.

One entry is the dual-lock unit. The region wrapper / ``<ul>`` are layout
furniture; validate entries with ``require_root`` on the entry root.

``icon_html`` is trusted SSR for the icon slot. Empty → spacer so titles
align with iconned rows (zero-paint / column-align gate).
"""

from __future__ import annotations

import html
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from contracts._kit import DomContract, Node, OneOf, Present

State = Literal["neutral", "positive", "warning", "destructive", "accent"]
_STATES = ("neutral", "positive", "warning", "destructive", "accent")

DOM_CONTRACT = DomContract(
    part="status-list",
    root="[data-dz-status-entry]",
    nodes=(
        Node(
            "[data-dz-status-entry]",
            attrs={
                "data-dz-status-entry": Present(),
                "data-dz-state": OneOf(*_STATES),
            },
        ),
    ),
)


class StatusListEntry(BaseModel):
    """One status row.

    - ``title`` → primary line (required)
    - ``state`` → tone via ``data-dz-state``; non-neutral also renders a pill
    - ``caption`` → optional secondary line
    - ``icon_html`` → trusted HTML for the icon slot; empty → spacer
    """

    title: str
    state: State = "neutral"
    caption: str = ""
    icon_html: str = Field(
        default="",
        description="Trusted HTML for the icon slot (already escaped/SSR-safe).",
    )

    @field_validator("title")
    @classmethod
    def _title_nonempty(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("StatusListEntry requires a non-empty title")
        return v


EXEMPLARS: list[StatusListEntry] = [
    StatusListEntry(
        title="Payments API",
        state="positive",
        caption="Operational · 99.99% this month",
        icon_html='<span class="dz-status-list-icon" aria-hidden="true">✓</span>',
    ),
    StatusListEntry(
        title="Webhooks",
        state="warning",
        caption="Elevated retries since 09:20",
        icon_html='<span class="dz-status-list-icon" aria-hidden="true">!</span>',
    ),
    StatusListEntry(
        title="Nightly export",
        state="neutral",
        caption="Scheduled 02:00",
    ),
]


def render(entry: StatusListEntry) -> str:
    """Model → one ``<li>`` status entry."""
    state = html.escape(entry.state, quote=True)
    title = html.escape(entry.title)
    if entry.icon_html.strip():
        icon_html = entry.icon_html
    else:
        icon_html = '<span class="dz-status-list-icon-spacer" aria-hidden="true"></span>'
    caption_html = ""
    if entry.caption:
        caption_html = f'<div class="dz-status-list-caption">{html.escape(entry.caption)}</div>'
    pill_html = ""
    if entry.state != "neutral":
        pill_html = f'<span class="dz-status-list-pill">{html.escape(entry.state)}</span>'
    return (
        f'<li class="dz-status-list-entry" data-dz-status-entry '
        f'data-dz-state="{state}">'
        f"{icon_html}"
        f'<div class="dz-status-list-text">'
        f'<div class="dz-status-list-title">{title}</div>'
        f"{caption_html}"
        f"</div>"
        f"{pill_html}"
        f"</li>"
    )


def render_list(entries: list[StatusListEntry]) -> str:
    """Full list body (entries only — no region wrapper)."""
    return "".join(render(e) for e in entries)


__all__ = [
    "DOM_CONTRACT",
    "StatusListEntry",
    "EXEMPLARS",
    "render",
    "render_list",
    "State",
]
