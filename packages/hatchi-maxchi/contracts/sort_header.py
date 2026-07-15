"""HYPERPART: sort-header — list column sort control link.

Dual-lock unit is the sort link root. Column key, endpoint, region target,
and active-direction indicator are host-owned. Class ``.dz-list-sort-link``
is the stable substrate root (``_emit_sort_header``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="sort-header",
    root=".dz-list-sort-link",
    nodes=(Node(".dz-list-sort-link", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
