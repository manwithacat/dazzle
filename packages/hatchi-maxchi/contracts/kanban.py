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
    """

    title: str
    fields_html: str = Field(
        default="",
        description="Trusted HTML for secondary field lines.",
    )
    attention_level: str = ""
    attention_message: str = ""

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
    attn_html = ""
    if card.attention_level:
        level = html.escape(card.attention_level, quote=True)
        msg = html.escape(card.attention_message)
        attn_html = f'<p class="dz-kanban-card-attn" data-dz-attn="{level}">{msg}</p>'
    return (
        f'<div class="dz-kanban-card" data-dz-kanban-card>'
        f'<div class="dz-kanban-card-body">'
        f'<h4 class="dz-kanban-card-title">{title}</h4>'
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
