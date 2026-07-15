"""HYPERPART: kpi — compact KPI label/value tile.

Dual-lock unit is the tile root. Trend modifiers, delta text, and packing
layout are host-owned. Class ``.dz-kpi`` is the stable substrate root
(``_emit_kpi``). Distinct from metrics metric-tile (``data-dz-metric-key``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="kpi",
    root=".dz-kpi",
    nodes=(Node(".dz-kpi", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
