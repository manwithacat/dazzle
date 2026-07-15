"""HYPERPART: nav-group — collapsible primary-nav section.

Dual-lock unit is the details root. Label, icon, open/collapsed state, and
nested nav items are host-owned. Class ``.dz-nav-group`` is the stable
substrate root (``_emit_nav_group``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="nav-group",
    root=".dz-nav-group",
    nodes=(Node(".dz-nav-group", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
