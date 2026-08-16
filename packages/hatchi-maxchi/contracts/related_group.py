"""HYPERPART: related-group — detail-page related-entity block.

Dual-lock unit is the group root for status_cards / file_list displays
(``.dz-related-group``). Table display composes tabs Hyperpart. Nested
tabs, create rows, and drill links are host-owned.

Leftover-honest catalog (cycle 2185): valid ``?tab=`` rides the
declared tab_id. Leftover junk restores the first declared tab.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="related-group",
    root=".dz-related-group",
    nodes=(Node(".dz-related-group", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
