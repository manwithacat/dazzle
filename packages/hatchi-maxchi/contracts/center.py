"""HYPERPART: center — measure-capped, centred column (prose/forms).

Dual-lock unit is the center root. Children and ``data-dz-measure``
(prose/wide/full) are host-owned. Class ``.dz-center`` is the stable
substrate root (gallery partial; no FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="center",
    root=".dz-center",
    nodes=(Node(".dz-center", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
