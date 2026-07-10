"""HYPERPART: command — palette dialog root contract."""

from __future__ import annotations

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="command",
    root="[data-dz-command]",
    nodes=(Node("[data-dz-command]", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
