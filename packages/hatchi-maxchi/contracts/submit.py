"""HYPERPART: submit — form submit button.

Dual-lock unit is the button root. Label, variant modifiers, and htmx host
attrs are host-owned. Class ``.dz-submit`` is the stable substrate root
(``_emit_submit``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="submit",
    root=".dz-submit",
    nodes=(Node(".dz-submit", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
