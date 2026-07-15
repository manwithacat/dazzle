"""HYPERPART: nav-item — primary navigation list entry.

Dual-lock unit is the ``li`` root. Link href, active/current state, icon,
and ``data-dz-nav`` slug are host-owned. Class ``.dz-nav-item`` is the
stable substrate root (``_emit_nav_item``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="nav-item",
    root=".dz-nav-item",
    nodes=(Node(".dz-nav-item", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
