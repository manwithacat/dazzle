"""HYPERPART: skip-link — a11y skip-to-content control.

Dual-lock unit is the anchor root. Target href and label text are host-owned.
Class ``.dz-skip-link`` is the stable substrate root (visually hidden until
focus).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="skip-link",
    root=".dz-skip-link",
    nodes=(Node(".dz-skip-link", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
