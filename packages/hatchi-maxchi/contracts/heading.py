"""HYPERPART: heading — typed heading levels.

Dual-lock unit is the heading root. Level and body text are host-owned.
Class ``.dz-heading`` is the stable substrate root (``_emit_heading``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="heading",
    root=".dz-heading",
    nodes=(Node(".dz-heading", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
