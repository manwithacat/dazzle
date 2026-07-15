"""HYPERPART: queue-region — worklist packing shell for queue rows.

Dual-lock unit is the region root. Count/metrics chrome, filter bar, and
row children are host-owned. Class ``.dz-queue-region`` is the stable
substrate root (``_emit_queue_region``). Distinct from the row unit in
``contracts/queue.py`` (``data-dz-queue-row``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="queue-region",
    root=".dz-queue-region",
    nodes=(Node(".dz-queue-region", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
