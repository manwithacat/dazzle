"""HYPERPART: interactive — htmx behaviour wrapper around any fragment.

Dual-lock unit is the wrapper root. HTMX method/target/swap attrs and the
child fragment are host-owned. Class ``.dz-interactive`` is the stable
substrate root (``_emit_interactive``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="interactive",
    root=".dz-interactive",
    nodes=(Node(".dz-interactive", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
