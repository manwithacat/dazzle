"""HYPERPART: stack — vertical layout group.

Dual-lock unit is the stack root. Gap scale rides ``data-dz-gap``. Child
fragments are host-owned. Class ``.dz-stack`` is the stable substrate root.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="stack",
    root=".dz-stack",
    nodes=(Node(".dz-stack", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
