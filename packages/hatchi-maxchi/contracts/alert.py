"""HYPERPART: alert — tone-wash feedback surface.

Dual-lock unit is the alert root. Tone (``data-dz-tone``), icon, title, and
description are host-owned. Class ``.dz-alert`` is the stable substrate root
(gallery CSS; no FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="alert",
    root=".dz-alert",
    nodes=(Node(".dz-alert", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
