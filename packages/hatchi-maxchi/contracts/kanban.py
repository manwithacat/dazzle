"""HYPERPART: kanban — board card unit (title + fields + optional attention).

One card is the dual-lock unit. Columns / board chrome are layout furniture;
validate cards with ``require_root`` on the card root.

``fields_html`` is trusted SSR for secondary field lines (label: value pairs
or badges). Attention is never colour-only — message text rides with
``data-dz-attn`` when set.
"""

from __future__ import annotations

import html

from pydantic import BaseModel, Field, field_validator

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="kanban",
    root="[data-dz-kanban-card]",
    nodes=(
        Node(
            "[data-dz-kanban-card]",
            attrs={"data-dz-kanban-card": Present()},
        ),
    ),
)


class KanbanCard(BaseModel):
    """One card in a kanban column.

    - ``title`` → headline (required)
    - ``fields_html`` → trusted secondary field lines
    - ``attention_level`` / ``attention_message`` → optional SLA chrome
    - ``drill_url`` → when set, title becomes an ``<a href>`` hub drill
      (same class as queue row / list #1303; host gates EDIT paths)
    """

    title: str
    fields_html: str = Field(
        default="",
        description="Trusted HTML for secondary field lines.",
    )
    attention_level: str = ""
    attention_message: str = ""
    drill_url: str = Field(
        default="",
        description="Optional hub URL (/app/<slug>/{id} or …/edit); title becomes a link.",
    )

    @field_validator("title")
    @classmethod
    def _title_nonempty(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("KanbanCard requires a non-empty title")
        return v


EXEMPLARS: list[KanbanCard] = [
    KanbanCard(
        title="Refund request — Acme",
        fields_html='<p class="dz-kanban-card-field"><span>Amount:</span> £1,250</p>',
        attention_level="critical",
        attention_message="SLA breaches at 16:00",
    ),
    KanbanCard(
        title="KYC review — Globex",
        fields_html='<p class="dz-kanban-card-field"><span>Due:</span> tomorrow</p>',
    ),
]


def render(card: KanbanCard) -> str:
    """Model → one kanban card."""
    title = html.escape(card.title)
    if card.drill_url:
        href = html.escape(card.drill_url, quote=True)
        # Keep h4 + class for dual-lock/CSS; wrap title text in hub drill
        # (queue-row pattern; empty drill_url stays byte-stable plain h4).
        title_html = (
            f'<h4 class="dz-kanban-card-title">'
            f'<a href="{href}" data-dz-kanban-drill>{title}</a>'
            f"</h4>"
        )
    else:
        title_html = f'<h4 class="dz-kanban-card-title">{title}</h4>'
    attn_html = ""
    if card.attention_level:
        level = html.escape(card.attention_level, quote=True)
        msg = html.escape(card.attention_message)
        attn_html = f'<p class="dz-kanban-card-attn" data-dz-attn="{level}">{msg}</p>'
    return (
        f'<div class="dz-kanban-card" data-dz-kanban-card>'
        f'<div class="dz-kanban-card-body">'
        f"{title_html}"
        f"{card.fields_html}"
        f"{attn_html}"
        f"</div>"
        f"</div>"
    )


__all__ = [
    "DOM_CONTRACT",
    "KanbanCard",
    "EXEMPLARS",
    "render",
]
