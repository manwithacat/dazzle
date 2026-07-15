"""HYPERPART: data-list-scroll — filterable list-table packing shell.

Dual-lock unit is the table shell root. Scroll chrome, loading overlay,
empty-state sibling, and embedded table body are host-owned. Class
``.dz-table`` is the stable substrate root (``_emit_data_list_scroll``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="data-list-scroll",
    root=".dz-table",
    nodes=(Node(".dz-table", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
