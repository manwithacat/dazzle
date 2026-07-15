"""HYPERPART: kbd — keyboard shortcut chip for docs and command chrome.

Dual-lock unit is the kbd root. Glyph content and layout role (adjacent vs
trailing) are host-owned. Class ``.dz-kbd`` is the stable substrate root
(gallery / hm-core; no FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="kbd",
    root=".dz-kbd",
    nodes=(Node(".dz-kbd", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
