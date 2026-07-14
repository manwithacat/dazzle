"""HYPERPART: card — bordered surface wrapping content.

Dual-lock unit is the surface root. Header/body/footer slots and BEM
token modifiers (``dz-card--radius-*`` etc.) are host-owned. Gallery KPI
tiles use ``dz-card`` + content classes; substrate ``Card`` emits
``dz-card`` + optional ``dz-card__header|body|footer``.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="card",
    root=".dz-card",
    nodes=(Node(".dz-card", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
