"""Member-admin routes (auth Plan 3b): roster + role/suspend/reactivate/remove.

Every mutation runs the same gate:
  1. the caller has an ACTIVE membership in their active org whose roles satisfy the
     ``manage_members`` capability (``app.state.admin_policy``; fail-closed);
  2. the TARGET membership belongs to the caller's active org (cross-org guard —
     a membership_id from another org is rejected, never managed);
  3. the change won't leave the org with zero active admins (orphan guard).
The org is always the caller's active membership's tenant_id — never request input.

Notes: the orphan guard (3) is a point-in-time check (see ``would_orphan_org`` —
concurrent admin-on-admin mutations can race it; atomic re-check is deferred). A
non-last admin who demotes/removes themselves keeps their current session's
active_membership until the next request, when the gate re-validates and locks
them out — self-demotion takes effect on the next request, which is safe.
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from dazzle.back.runtime.auth.cookie_name import read_session_id


def _product_name(request: Request) -> str:
    sitespec = getattr(request.app.state, "sitespec", None) or {}
    brand = sitespec.get("brand", {}) if isinstance(sitespec, dict) else {}
    return str(brand.get("product_name", "Dazzle"))


def _back_to_members(request: Request) -> Response:
    """HX-Redirect for htmx (action buttons), 303 for a plain form post."""
    if request.headers.get("HX-Request") == "true":
        return Response(status_code=204, headers={"HX-Redirect": "/auth/members"})
    return RedirectResponse(url="/auth/members", status_code=303)


def _manage_members_roles(request: Request) -> frozenset[str]:
    """The resolved ``manage_members`` capability persona set (the orphan-guard's admin set)."""
    from dazzle.back.runtime.auth.admin_policy import request_policy

    return request_policy(request).roles_for("manage_members")


def create_member_admin_routes() -> APIRouter:
    router = APIRouter(tags=["auth"])

    def _gate(request: Request) -> tuple[Any, Any, str] | None:
        """Return (store, ctx, org_id) if the caller holds the ``manage_members`` capability."""
        from dazzle.back.runtime.auth.admin_policy import request_policy
        from dazzle.back.runtime.auth.models import effective_roles_of

        store = request.app.state.auth_store
        session_id = read_session_id(request)
        ctx = store.validate_session(session_id) if session_id else None
        if ctx is None or not ctx.is_authenticated or ctx.user is None:
            return None
        if ctx.active_membership is None:
            return None
        if not request_policy(request).may("manage_members", list(effective_roles_of(ctx))):
            return None
        return store, ctx, ctx.active_membership.tenant_id

    def _roster_rows(store: object, org_id: str) -> list[tuple[str, list[str], str]]:
        """(membership_id, roles, status) tuples for the org's current roster."""
        return [
            (m.id, list(m.roles), m.status)
            for m in store.get_memberships_for_tenant(org_id)  # type: ignore[attr-defined]
        ]

    def _resolve_target(store: object, org_id: str, membership_id: str) -> Any | None:
        """The target membership IFF it belongs to ``org_id`` (cross-org guard)."""
        m = store.get_membership(membership_id)  # type: ignore[attr-defined]
        if m is None or m.tenant_id != org_id:
            return None
        return m

    @router.get("/auth/members", response_class=HTMLResponse, include_in_schema=False)
    async def members_page(request: Request) -> HTMLResponse:
        from dazzle.back.runtime.auth.invitations import list_pending_invitations
        from dazzle.back.runtime.auth.member_admin import active_admins
        from dazzle.back.runtime.auth.member_admin_views import build_members_view
        from dazzle.render.fragment.renderer import FragmentRenderer

        gated = _gate(request)
        if gated is None:
            return HTMLResponse("Forbidden", status_code=403)
        store, _ctx, org_id = gated
        roster = _roster_rows(store, org_id)
        admins = set(active_admins(roster, _manage_members_roles(request)))
        last_admin = next(iter(admins)) if len(admins) == 1 else None

        members = []
        for m in store.get_memberships_for_tenant(org_id):
            user = store.get_user_by_id(UUID(m.identity_id))
            members.append(
                {
                    "membership_id": m.id,
                    "email": user.email if user is not None else m.identity_id,
                    "roles": list(m.roles),
                    "status": m.status,
                    "is_last_admin": m.id == last_admin,
                }
            )
        pending = [
            {"email": p.email, "roles": p.roles} for p in list_pending_invitations(store, org_id)
        ]
        org = store.get_organization(org_id)
        page = build_members_view(
            product_name=_product_name(request),
            org_name=org.name if org is not None else org_id,
            members=members,
            pending=pending,
        )
        return HTMLResponse(FragmentRenderer().render(page))

    @router.post("/auth/members/roles", include_in_schema=False)
    async def change_roles(
        request: Request,
        membership_id: Annotated[str, Query()] = "",
        roles: Annotated[str, Form()] = "",
    ) -> Response:
        from dazzle.back.runtime.auth.member_admin import would_orphan_org

        gated = _gate(request)
        if gated is None:
            return HTMLResponse("Forbidden", status_code=403)
        store, ctx, org_id = gated
        if _resolve_target(store, org_id, membership_id) is None:
            return HTMLResponse("Not found", status_code=404)
        new_roles = [r.strip() for r in roles.split(",") if r.strip()]
        if would_orphan_org(
            _roster_rows(store, org_id),
            membership_id,
            new_roles=new_roles,
            admin_roles=_manage_members_roles(request),
        ):
            return HTMLResponse("Cannot demote the last admin", status_code=409)
        store.update_membership_roles(membership_id, new_roles, actor_id=str(ctx.user.id))
        return _back_to_members(request)

    @router.post("/auth/members/suspend", include_in_schema=False)
    async def suspend(request: Request, membership_id: Annotated[str, Query()] = "") -> Response:
        from dazzle.back.runtime.auth.member_admin import would_orphan_org

        gated = _gate(request)
        if gated is None:
            return HTMLResponse("Forbidden", status_code=403)
        store, ctx, org_id = gated
        if _resolve_target(store, org_id, membership_id) is None:
            return HTMLResponse("Not found", status_code=404)
        if would_orphan_org(
            _roster_rows(store, org_id),
            membership_id,
            new_roles=None,
            admin_roles=_manage_members_roles(request),
        ):
            return HTMLResponse("Cannot suspend the last admin", status_code=409)
        store.suspend_membership(membership_id, actor_id=str(ctx.user.id))
        return _back_to_members(request)

    @router.post("/auth/members/reactivate", include_in_schema=False)
    async def reactivate(request: Request, membership_id: Annotated[str, Query()] = "") -> Response:
        gated = _gate(request)
        if gated is None:
            return HTMLResponse("Forbidden", status_code=403)
        store, ctx, org_id = gated
        if _resolve_target(store, org_id, membership_id) is None:
            return HTMLResponse("Not found", status_code=404)
        store.reactivate_membership(membership_id, actor_id=str(ctx.user.id))
        return _back_to_members(request)

    @router.post("/auth/members/remove", include_in_schema=False)
    async def remove(request: Request, membership_id: Annotated[str, Query()] = "") -> Response:
        from dazzle.back.runtime.auth.member_admin import would_orphan_org

        gated = _gate(request)
        if gated is None:
            return HTMLResponse("Forbidden", status_code=403)
        store, ctx, org_id = gated
        if _resolve_target(store, org_id, membership_id) is None:
            return HTMLResponse("Not found", status_code=404)
        if would_orphan_org(
            _roster_rows(store, org_id),
            membership_id,
            new_roles=None,
            admin_roles=_manage_members_roles(request),
        ):
            return HTMLResponse("Cannot remove the last admin", status_code=409)
        store.remove_membership(membership_id, actor_id=str(ctx.user.id))
        return _back_to_members(request)

    return router
