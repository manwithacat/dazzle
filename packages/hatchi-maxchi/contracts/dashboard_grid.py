"""HYPERPART: dashboard-grid — workspace card-grid packing shell.

Dual-lock unit is the grid root. Dashboard cards, SSE connect attrs, and
edit-mode chrome are host-owned. Class ``.dz-dashboard-grid`` is the stable
substrate root (``_emit_dashboard_grid``). Distinct from the card unit in
``contracts/dashboard_card.py`` (``data-dz-dashboard-card``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="dashboard-grid",
    root=".dz-dashboard-grid",
    nodes=(Node(".dz-dashboard-grid", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
