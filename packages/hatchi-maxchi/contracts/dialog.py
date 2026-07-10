"""HYPERPART: dialog — native <dialog> open trigger contract."""

from __future__ import annotations

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="dialog",
    root="[data-dz-dialog-open]",
    nodes=(Node("[data-dz-dialog-open]", attrs={"data-dz-dialog-open": Present()}),),
)

__all__ = ["DOM_CONTRACT"]
