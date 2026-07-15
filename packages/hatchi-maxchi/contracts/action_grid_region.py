"""HYPERPART: action-grid-region — packing shell for CTA action cards.

Dual-lock unit is the region root. Card children, empty-state copy, and
grid layout are host-owned. Class ``.dz-action-grid-region`` is the stable
substrate root (``_emit_action_grid``). Distinct from the card unit in
``contracts/action_grid.py`` (``data-dz-action-card``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="action-grid-region",
    root=".dz-action-grid-region",
    nodes=(Node(".dz-action-grid-region", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
