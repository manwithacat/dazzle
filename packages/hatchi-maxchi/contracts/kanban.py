"""HYPERPART: kanban — board card unit (title + fields + optional attention).

One card is the dual-lock unit. Columns / board chrome are layout furniture;
validate cards with ``require_root`` on the card root.

``fields_html`` is trusted SSR for secondary field lines (label: value pairs
or badges). Attention is never colour-only — message text rides with
``data-dz-attn`` when set.

Rearrange (Linear-class status move — design
``docs/superpowers/specs/2026-07-28-kanban-rearrange-htmx-design.md``):
when the host permits UPDATE, SSR may stamp ``row_id``, ``from_state``,
``allowed_to``, and ``draggable``. Absent those attrs the card is
presentation-only (read-only personas, no SM edge).
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
    - ``row_id`` / ``from_state`` / ``allowed_to`` → rearrange capability
      (empty allowed_to ⇒ no drag; host omits for read-only personas)
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
    row_id: str = Field(
        default="",
        description="Entity id for PUT rearrange; empty when not rearrange-capable.",
    )
    from_state: str = Field(
        default="",
        description="Current column / status key (data-dz-from-state).",
    )
    allowed_to: tuple[str, ...] = Field(
        default=(),
        description="Legal destination states for this card (manual SM edges).",
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
        row_id="card-1",
        from_state="open",
        allowed_to=("in_progress", "done"),
    ),
    KanbanCard(
        title="KYC review — Globex",
        fields_html='<p class="dz-kanban-card-field"><span>Due:</span> tomorrow</p>',
        row_id="card-2",
        from_state="in_progress",
        allowed_to=("done",),
    ),
    # Read-only exemplar — no rearrange attrs stamped for dual-lock baseline.
    KanbanCard(
        title="Audit sample — locked",
        fields_html='<p class="dz-kanban-card-field"><span>Read only</span></p>',
    ),
]


def _move_select_html(card: KanbanCard) -> str:
    """Keyboard parity control — same targets as drag (Linear requirement R6)."""
    if not card.row_id or not card.allowed_to:
        return ""
    options = ['<option value="">Move to…</option>']
    for state in card.allowed_to:
        label = html.escape(state.replace("_", " ").title())
        val = html.escape(state, quote=True)
        options.append(f'<option value="{val}">{label}</option>')
    return (
        f'<div class="dz-kanban-card-move">'
        f'<label><span class="visually-hidden">Move card</span>'
        f'<select data-dz-kanban-move aria-label="Move {html.escape(card.title)}">'
        f"{''.join(options)}"
        f"</select></label>"
        f"</div>"
    )


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

    # Dual-lock root: always data-dz-kanban-card; rearrange attrs only when
    # host stamped capability (read-only boards stay presentation-only).
    root_bits = ["data-dz-kanban-card"]
    id_attr = ""
    if card.row_id:
        rid = html.escape(card.row_id, quote=True)
        root_bits.append(f'data-dz-entity-id="{rid}"')
        id_attr = f' id="dz-kanban-card-{rid}"'
    if card.from_state:
        root_bits.append(f'data-dz-from-state="{html.escape(card.from_state, quote=True)}"')
    if card.allowed_to:
        allowed = html.escape(" ".join(card.allowed_to), quote=True)
        root_bits.append(f'data-dz-allowed-to="{allowed}"')
        root_bits.append('draggable="true"')
    root_attrs = " ".join(root_bits)

    return (
        f'<div class="dz-kanban-card" {root_attrs}{id_attr}>'
        f'<div class="dz-kanban-card-body">'
        f"{title_html}"
        f"{card.fields_html}"
        f"{attn_html}"
        f"{_move_select_html(card)}"
        f"</div>"
        f"</div>"
    )


__all__ = [
    "DOM_CONTRACT",
    "KanbanCard",
    "EXEMPLARS",
    "render",
]
