"""HYPERPART: inline-edit — in-place field edit chrome.

Dual-lock unit is the edit span root. Field name, value, and placeholder
are host-owned. Class ``.dz-inline-edit`` is the stable substrate root
(``_emit_inline_edit``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="inline-edit",
    root=".dz-inline-edit",
    nodes=(Node(".dz-inline-edit", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
