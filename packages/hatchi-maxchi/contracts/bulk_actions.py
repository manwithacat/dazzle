"""HYPERPART: bulk-actions — list grid bulk-selection toolbar.

Dual-lock unit is the toolbar root. Controller seams
(``data-dz-grid-bulk-action``, ``data-dz-grid-clear``, matching-total mirrors)
are host-owned. Class ``.dz-bulk-actions`` is the stable substrate root.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="bulk-actions",
    root=".dz-bulk-actions",
    nodes=(Node(".dz-bulk-actions", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
