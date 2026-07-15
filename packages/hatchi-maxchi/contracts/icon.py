"""HYPERPART: icon — Lucide SVG icon span.

Dual-lock unit is the icon root. Name/size are host-owned. Class
``.dz-icon`` is the stable substrate root (``_emit_icon`` via
``lucide_icon_html``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="icon",
    root=".dz-icon",
    nodes=(Node(".dz-icon", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
