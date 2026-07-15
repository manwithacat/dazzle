"""HYPERPART: chart_legend — shared multi-series chart legend (swatch + name).

Dual-lock unit is the legend list root. Items, swatch colours, series names,
and the optional summary line are host-owned. Class ``.dz-chart-legend`` is
the stable substrate root (gallery CSS; no FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="chart_legend",
    root=".dz-chart-legend",
    nodes=(Node(".dz-chart-legend", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
