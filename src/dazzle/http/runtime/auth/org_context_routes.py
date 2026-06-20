"""Phase-2 org-context routes (auth Plan 1b): pick / switch / no-orgs.

``GET  /auth/select-org``  — picker (a session with no active membership yet)
``POST /auth/select-org``  — activate one of the identity's memberships
``POST /auth/switch-org``  — rotate the active membership (+ CSRF) without re-auth
``GET  /auth/no-orgs``     — honest "no orgs yet" page

All POSTs are ownership-checked in the store (``set_session_active_membership``).
A successful activation rotates the CSRF secret (privilege change) and re-sets
the ``dazzle_csrf`` cookie; the RLS GUC re-binds on the next request via 1a's
``validate_session`` → ``_bind_rls_tenant_id``.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from dazzle.http.runtime.auth.cookie_name import read_session_id
from dazzle.http.runtime.auth.crypto import cookie_secure
from dazzle.http.runtime.auth.redirect_safety import is_safe_redirect_path


def _product_name(request: Request) -> str:
    sitespec = getattr(request.app.state, "sitespec", None) or {}
    brand = sitespec.get("brand", {}) if isinstance(sitespec, dict) else {}
    return str(brand.get("product_name", "Dazzle"))


async def _activate_and_redirect(
    request: Request, membership_id: str, next_target: str
) -> RedirectResponse:
    """Ownership-checked activation shared by select-org and switch-org.

    Re-validates the session, pins the chosen membership (the store rejects a
    foreign/suspended one), rotates CSRF on success, and 303s to ``next_target``.
    """
    auth_store = request.app.state.auth_store
    session_id = read_session_id(request)
    if not session_id:
        return RedirectResponse(url="/login", status_code=303)
    ctx = auth_store.validate_session(session_id)
    if not ctx.is_authenticated or ctx.user is None:
        return RedirectResponse(url="/login", status_code=303)
    ok = auth_store.set_session_active_membership(
        session_id, membership_id, identity_id=str(ctx.user.id)
    )
    if not ok:
        # Not the user's membership / not active — bounce to the picker.
        return RedirectResponse(url="/auth/select-org?error=invalid_org", status_code=303)
    response = RedirectResponse(url=next_target, status_code=303)
    # Privilege set changed → rotate the CSRF secret and re-issue the cookie.
    new_secret = auth_store.regenerate_session_csrf(session_id)
    response.set_cookie(
        key="dazzle_csrf",
        value=new_secret,
        httponly=False,
        secure=cookie_secure(request),
        samesite="lax",
    )
    return response


def create_org_context_routes() -> APIRouter:
    router = APIRouter(tags=["auth"])

    @router.get("/auth/select-org", response_class=HTMLResponse, include_in_schema=False)
    async def select_org_page(request: Request, next: Annotated[str, Query()] = "/app") -> str:
        from dazzle.http.runtime.auth.org_context_views import build_select_org_view
        from dazzle.render.fragment.renderer import FragmentRenderer

        auth_store = request.app.state.auth_store
        session_id = read_session_id(request)
        ctx = auth_store.validate_session(session_id) if session_id else None
        memberships: tuple[Any, ...] = ()
        if ctx is not None and ctx.is_authenticated and ctx.user is not None:
            memberships = tuple(
                m
                for m in auth_store.get_memberships_for_identity(str(ctx.user.id))
                if m.status == "active"
            )
        page = build_select_org_view(
            product_name=_product_name(request),
            memberships=memberships,
            next_url=next if is_safe_redirect_path(next) else "/app",
        )
        return FragmentRenderer().render(page)

    @router.post("/auth/select-org", include_in_schema=False)
    async def select_org_submit(
        request: Request,
        membership_id: Annotated[str, Form()] = "",
        next: Annotated[str, Query()] = "/app",
    ) -> RedirectResponse:
        target = next if next and next != "/" and is_safe_redirect_path(next) else "/app"
        return await _activate_and_redirect(request, membership_id, target)

    @router.post("/auth/switch-org", include_in_schema=False)
    async def switch_org_submit(
        request: Request,
        membership_id: Annotated[str, Form()] = "",
        next: Annotated[str, Query()] = "/app",
    ) -> RedirectResponse:
        target = next if next and next != "/" and is_safe_redirect_path(next) else "/app"
        return await _activate_and_redirect(request, membership_id, target)

    @router.get("/auth/no-orgs", response_class=HTMLResponse, include_in_schema=False)
    async def no_orgs_page(request: Request) -> str:
        from dazzle.http.runtime.auth.org_context_views import build_no_orgs_view
        from dazzle.render.fragment.renderer import FragmentRenderer

        return FragmentRenderer().render(build_no_orgs_view(product_name=_product_name(request)))

    return router
