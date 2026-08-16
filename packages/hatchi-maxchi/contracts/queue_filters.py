"""HYPERPART: queue-filters — queue/list filter-bar packing shell.

Dual-lock unit is the filter row root. Select controls and HTMX target
attrs are host-owned. Class ``.dz-queue-filters`` is the stable substrate
root (``_emit_filter_bar``). Distinct from the list filter-bar dual-lock
``.dz-filter-bar`` (``_emit_list_filter_bar``).

Leftover honesty (cycle 2179): each select ``hx-get`` must echo
leftover-honest ``include_closed`` / ``as_of``. Bare
``hx-get="{endpoint}"`` + ``hx-include="closest .filter-bar"``
dropped them and invented open-only / current after a filter
change. Leftover junk (``zzz``, ``2abc``, ``maybe``,
``not-a-date``) must not invent. Valid ``true`` / YYYY-MM-DD
still ride hx-get. Rest-state gallery is unchanged (oral #33).
Not leftover list include_closed / related-tab as_of / DETAIL
as_of onto the edit form.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="queue-filters",
    root=".dz-queue-filters",
    nodes=(Node(".dz-queue-filters", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
