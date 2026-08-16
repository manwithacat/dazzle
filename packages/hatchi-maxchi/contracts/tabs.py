"""HYPERPART: tabs — tablist root + panel targets.

Leftover-honest catalog (cycle 2185): valid ``?tab=`` rides.
Leftover junk (``ghost``, ``zzz``) must not invent the first
declared tab when a later sibling is rest.
"""

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="tabs",
    root="[data-dz-tabs]",
    nodes=(
        Node("[data-dz-tabs]", attrs={}),
        Node("[data-dz-tab-target]", attrs={"data-dz-tab-target": Present()}),
    ),
)

__all__ = ["DOM_CONTRACT"]
