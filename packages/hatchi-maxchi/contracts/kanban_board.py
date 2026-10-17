"""HYPERPART: kanban-board — column packing shell for kanban cards.

Dual-lock unit is the board root, marked ``data-dz-kanban``
(``_emit_kanban_board``); the skin is the kanban Hyperpart's
``dz-kanban-board`` / ``dz-kanban-column`` / ``dz-kanban-stack`` (#1799).
Column keys and card children are host-owned. It never carries
``data-dz-kanban-board`` (the rearrange controller's opt-in). Distinct from
the card unit in ``contracts/kanban.py`` (board card dual-lock).
"""

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="kanban-board",
    root="[data-dz-kanban]",
    nodes=(Node("[data-dz-kanban]", attrs={"data-dz-kanban": Present()}),),
)

__all__ = ["DOM_CONTRACT"]
