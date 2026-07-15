"""HYPERPART: kanban-board — column packing shell for kanban cards.

Dual-lock unit is the board root. Column keys and card children are
host-owned. Class ``.dz-kanban`` is the stable substrate root
(``_emit_kanban_board``). Distinct from the card unit in
``contracts/kanban.py`` (board card dual-lock).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="kanban-board",
    root=".dz-kanban",
    nodes=(Node(".dz-kanban", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
