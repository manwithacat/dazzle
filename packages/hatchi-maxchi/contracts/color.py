"""HYPERPART: field (extension: dz-color) — colour input group."""

from __future__ import annotations

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="color",
    root="[data-dz-color-group]",
    nodes=(Node("[data-dz-color-group]", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
