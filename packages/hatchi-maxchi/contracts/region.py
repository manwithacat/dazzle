"""HYPERPART: region — workspace region surface shell.

Dual-lock unit is the region root. Kind modifiers, data-table mount, and
entity anchors are host-owned. Class ``.dz-region`` is the stable substrate
root (``_emit_region``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="region",
    root=".dz-region",
    nodes=(Node(".dz-region", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
