"""HYPERPART: menu — details disclosure root (light-dismiss enhanced)."""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="menu",
    root="details.dz-menu, .dz-menu",
    nodes=(Node("details.dz-menu, .dz-menu", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
