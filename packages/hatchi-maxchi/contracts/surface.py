"""HYPERPART: surface — top-level page surface chrome.

Dual-lock unit is the surface root. Header/body/footer slots are host-owned.
Class ``.dz-surface`` is the stable substrate root.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="surface",
    root=".dz-surface",
    nodes=(Node(".dz-surface", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
