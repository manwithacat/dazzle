"""HYPERPART: two_factor — 2FA enrolment/settings auth card.

Dual-lock unit is the auth-card root. QR container, code input, recovery
grid, and factor status rows are host-owned. Class ``.dz-auth-card`` is the
stable substrate root (gallery CSS / two-factor panel; no FragmentRenderer
emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="two_factor",
    root=".dz-auth-card",
    nodes=(Node(".dz-auth-card", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
