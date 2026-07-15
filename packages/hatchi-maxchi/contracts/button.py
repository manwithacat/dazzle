"""HYPERPART: button — chromatic CTA control.

Dual-lock unit is the control root. Variant/size/htmx attrs are host-owned.
Gallery and Dazzle substrate both use class ``.dz-button`` (plus
``data-dz-variant`` / ``data-dz-size`` when styled).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="button",
    root=".dz-button",
    nodes=(Node(".dz-button", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
