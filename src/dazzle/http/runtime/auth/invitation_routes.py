"""Org invitation routes (auth Plan 3a): invite / accept.

``POST /auth/invite``                — an org admin invites email+roles into their
                                        active org (authz: ``manage_members`` capability)
``GET  /auth/accept-invite/{token}``  — accept page (verified-email gated on POST)
``POST /auth/accept-invite?token=..`` — redeem token → active membership + activate

Authz: the inviter must have an ACTIVE membership in their active org whose roles
satisfy the ``manage_members`` capability (``app.state.admin_policy``; fail-closed). The
target org is taken from the inviter's active membership — never from request input. Accept enforces
the verified-email join rule in ``invitations.accept_invitation``.
"""

from typing import Annotated

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from dazzle.http.runtime.auth.cookie_name import read_session_id


def _product_name(request: Request) -> str:
    sitespec = getattr(request.app.state, "sitespec", None) or {}
    brand = sitespec.get("brand", {}) if isinstance(sitespec, dict) else {}
    return str(brand.get("product_name", "Dazzle"))


def _is_wellformed_token(token: str) -> bool:
    """A real invitation token is ``secrets.token_urlsafe`` → ``[A-Za-z0-9_-]``.

    Reject anything else BEFORE it reaches the DB lookup / a ``URL(...)`` (a token
    with a ``:`` would otherwise raise in the Fragment URL scheme check → 500). A
    malformed token is treated as a not-found invitation (fail-closed).
    """
    return bool(token) and len(token) <= 256 and all(c.isalnum() or c in "-_" for c in token)


def create_invitation_routes() -> APIRouter:
    router = APIRouter(tags=["auth"])

    @router.post("/auth/invite", include_in_schema=False)
    async def invite(
        request: Request,
        email: Annotated[str, Form()] = "",
        roles: Annotated[str, Form()] = "",  # comma-separated personas
    ) -> HTMLResponse:
        from dazzle.http.runtime.auth.admin_policy import request_policy
        from dazzle.http.runtime.auth.invitation_views import build_invite_result_view
        from dazzle.http.runtime.auth.invitations import create_invitation
        from dazzle.http.runtime.auth.mailer import get_invitation_mailer
        from dazzle.http.runtime.auth.models import effective_roles_of
        from dazzle.render.fragment.renderer import FragmentRenderer

        store = request.app.state.auth_store
        session_id = read_session_id(request)
        ctx = store.validate_session(session_id) if session_id else None
        if ctx is None or not ctx.is_authenticated or ctx.user is None:
            return HTMLResponse("Forbidden", status_code=403)
        # Org context comes from the ACTIVE membership — never request input.
        if ctx.active_membership is None:
            return HTMLResponse("Forbidden — no active organization", status_code=403)
        if not request_policy(request).may("manage_members", list(effective_roles_of(ctx))):
            return HTMLResponse(
                "Forbidden — you cannot manage members of this organization", status_code=403
            )
        if not email.strip():
            return HTMLResponse("Email required", status_code=400)

        org_id = ctx.active_membership.tenant_id
        role_list = [r.strip() for r in roles.split(",") if r.strip()]
        token = create_invitation(
            store, org_id=org_id, email=email, roles=role_list, invited_by=str(ctx.user.id)
        )
        org = store.get_organization(org_id)
        org_name = org.name if org is not None else org_id
        accept_url = f"{str(request.base_url).rstrip('/')}/auth/accept-invite/{token}"
        get_invitation_mailer(request.app.state).send_invitation(
            to_email=email.strip().lower(), accept_url=accept_url, org_name=org_name
        )
        return HTMLResponse(
            FragmentRenderer().render(
                build_invite_result_view(
                    product_name=_product_name(request),
                    message=f"Invitation sent to {email.strip().lower()}.",
                )
            )
        )

    @router.get("/auth/accept-invite/{token}", response_class=HTMLResponse, include_in_schema=False)
    async def accept_page(request: Request, token: str) -> str:
        from dazzle.http.runtime.auth.invitation_views import (
            build_accept_invite_view,
            build_invite_result_view,
        )
        from dazzle.http.runtime.auth.invitations import get_invitation
        from dazzle.render.fragment.renderer import FragmentRenderer

        store = request.app.state.auth_store
        # Malformed / not-found / used → a token-free invalid page (never embed an
        # untrusted token into a URL — a `:` would 500 the Fragment URL builder).
        if not _is_wellformed_token(token):
            return FragmentRenderer().render(
                build_invite_result_view(
                    product_name=_product_name(request), message="This invitation link is invalid."
                )
            )
        inv = get_invitation(store, token)
        if inv is None or inv.accepted_at is not None:
            return FragmentRenderer().render(
                build_invite_result_view(
                    product_name=_product_name(request),
                    message="This invitation is invalid or has already been used.",
                )
            )
        session_id = read_session_id(request)
        ctx = store.validate_session(session_id) if session_id else None
        signed_in_email = (
            ctx.user.email if ctx is not None and ctx.is_authenticated and ctx.user else None
        )
        org = store.get_organization(inv.org_id)
        return FragmentRenderer().render(
            build_accept_invite_view(
                product_name=_product_name(request),
                org_name=org.name if org is not None else inv.org_id,
                roles=inv.roles,
                token=token,
                signed_in_email=signed_in_email,
            )
        )

    @router.post("/auth/accept-invite", include_in_schema=False, response_model=None)
    async def accept_submit(
        request: Request, token: Annotated[str, Query()] = ""
    ) -> HTMLResponse | RedirectResponse:
        from dazzle.http.runtime.auth.crypto import cookie_secure
        from dazzle.http.runtime.auth.invitations import InvitationError, accept_invitation

        store = request.app.state.auth_store
        if not _is_wellformed_token(token):
            return HTMLResponse("Cannot accept invitation: invalid token", status_code=400)
        session_id = read_session_id(request)
        ctx = store.validate_session(session_id) if session_id else None
        if ctx is None or not ctx.is_authenticated or ctx.user is None:
            return RedirectResponse(url=f"/login?next=/auth/accept-invite/{token}", status_code=303)
        try:
            membership = accept_invitation(
                store,
                token,
                identity_id=str(ctx.user.id),
                accepting_email=ctx.user.email,
                email_verified=bool(getattr(ctx.user, "email_verified", False)),
            )
        except InvitationError as exc:
            return HTMLResponse(f"Cannot accept invitation: {exc.reason}", status_code=400)
        # Activate the new membership (+ CSRF rotation), then land in the app.
        store.set_session_active_membership(session_id, membership.id, identity_id=str(ctx.user.id))
        response = RedirectResponse(url="/app", status_code=303)
        new_secret = store.regenerate_session_csrf(session_id)
        response.set_cookie(
            key="dazzle_csrf",
            value=new_secret,
            httponly=False,
            secure=cookie_secure(request),
            samesite="lax",
        )
        return response

    return router
