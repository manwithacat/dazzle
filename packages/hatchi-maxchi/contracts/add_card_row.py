"""HYPERPART: add-card-row — workspace dashboard "Add Card" CTA + picker host.

Dual-lock unit is the row root. Nested card-picker and toggle-picker button
are host-owned. Class ``.dz-add-card-row`` is the stable substrate root.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="add-card-row",
    root=".dz-add-card-row",
    nodes=(Node(".dz-add-card-row", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
