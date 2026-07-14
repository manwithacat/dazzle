"""HYPERPART: topbar — application header chrome.

Dual-lock unit is the bar root. Leading/title/trailing slots and optional
sidebar toggle are host-owned. Class ``.dz-topbar`` is the stable substrate
root (see app-shell.css).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="topbar",
    root=".dz-topbar",
    nodes=(Node(".dz-topbar", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
