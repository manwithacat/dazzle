"""Auditor-facing tenancy plane one-liner (ADR-0055 observability)."""

from __future__ import annotations

from typing import Any


def render_tenancy_planes(appspec: Any) -> str:
    """``shared_schema + membership on Practice + topology apex``.

    Isolation, membership root, and hosting topology must not collapse into
    one token. Missing planes stay the honest leftover (``none``).
    """
    isolation = "none"
    tenancy = getattr(appspec, "tenancy", None)
    if tenancy is not None:
        iso = getattr(tenancy, "isolation", None)
        mode = getattr(iso, "mode", None) if iso is not None else None
        isolation = getattr(mode, "value", None) or (str(mode) if mode else "none")

    topology = "none"
    root: str | None = None
    domain = getattr(appspec, "domain", None)
    for entity in getattr(domain, "entities", None) or ():
        if getattr(entity, "is_tenant_root", False) and root is None:
            root = entity.name
        th = getattr(entity, "tenant_host", None)
        if th is not None:
            topology = getattr(th, "topology", None) or "none"
            if root is None:
                root = entity.name

    membership = f"membership on {root}" if root else "no membership root"
    return f"{isolation} + {membership} + topology {topology}"
