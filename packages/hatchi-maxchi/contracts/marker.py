"""HYPERPART: marker — map pin chrome + optional label.

Dual-lock unit is the marker root. Pin, label, tone, and size are host-owned
(map projection/placement is host CSS). Class ``.dz-marker`` is the stable
substrate root (gallery CSS; no FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="marker",
    root=".dz-marker",
    nodes=(Node(".dz-marker", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
