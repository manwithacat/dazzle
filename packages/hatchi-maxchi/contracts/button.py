"""HYPERPART: button — chromatic CTA control.

Dual-lock unit is the control root. Variant/size/htmx attrs are host-owned.
Gallery and Dazzle substrate both use class ``.dz-button`` (plus
``data-dz-variant`` / ``data-dz-size`` when styled).

HM has one secondary look: ``data-dz-variant="secondary"`` is a styled alias of
``outline`` (secondary = outline), same as the Python ``Button(variant="secondary")``
mapping.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="button",
    root=".dz-button",
    nodes=(Node(".dz-button", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
