"""HYPERPART: item — generic list row (media + title + description + actions).

Dual-lock unit is the item root. Media, content, trailing actions, and
``data-dz-variant`` are host-owned. Class ``.dz-item`` is the stable substrate
root (gallery CSS; no FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="item",
    root=".dz-item",
    nodes=(Node(".dz-item", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
