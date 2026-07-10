"""HYPERPART: grid (extension: dz-grid-cols) — column visibility seam."""

from __future__ import annotations

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="grid-cols",
    root="[data-dz-grid]",
    nodes=(
        Node("[data-dz-grid-col-toggle]", attrs={"data-dz-grid-col-toggle": Present()}),
        Node("[data-dz-col]", attrs={"data-dz-col": Present()}),
        Node("[data-dz-grid-cols-reset]", attrs={}),
    ),
)

__all__ = ["DOM_CONTRACT"]
