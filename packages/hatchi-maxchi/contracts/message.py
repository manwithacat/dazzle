"""HYPERPART: message — chat message row (media + meta + bubble).

Dual-lock unit is the message root. Author/time, bubble body, and
``data-dz-from`` orientation are host-owned. Class ``.dz-message`` is the
stable substrate root (gallery CSS; no FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="message",
    root=".dz-message",
    nodes=(Node(".dz-message", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
