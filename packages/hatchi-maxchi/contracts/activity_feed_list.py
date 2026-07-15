"""HYPERPART: activity-feed-list — packing shell for activity rows.

Dual-lock unit is the list root. Row children and empty-state copy are
host-owned. Class ``.dz-activity-feed`` is the stable substrate root
(``_emit_activity_feed``). Distinct from the row unit in
``contracts/activity_feed.py`` (``data-dz-activity-row``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="activity-feed-list",
    root=".dz-activity-feed",
    nodes=(Node(".dz-activity-feed", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
