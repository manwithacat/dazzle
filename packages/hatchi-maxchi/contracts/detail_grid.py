"""HYPERPART: detail-grid — label/value definition-list region shell.

Dual-lock unit is the region root. Row labels, value fragments, and
packing layout are host-owned. Class ``.dz-detail-region`` is the stable
substrate root (``_emit_detail_grid``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="detail-grid",
    root=".dz-detail-region",
    nodes=(Node(".dz-detail-region", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
