"""HYPERPART: card-picker — workspace dashboard "Add a card" panel.

Dual-lock unit is the picker root. Catalog JSON and entry buttons are
host-owned (``data-card-catalog``, ``data-dz-add-region``). Class
``.dz-card-picker`` is the stable substrate root.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="card-picker",
    root=".dz-card-picker",
    nodes=(Node(".dz-card-picker", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
