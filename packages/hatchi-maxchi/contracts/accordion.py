"""HYPERPART: accordion — native details group (single-open via name=).

Dual-lock unit is the accordion root. Item open state, panel body, and
shared ``name=`` exclusive-open policy are host-owned. Class
``.dz-accordion`` is the stable substrate root (gallery CSS; no
FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="accordion",
    root=".dz-accordion",
    nodes=(Node(".dz-accordion", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
