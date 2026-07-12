"""HYPERPART: tree — native details/summary hierarchy.

Dual-lock unit is the region root. Nested node markup is host-owned
(recursive details/summary + chevron SVG).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="tree",
    root="[data-dz-tree]",
    nodes=(
        Node(
            "[data-dz-tree]",
            attrs={"data-dz-tree": Present()},
        ),
    ),
)


class Tree(BaseModel):
    """Tree region shell.

    - ``body_html`` → trusted recursive ``dz-tree-node`` details forest
    """

    body_html: str = Field(
        default="",
        description="Trusted top-level tree node markup (details/summary forest).",
    )


EXEMPLARS: list[Tree] = [
    Tree(
        body_html=(
            '<details class="dz-tree-node" open>'
            '<summary class="dz-tree-summary">'
            '<span class="dz-tree-label">Engineering</span>'
            '<span class="dz-tree-count">1</span></summary>'
            '<div class="dz-tree-children">'
            '<details class="dz-tree-node">'
            '<summary class="dz-tree-summary">'
            '<span class="dz-tree-label">Platform</span></summary>'
            "</details></div></details>"
        ),
    ),
    Tree(body_html=""),
]


def render(t: Tree) -> str:
    """Model → tree region root."""
    return f'<div class="dz-tree" data-dz-tree>{t.body_html}</div>'


__all__ = [
    "DOM_CONTRACT",
    "Tree",
    "EXEMPLARS",
    "render",
]
