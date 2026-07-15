"""HYPERPART: column-visibility-menu — grid column toggle disclosure.

Dual-lock unit is the details menu root. Column keys, persistence, and
grid-controller seams are host-owned. Class ``.dz-table-col-menu`` is the
stable substrate root (``_emit_column_visibility_menu``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="column-visibility-menu",
    root=".dz-table-col-menu",
    nodes=(Node(".dz-table-col-menu", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
