"""HYPERPART: text — inline typed text with tone.

Dual-lock unit is the text span root. Body copy and tone modifiers are
host-owned. Class ``.dz-text`` is the stable substrate root (``_emit_text``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="text",
    root=".dz-text",
    nodes=(Node(".dz-text", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
