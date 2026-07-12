"""HYPERPART: pipeline — sequential stage workflow row.

Dual-lock unit is the region root. Stage list HTML is host-owned.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="pipeline",
    root="[data-dz-pipeline]",
    nodes=(
        Node(
            "[data-dz-pipeline]",
            attrs={"data-dz-pipeline": Present()},
        ),
    ),
)


class Pipeline(BaseModel):
    """Pipeline steps region shell.

    - ``body_html`` → trusted empty-state or stages list
    """

    body_html: str = Field(
        default="",
        description="Trusted empty-state or .dz-pipeline-stages markup.",
    )


EXEMPLARS: list[Pipeline] = [
    Pipeline(
        body_html=(
            '<ol class="dz-pipeline-stages">'
            '<li class="dz-pipeline-stage">'
            '<span class="dz-pipeline-stage-label">Lead</span>'
            '<span class="dz-pipeline-stage-value">12</span></li></ol>'
        ),
    ),
    Pipeline(body_html='<p class="dz-empty-dense" role="status">No pipeline data available.</p>'),
]


def render(p: Pipeline) -> str:
    """Model → pipeline-steps region root."""
    return f'<div class="dz-pipeline-steps-region" data-dz-pipeline>{p.body_html}</div>'


__all__ = [
    "DOM_CONTRACT",
    "Pipeline",
    "EXEMPLARS",
    "render",
]
