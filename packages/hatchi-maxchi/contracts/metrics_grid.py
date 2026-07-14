"""HYPERPART: metrics-grid — responsive packing shell for metric tiles.

Dual-lock unit is the grid root. Tile children and ``data-dz-tile-count``
column math are host-owned. Class ``.dz-metrics-grid`` is the stable
substrate root (``_emit_metrics_grid``). Distinct from the tile unit in
``contracts/metrics.py`` (``data-dz-metric-key``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="metrics-grid",
    root=".dz-metrics-grid",
    nodes=(Node(".dz-metrics-grid", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
