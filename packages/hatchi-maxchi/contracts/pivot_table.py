"""HYPERPART: pivot-table — simple cross-tab HTML table shell.

Dual-lock unit is the table root. Caption, dimension headers, and cell
values are host-owned. Class ``.dz-pivot-table`` is the stable substrate
root (``_emit_pivot_table``). Distinct from the region dual-lock in
``contracts/pivot.py`` (``data-dz-pivot``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="pivot-table",
    root=".dz-pivot-table",
    nodes=(Node(".dz-pivot-table", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
