"""HYPERPART: workspace-toolbar — dashboard builder Reset/Save chrome.

Dual-lock unit is the toolbar root. Save-state spans (``data-dz-when``) and
controller bindings are host-owned. Class ``.dz-workspace-toolbar`` is the
stable substrate root.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="workspace-toolbar",
    root=".dz-workspace-toolbar",
    nodes=(Node(".dz-workspace-toolbar", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
