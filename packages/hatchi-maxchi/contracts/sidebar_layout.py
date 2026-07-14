"""HYPERPART: sidebar_layout — two-pane flex wrap (side + fluid content).

Dual-lock unit is the layout root. Side/content children, ``--dz-sidebar-width``,
and ``data-dz-side`` are host-owned. Class ``.dz-sidebar-layout`` is the stable
substrate root (gallery layout primitive; no FragmentRenderer emit yet).
Distinct from contracts/sidebar.py (``.dz-sidebar`` nav rail).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="sidebar_layout",
    root=".dz-sidebar-layout",
    nodes=(Node(".dz-sidebar-layout", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
