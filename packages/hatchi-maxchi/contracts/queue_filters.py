"""HYPERPART: queue-filters — queue/list filter-bar packing shell.

Dual-lock unit is the filter row root. Select controls and HTMX target
attrs are host-owned. Class ``.dz-queue-filters`` is the stable substrate
root (``_emit_filter_bar``). Distinct from the list filter-bar dual-lock
``.dz-filter-bar`` (``_emit_list_filter_bar``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="queue-filters",
    root=".dz-queue-filters",
    nodes=(Node(".dz-queue-filters", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
