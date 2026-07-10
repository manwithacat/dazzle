"""HYPERPART: tabs — tablist root + panel targets."""

from __future__ import annotations

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="tabs",
    root="[data-dz-tabs]",
    nodes=(
        Node("[data-dz-tabs]", attrs={}),
        Node("[data-dz-tab-target]", attrs={"data-dz-tab-target": Present()}),
    ),
)

__all__ = ["DOM_CONTRACT"]
