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
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from dazzle.http.runtime.auth.auth_views import (
    SELECT_ORG_ERROR_MESSAGES,
    SELECT_ORG_ERROR_TOKENS,
    leftover_honest_auth_error,
    leftover_honest_auth_token,
)
from dazzle.http.runtime.auth.cookie_name import read_session_id, set_session_cookies
from dazzle.http.runtime.auth.redirect_safety import (
    is_safe_redirect_path,
    leftover_honest_auth_next,
)


def leftover_honest_membership_id(raw: Any) -> str | None:
    """Valid membership token_urlsafe ids ride. Leftover stays put (None).

    Leftover ``membership_id=zzz`` / ``ghost`` on POST
    ``/auth/select-org`` and ``/auth/switch-org`` used to invent
    ``303 /auth/select-org?error=invalid_org`` picker theater
    (store reject → error redirect). ``secrets.token_urlsafe(24)``
    ids ride via leftover_honest_auth_token. Absent / blank is
    first-visit (``""``). Well-formed ids that fail ownership still
    bounce ``invalid_org``. Distinct from leftover auth token echo
    (oral #98) and leftover entity-id query (oral #71). Live
    simple_task ``/auth/select-org``. Cycle 2237.
    """
    return leftover_honest_auth_token(raw)


async def _submit_membership(
    request: Request, membership_id: str, next: str
) -> HTMLResponse | RedirectResponse:
    """Leftover ``membership_id=zzz`` used to invent invalid_org theater."""
    honest = leftover_membership_or_400(membership_id)
    if not isinstance(honest, str):
        return honest
    target = next if next and next != "/" and is_safe_redirect_path(next) else "/app"
    return await _activate_and_redirect(request, honest, target)


def leftover_membership_or_400(raw: Any) -> str | HTMLResponse:
    """Ride a valid membership id or return a stay-put 400.

    Leftover stays put (``Unknown membership``). Absent / blank is
    first-visit (``Membership required``). Callers return the
    HTMLResponse as-is when it is not a str.
    """
    honest = leftover_honest_membership_id(raw)
    if honest is None:
        return HTMLResponse("Unknown membership", status_code=400)
    if not honest:
        return HTMLResponse("Membership required", status_code=400)
    return honest


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
    new_secret = auth_store.regenerate_session_csrf(session_id)
    set_session_cookies(
        response,
        request,
        session_id=session_id,
        csrf_secret=new_secret,
        user_roles=list(getattr(ctx, "effective_roles", None) or getattr(ctx, "roles", None) or []),
    )
    return response


def create_org_context_routes() -> APIRouter:
    router = APIRouter(tags=["auth"])

    @router.get("/auth/select-org", response_class=HTMLResponse, include_in_schema=False)
    async def select_org_page(
        request: Request,
        next: Annotated[str, Query()] = "/app",
        error: Annotated[str, Query()] = "",
    ) -> Response:
        from dazzle.http.runtime.auth.org_context_views import build_select_org_view
        from dazzle.render.fragment.renderer import FragmentRenderer

        honest_error = leftover_honest_auth_error(error, SELECT_ORG_ERROR_TOKENS)
        if honest_error is None:
            return HTMLResponse("Unknown org error", status_code=400)
        # Leftover ``?next=zzz`` used to invent ``/app``. Valid
        # same-origin paths ride; absent/blank is first visit.
        honest_next = leftover_honest_auth_next(next)
        if honest_next is None:
            return HTMLResponse("Unknown org next", status_code=400)
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
            next_url=honest_next or "/app",
            error_message=SELECT_ORG_ERROR_MESSAGES.get(honest_error, ""),
        )
        return HTMLResponse(content=FragmentRenderer().render(page))

    @router.post("/auth/select-org", include_in_schema=False, response_model=None)
    async def select_org_submit(
        request: Request,
        membership_id: Annotated[str, Form()] = "",
        next: Annotated[str, Query()] = "/app",
    ) -> HTMLResponse | RedirectResponse:
        return await _submit_membership(request, membership_id, next)

    @router.post("/auth/switch-org", include_in_schema=False, response_model=None)
    async def switch_org_submit(
        request: Request,
        membership_id: Annotated[str, Form()] = "",
        next: Annotated[str, Query()] = "/app",
    ) -> HTMLResponse | RedirectResponse:
        return await _submit_membership(request, membership_id, next)

    @router.get("/auth/no-orgs", response_class=HTMLResponse, include_in_schema=False)
    async def no_orgs_page(request: Request) -> str:
        from dazzle.http.runtime.auth.org_context_views import build_no_orgs_view
        from dazzle.render.fragment.renderer import FragmentRenderer

        return FragmentRenderer().render(build_no_orgs_view(product_name=_product_name(request)))

    return router
