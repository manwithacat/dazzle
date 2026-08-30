"""Bind JWT Bearer claims onto AuthContext + tenant fence (ADR-0055 PR2).

Cookie sessions never consult Authorization. This module is the Bearer
tail of ``_resolve_auth_context``: claim vs membership vs Host, then
the caller binds RLS / lens the same way as a session.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException

from dazzle.http.runtime.auth.models import AuthContext, MembershipRecord
from dazzle.http.runtime.tenant.guard_wiring import _resolve_tenant_state


def bind_jwt_tenant_context(request: Any, jwt_auth: Any, auth_store: Any) -> AuthContext:
    """Turn a verified JWT into an ``AuthContext`` with a chosen membership.

    Never reads ``X-Tenant-ID`` / query / body. Leftover topology does
    not invent a Host match.
    """
    if not getattr(jwt_auth, "is_authenticated", False):
        return AuthContext()
    user_id = getattr(jwt_auth, "user_id", None)
    if not user_id:
        return AuthContext()
    try:
        uid = UUID(str(user_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Not authenticated") from None
    user = auth_store.get_user_by_id(uid)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    memberships = [
        m
        for m in auth_store.get_memberships_for_identity(str(user.id))
        if getattr(m, "status", None) == "active"
    ]
    claim = getattr(jwt_auth, "tenant_id", None) or None
    chosen = _choose_membership(request, memberships, claim)
    return AuthContext(
        user=user,
        is_authenticated=True,
        roles=list(getattr(user, "roles", None) or []),
        active_membership=chosen,
    )


def _host_accept(request: Any) -> set[str]:
    resolved = getattr(getattr(request, "state", None), "tenant", None)
    if resolved is None or not getattr(resolved, "id", None):
        return set()
    ids = {str(resolved.id)}
    ids.update(str(a) for a in (getattr(resolved, "ancestor_ids", ()) or ()) if a)
    return ids


def _topology(request: Any) -> str:
    cfg = _resolve_tenant_state(request)
    return getattr(cfg, "topology", "") or "" if cfg is not None else ""


def _choose_membership(
    request: Any,
    memberships: list[MembershipRecord],
    claim: str | None,
) -> MembershipRecord | None:
    topology = _topology(request)
    acceptable = _host_accept(request)
    if claim:
        return _membership_for_claim(memberships, claim, topology, acceptable)
    if topology == "provider_subdomain" and acceptable:
        return _membership_for_host(memberships, acceptable)
    return _membership_for_apex(request, memberships)


def _membership_for_claim(
    memberships: list[MembershipRecord],
    claim: str,
    topology: str,
    acceptable: set[str],
) -> MembershipRecord:
    match = next((m for m in memberships if m.tenant_id == claim), None)
    if match is None:
        raise HTTPException(status_code=403, detail="JWT tenant_id is not an active membership")
    if topology == "provider_subdomain" and acceptable and claim not in acceptable:
        raise HTTPException(status_code=403, detail="JWT tenant_id does not match host")
    return match


def _membership_for_host(
    memberships: list[MembershipRecord], acceptable: set[str]
) -> MembershipRecord:
    host_match = next((m for m in memberships if m.tenant_id in acceptable), None)
    if host_match is None:
        raise HTTPException(status_code=403, detail="No membership for host tenant")
    return host_match


def _membership_for_apex(
    request: Any, memberships: list[MembershipRecord]
) -> MembershipRecord | None:
    state = getattr(getattr(request, "app", None), "state", None)
    gated = bool(getattr(state, "memberships_required", False)) if state is not None else False
    if not memberships:
        if gated:
            raise HTTPException(status_code=403, detail="No active membership")
        return None
    if len(memberships) == 1:
        return memberships[0]
    raise HTTPException(status_code=403, detail="JWT missing tenant_id with multiple memberships")
