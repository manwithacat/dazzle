"""HYPERPART: hover-card — rich preview on hover/focus/tap.

Dual-lock unit is the card root. Trigger chrome and tooltip body are
host-owned. Class ``.dz-hover-card`` is the stable substrate root.

Open paths:
  * CSS ``:hover`` / ``:focus-within`` (fine pointers + keyboard)
  * ``data-dz-open`` / gallery ``data-open`` via ``controllers/dz-hover-card.js``
    (click/tap — required on iPadOS Safari where focus/hover do not stick)
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="hover-card",
    root=".dz-hover-card",
    nodes=(Node(".dz-hover-card", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
