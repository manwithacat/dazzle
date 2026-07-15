"""HYPERPART: sidebar — primary navigation rail.

Dual-lock unit is the nav root. Header/items/groups are host-owned.
Class ``.dz-sidebar`` is the stable substrate root (see app-shell.css /
nav chrome).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="sidebar",
    root=".dz-sidebar",
    nodes=(Node(".dz-sidebar", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
