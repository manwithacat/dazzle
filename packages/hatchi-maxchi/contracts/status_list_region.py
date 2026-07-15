"""HYPERPART: status-list-region — packing shell for status-list entries.

Dual-lock unit is the region root. Entry rows and empty-state copy are
host-owned. Class ``.dz-status-list-region`` is the stable substrate root
(``_emit_status_list``). Distinct from the entry unit in
``contracts/status_list.py`` (``data-dz-status-entry``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="status-list-region",
    root=".dz-status-list-region",
    nodes=(Node(".dz-status-list-region", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
