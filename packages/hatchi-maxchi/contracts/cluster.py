"""HYPERPART: cluster — horizontal wrapping group (substrate Row).

Dual-lock unit is the cluster root. Gap rides ``data-dz-gap``; optional
``data-dz-align``. Child fragments are host-owned. Class ``.dz-cluster`` is
the stable substrate root (``_emit_row``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="cluster",
    root=".dz-cluster",
    nodes=(Node(".dz-cluster", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
