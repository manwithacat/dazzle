"""HYPERPART: form_errors — form-level validation error summary.

Dual-lock unit is the errors root. Title, list items, and icon are
host-owned. Class ``.dz-form-errors`` is the stable substrate root
(form-chrome CSS; no FragmentRenderer emit yet — server re-renders on
failed submit).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="form_errors",
    root=".dz-form-errors",
    nodes=(Node(".dz-form-errors", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
