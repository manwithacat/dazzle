"""HYPERPART: breadcrumb — navigation trail with CSS-generated chevrons.

Dual-lock unit is the breadcrumb root. List items, links, and
``aria-current`` page are host-owned. Class ``.dz-breadcrumb`` is the
stable substrate root (gallery partial; no FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="breadcrumb",
    root=".dz-breadcrumb",
    nodes=(Node(".dz-breadcrumb", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
