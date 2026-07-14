"""HYPERPART: message_scroller — chat transcript viewport (scrollable message stack).

Dual-lock unit is the scroller root. Message children, live-region attrs, and
scroll behaviour are host-owned. Class ``.dz-message-scroller`` is the stable
substrate root (gallery CSS; no FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="message_scroller",
    root=".dz-message-scroller",
    nodes=(Node(".dz-message-scroller", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
