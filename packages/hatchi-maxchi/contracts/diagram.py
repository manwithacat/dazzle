"""HYPERPART: diagram — Mermaid scroll wrapper or structural node/edge list.

Dual-lock unit is the region root. Mermaid CDN loader script is host-owned
(Dazzle appends it after the dual-lock shell).
"""

from __future__ import annotations

import html

from pydantic import BaseModel, Field

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="diagram",
    root="[data-dz-diagram]",
    nodes=(
        Node(
            "[data-dz-diagram]",
            attrs={"data-dz-diagram": Present()},
        ),
    ),
)


class Diagram(BaseModel):
    """ER / graph diagram shell.

    - ``mermaid_source`` → preferred path: scroll wrapper + pre.mermaid
    - ``nodes`` / ``edges`` → structural fallback (no Mermaid)
    """

    mermaid_source: str = ""
    nodes: list[str] = Field(default_factory=list)
    edges: list[tuple[str, str]] = Field(default_factory=list)


EXEMPLARS: list[Diagram] = [
    Diagram(
        mermaid_source=(
            "erDiagram\n  CUSTOMER ||--o{ ORDER : places\n  ORDER ||--|{ LINE_ITEM : contains"
        ),
    ),
    Diagram(
        nodes=["A", "B"],
        edges=[("A", "B")],
    ),
]


def render(d: Diagram) -> str:
    """Model → diagram root (Mermaid shell or structural list)."""
    if d.mermaid_source:
        src = html.escape(d.mermaid_source)
        return (
            f'<div class="dz-diagram-scroll" data-dz-diagram>'
            f'<pre class="mermaid dz-diagram-source">{src}</pre>'
            f"</div>"
        )
    nodes_html = "".join(
        f'<li class="dz-diagram__node" data-dz-key="{html.escape(name, quote=True)}">'
        f"{html.escape(name)}</li>"
        for name in d.nodes
    )
    edges_html = "".join(
        f'<li class="dz-diagram__edge">'
        f'<span class="dz-diagram__edge-from">{html.escape(src)}</span>'
        f'<span class="dz-diagram__edge-arrow">→</span>'
        f'<span class="dz-diagram__edge-to">{html.escape(dst)}</span>'
        f"</li>"
        for src, dst in d.edges
    )
    return (
        f'<section class="dz-diagram" data-dz-diagram>'
        f'<ul class="dz-diagram__nodes">{nodes_html}</ul>'
        f'<ul class="dz-diagram__edges">{edges_html}</ul>'
        f"</section>"
    )


__all__ = [
    "DOM_CONTRACT",
    "Diagram",
    "EXEMPLARS",
    "render",
]
