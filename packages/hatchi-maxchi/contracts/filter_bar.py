"""HYPERPART: filter-bar — list/grid filter control row.

Dual-lock unit is the bar root. Select/input controls and grid-filter
seams (``data-dz-grid-filter``) are host-owned. Substrate
``ListFilterBar`` emits ``.dz-filter-bar`` inside ``.dz-table-toolbar-filters``.
Class ``.dz-filter-bar`` is the stable root.

Leftover-honest catalog (cycle 2185): leftover enum junk
(``filter[status]=ghost``) restores All / no filter. Must not
invent the first declared option or an empty collection.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="filter-bar",
    root=".dz-filter-bar",
    nodes=(Node(".dz-filter-bar", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
