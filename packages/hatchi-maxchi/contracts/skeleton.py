"""HYPERPART: skeleton — loading placeholder lines / shapes.

Dual-lock unit is the multi-line root used by Dazzle's Skeleton primitive
(``.dz-skeleton-lines``). Individual shape cells keep ``data-dz-shape``
for gallery demos; the dual-lock attr is ``data-dz-skeleton`` on the stack.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="skeleton",
    root="[data-dz-skeleton]",
    nodes=(
        Node(
            "[data-dz-skeleton]",
            attrs={"data-dz-skeleton": Present()},
        ),
    ),
)


class Skeleton(BaseModel):
    """Loading-state placeholder stack.

    - ``lines`` → number of text-shaped skeleton bars (Dazzle default 3)
    - ``body_html`` → optional trusted override of inner line markup
    """

    lines: int = 3
    body_html: str = Field(
        default="",
        description="Trusted override for inner skeleton shape markup.",
    )


EXEMPLARS: list[Skeleton] = [
    Skeleton(lines=3),
    Skeleton(
        lines=0,
        body_html=(
            '<div class="dz-skeleton" data-dz-shape="circle"></div>'
            '<div class="dz-skeleton" data-dz-shape="text"></div>'
            '<div class="dz-skeleton" data-dz-shape="block"></div>'
        ),
    ),
]


def render(s: Skeleton) -> str:
    """Model → skeleton-lines stack."""
    if s.body_html.strip():
        inner = s.body_html
    else:
        n = max(1, int(s.lines))
        inner = "".join('<div class="dz-skeleton" data-dz-shape="text"></div>' for _ in range(n))
    return f'<div class="dz-skeleton-lines" data-dz-skeleton>{inner}</div>'


__all__ = [
    "DOM_CONTRACT",
    "Skeleton",
    "EXEMPLARS",
    "render",
]
