"""HYPERPART: aspect-ratio — media frame that locks width/height.

Dual-lock unit is the frame root. ``data-dz-ratio`` presets and child
fill (object-fit) are host-owned. Class ``.dz-aspect-ratio`` is the stable
substrate root (gallery CSS; no FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="aspect-ratio",
    root=".dz-aspect-ratio",
    nodes=(Node(".dz-aspect-ratio", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
