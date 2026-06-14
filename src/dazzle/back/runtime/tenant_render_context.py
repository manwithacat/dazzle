"""Render-time `current_tenant` context injection (#1394).

Display gates like ``visible_when: current_tenant.kind == trust`` resolve the
host-resolved tenant from the render context (see
``dazzle.ui.utils.condition_eval``). This helper populates that context from
``request.state.tenant`` (the #1289 ``tenant_host`` ``ResolvedTenant``). Shared
by every context builder so the keys stay consistent.

Defensive by design: any object exposing ``.id`` works (legacy tenant records
included), missing attributes become ``None``, and no host tenant is a no-op —
a gate referencing ``current_tenant`` then simply hides rather than erroring.
"""

from __future__ import annotations

from typing import Any

# The attribute names a `current_tenant.<attr>` reference may read. Mirrors
# `condition_eval._CURRENT_TENANT_ATTRS` and the ResolvedTenant shape.
_TENANT_ATTRS: tuple[str, ...] = ("id", "slug", "kind", "name")


def inject_current_tenant(context: dict[str, Any], request: Any) -> None:
    """Populate ``current_tenant`` on the render context (#1394).

    Bound to the SAME source of truth as the scope path: the host-tenant context
    var set by ``TenantResolutionMiddleware``. If that var is unset (apex /
    non-tenant request, or an app that doesn't use ``tenant_host``), this is a
    no-op — so a ``current_tenant`` display gate HIDES exactly when the matching
    scope predicate would DENY. This prevents the display surface from advertising
    a tenant the data surface can't actually serve.

    The id is taken from the context var (the authoritative scope binding); the
    other attributes (slug/kind/name) come from ``request.state.tenant`` and are
    only used when the var-derived id and the request tenant agree.
    """
    from dazzle.back.runtime.tenant_isolation import get_current_host_tenant_id

    host_tid = get_current_host_tenant_id()
    if not host_tid:
        return
    tenant = getattr(getattr(request, "state", None), "tenant", None)
    # The request tenant must agree with the authoritative scope binding before we
    # expose its attributes — otherwise a middleware mismatch could surface one
    # tenant's slug/kind while scope binds another. On mismatch, expose id only.
    attrs: dict[str, Any] = {"id": host_tid, "slug": None, "kind": None, "name": None}
    if tenant is not None and str(getattr(tenant, "id", None)) == host_tid:
        for name in _TENANT_ATTRS:
            if name == "id":
                continue
            attrs[name] = getattr(tenant, name, None)
    context["current_tenant_id"] = host_tid
    context["current_tenant"] = attrs
