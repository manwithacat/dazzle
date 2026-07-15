"""HYPERPART: link — pure navigation anchor.

Dual-lock unit is the anchor root. Href/label and optional new-tab /
data-action attrs are host-owned. Class ``.dz-link`` is the stable
substrate root (``_emit_link``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="link",
    root=".dz-link",
    nodes=(Node(".dz-link", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
