"""HYPERPART: split — two-pane horizontal layout.

Dual-lock unit is the split root. Ratio modifiers and start/end slots are
host-owned. Class ``.dz-split`` is the stable substrate root (``_emit_split``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="split",
    root=".dz-split",
    nodes=(Node(".dz-split", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
