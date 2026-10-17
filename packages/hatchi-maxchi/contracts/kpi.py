"""HYPERPART: kpi — compact KPI label/value tile.

Dual-lock unit is the tile root, marked ``data-dz-kpi``. The skin is the
metrics Hyperpart's tile (``dz-metric-tile`` + ``dz-metric-label`` /
``dz-metric-value`` / ``dz-metric-delta``) so a KPI renders styled anywhere,
including inside a card body (#1799). Trend → delta tone/direction, delta
text, and packing layout are host-owned. Distinct from a metrics-region tile,
which carries ``data-dz-metric-key``.
"""

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="kpi",
    root="[data-dz-kpi]",
    nodes=(Node("[data-dz-kpi]", attrs={"data-dz-kpi": Present()}),),
)

__all__ = ["DOM_CONTRACT"]
