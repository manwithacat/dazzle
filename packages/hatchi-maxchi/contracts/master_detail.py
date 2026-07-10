"""HYPERPART: master-detail — selection marker + detail pane root."""

from __future__ import annotations

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="master-detail",
    root="[data-dz-master-detail]",
    nodes=(Node("[data-dz-master-detail]", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
