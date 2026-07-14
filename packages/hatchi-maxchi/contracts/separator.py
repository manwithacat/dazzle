"""HYPERPART: separator — hairline divider (horizontal or vertical).

Dual-lock unit is the separator root. Orientation and placement are
host-owned. Class ``.dz-separator`` (and ``.dz-separator--vertical``) is
the stable substrate root (gallery partial; no FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="separator",
    root=".dz-separator, .dz-separator--vertical",
    nodes=(Node(".dz-separator, .dz-separator--vertical", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
