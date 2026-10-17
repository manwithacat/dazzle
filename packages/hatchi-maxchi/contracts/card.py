"""HYPERPART: card — bordered surface wrapping content.

Dual-lock unit is the surface root. Slots are ``dz-card-header`` /
``dz-card-body`` / ``dz-card-footer``; token knobs ride ``data-dz-radius`` /
``-border`` / ``-padding`` / ``-shadow`` (only where they differ from the
resting card) and are host-owned. Gallery KPI tiles use ``dz-card`` + content
classes; the substrate ``Card`` emits the same slot classes (#1799).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="card",
    root=".dz-card",
    nodes=(Node(".dz-card", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
