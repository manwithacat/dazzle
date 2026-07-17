"""HYPERPART: queue — worklist rows with optional SLA attention chrome.

One row is the dual-lock unit. Count/metrics/region chrome are layout
furniture; validate rows with ``require_root`` on the row root.

``badges_html`` / ``actions_html`` / ``date_html`` are trusted SSR fragments
for product-specific columns (status badges, transition buttons, dates).
"""

from __future__ import annotations

import html

from pydantic import BaseModel, Field, field_validator

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="queue",
    root="[data-dz-queue-row]",
    nodes=(
        Node(
            "[data-dz-queue-row]",
            attrs={"data-dz-queue-row": Present()},
        ),
    ),
)


class QueueRow(BaseModel):
    """One triage row in the worklist.

    - ``title`` → headline (required)
    - ``attention_level`` → when set, ``data-dz-attn`` + attention message
    - ``attention_message`` → human copy (never colour-only flag)
    - ``date_html`` → trusted secondary date lines
    - ``badges_html`` → trusted badges next to the title
    - ``actions_html`` → trusted transition action buttons (incl. wrapper)
    - ``drill_url`` → when set, title becomes an ``<a href>`` hub drill
    """

    title: str
    attention_level: str = ""
    attention_message: str = ""
    date_html: str = Field(
        default="",
        description="Trusted HTML for date secondaries (already escaped/SSR-safe).",
    )
    badges_html: str = Field(
        default="",
        description="Trusted HTML for headline badges.",
    )
    actions_html: str = Field(
        default="",
        description="Trusted HTML for the actions column (wrapper + buttons).",
    )
    drill_url: str = Field(
        default="",
        description="Optional VIEW-hub URL (/app/<slug>/{id}); title becomes a link.",
    )

    @field_validator("title")
    @classmethod
    def _title_nonempty(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("QueueRow requires a non-empty title")
        return v


EXEMPLARS: list[QueueRow] = [
    QueueRow(
        title="Refund request — Acme",
        attention_level="critical",
        attention_message="SLA breaches at 16:00 — assign now.",
        date_html='<span class="dz-queue-row-date">2h left</span>',
    ),
    QueueRow(
        title="KYC review — Globex",
        date_html='<span class="dz-queue-row-date">due tomorrow</span>',
    ),
]


def render(row: QueueRow) -> str:
    """Model → one queue row (div; matches Dazzle emitter tag)."""
    title = html.escape(row.title)
    attn_class = ""
    attn_data_attr = ""
    attn_message_html = ""
    if row.attention_level:
        level = html.escape(row.attention_level, quote=True)
        attn_class = f"dz-attn-both dz-attn-tone-{html.escape(row.attention_level)}"
        attn_data_attr = f' data-dz-attn="{level}"'
        if row.attention_message:
            attn_message_html = (
                f'<p class="dz-queue-row-attn">{html.escape(row.attention_message)}</p>'
            )
    if row.drill_url:
        href = html.escape(row.drill_url, quote=True)
        title_html = f'<a class="dz-queue-row-title" href="{href}" data-dz-queue-drill>{title}</a>'
    else:
        title_html = f'<span class="dz-queue-row-title">{title}</span>'
    headline_html = f'<div class="dz-queue-row-headline">{title_html}{row.badges_html}</div>'
    # Trailing space inside class mirrors legacy Jinja when no attn.
    row_open_class = f"dz-queue-row {attn_class}" if attn_class else "dz-queue-row "
    return (
        f'<div class="{row_open_class}" data-dz-queue-row{attn_data_attr}>'
        f'<div class="dz-queue-row-main ">'
        f"{headline_html}"
        f"{attn_message_html}"
        f"{row.date_html}"
        f"</div>"
        f"{row.actions_html}"
        f"</div>"
    )


__all__ = [
    "DOM_CONTRACT",
    "QueueRow",
    "EXEMPLARS",
    "render",
]
