"""HYPERPART: grid (extension: dz-grid-resize) — column resize seam."""

from __future__ import annotations

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="grid-resize",
    root="[data-dz-grid]",
    nodes=(
        Node("[data-dz-grid-resize]", attrs={"data-dz-grid-resize": Present()}),
        Node("col[data-dz-col], [data-dz-col]", attrs={"data-dz-col": Present()}),
    ),
)

__all__ = ["DOM_CONTRACT"]
