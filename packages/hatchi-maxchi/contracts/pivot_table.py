"""HYPERPART: pivot-table — simple cross-tab HTML table shell.

Dual-lock unit is the table root, marked ``data-dz-pivot-table``
(``_emit_pivot_table``); the skin is the pivot grid (``dz-pivot-grid``,
measure cells ``is-measure``, #1799). Caption, dimension headers, and cell
values are host-owned. Distinct from the region dual-lock in
``contracts/pivot.py`` (``data-dz-pivot``).
"""

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="pivot-table",
    root="[data-dz-pivot-table]",
    nodes=(Node("[data-dz-pivot-table]", attrs={"data-dz-pivot-table": Present()}),),
)

__all__ = ["DOM_CONTRACT"]
