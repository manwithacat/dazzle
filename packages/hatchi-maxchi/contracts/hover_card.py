"""HYPERPART: hover-card — rich preview on hover/focus.

Dual-lock unit is the card root. Trigger chrome and tooltip body are
host-owned. Class ``.dz-hover-card`` is the stable substrate root
(gallery CSS :hover/:focus-within; no FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="hover-card",
    root=".dz-hover-card",
    nodes=(Node(".dz-hover-card", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
