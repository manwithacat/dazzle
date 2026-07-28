"""HYPERPART: kanban-region — full workspace kanban board shell.

Dual-lock unit is the board region root. Columns, cards, and overflow chrome
are host-owned. Class ``.dz-kanban-board`` is the stable substrate root
(``_emit_kanban_region``). Distinct from the simplified packing shell
``.dz-kanban`` (``_emit_kanban_board``) and the card unit in
``contracts/kanban.py``.

When the host enables Linear-class rearrange, the board also carries
``data-dz-kanban-board`` + rearrange attrs; those are optional host chrome
and are not dual-lock-required (read-only boards omit them).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="kanban-region",
    root=".dz-kanban-board",
    nodes=(Node(".dz-kanban-board", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
