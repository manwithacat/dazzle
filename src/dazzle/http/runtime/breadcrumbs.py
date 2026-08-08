"""
Breadcrumb trail derivation from URL paths.

Compatibility facade — implementation lives in pure ``dazzle.render.breadcrumbs``
so app chrome can mount the HM Breadcrumb fragment without crossing the
render ↛ http layer boundary.
"""

from __future__ import annotations

from dazzle.render.breadcrumbs import (
    Crumb,
    build_breadcrumb_trail,
    build_shell_breadcrumb,
    crumbs_to_breadcrumb,
)

__all__ = [
    "Crumb",
    "build_breadcrumb_trail",
    "build_shell_breadcrumb",
    "crumbs_to_breadcrumb",
]
