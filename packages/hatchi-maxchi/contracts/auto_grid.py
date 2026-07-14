"""HYPERPART: auto_grid — responsive equal-column card grid (no breakpoints).

Dual-lock unit is the auto-grid root. Children, ``--dz-grid-min``, and
``data-dz-gap`` are host-owned. Class ``.dz-auto-grid`` is the stable
substrate root (gallery partial; no FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="auto_grid",
    root=".dz-auto-grid",
    nodes=(Node(".dz-auto-grid", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
