"""HYPERPART: avatar — initials or image; optional stacked groups.

Dual-lock unit is the avatar root. Content, size, and grouping are
host-owned. Class ``.dz-avatar`` is the stable substrate root (gallery
partial; no FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="avatar",
    root=".dz-avatar",
    nodes=(Node(".dz-avatar", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
