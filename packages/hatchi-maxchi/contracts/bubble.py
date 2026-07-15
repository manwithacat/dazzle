"""HYPERPART: bubble — chat bubble content shell (inbound/outbound).

Dual-lock unit is the bubble root. Body copy and ``data-dz-from`` orientation
are host-owned. Class ``.dz-bubble`` is the stable substrate root (gallery CSS;
no FragmentRenderer emit yet). Compose inside message rows for full chat UI.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="bubble",
    root=".dz-bubble",
    nodes=(Node(".dz-bubble", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
