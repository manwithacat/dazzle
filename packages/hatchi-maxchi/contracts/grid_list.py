"""HYPERPART: grid_list — responsive grid of plain record cells.

Dual-lock unit is the grid-list root. Cells, titles, and field lines are
host-owned. Class ``.dz-grid-list`` is the stable substrate root (gallery CSS;
no FragmentRenderer emit yet). Often nested under ``.dz-grid-region``.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="grid_list",
    root=".dz-grid-list",
    nodes=(Node(".dz-grid-list", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
