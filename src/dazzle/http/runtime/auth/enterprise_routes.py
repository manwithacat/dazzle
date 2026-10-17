"""Enterprise SSO route handlers (auth Plan 4b.iii).

Two endpoints drive per-org enterprise OIDC:

  GET /auth/enterprise/login     — resolve the org's connection, redirect to its IdP
  GET /auth/enterprise/callback  — validate the IdP response, JIT-join, sign in

These mirror ``sso_routes.py`` (session-fixation regen, redirect-safety, CSRF-cookie
binding) but are simpler: ``provision_enterprise_login`` returns the org membership
directly, so there is no org-picker activation step.

Connection resolution at login: an explicit ``?connection=<id>``, else ``?email=`` →
``get_connection_by_verified_domain`` (verified-domain routing — anti-hijack), else the
host-pinned tenant's active OIDC connection. The chosen connection id is stashed in the
session so the single stable callback URL can recover it (one redirect URI per app, which
the IdP admin registers once).

ADR-0014: no ``from __future__ import annotations`` in FastAPI route files.
"""

import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from dazzle.http.runtime.auth.auth_views import (
    leftover_auth_email_or_400,
    leftover_honest_auth_token,
)
from dazzle.http.runtime.auth.connections import (
    AssertedIdentity,
    ConnectionError,
    resolve_provider,
)
from dazzle.http.runtime.auth.enterprise_login import (
    EnterpriseLoginError,
    provision_enterprise_login,
)
from dazzle.http.runtime.auth.leftover_oauth_code import leftover_honest_oauth_code
from dazzle.http.runtime.auth.models import SecondFactorProof
from dazzle.http.runtime.auth.org_activation import host_tenant_id_from_request
from dazzle.http.runtime.auth.redirect_safety import (
    is_safe_redirect_path as _is_safe_redirect_path,
)
from dazzle.http.runtime.auth.sign_in import complete_sign_in
from dazzle.http.runtime.auth.store_two_factor import factor_reference

_logger = logging.getLogger(__name__)

# Session keys carrying state across the IdP round-trip (signed session cookie).
_SESSION_CONN_KEY = "enterprise_conn_id"
_SESSION_NEXT_KEY = "enterprise_next"


def _honest_login_query(email: Any, connection: Any) -> tuple[str, str] | HTMLResponse:
    """Honest ``?email=`` + ``?connection=``: a malformed value stays put (400).

    A valid mailbox / ``secrets.token_urlsafe(24)`` connection id rides; absent or
    blank is the first visit (``""``: email-domain or host-pin routing). A
    well-formed id that misses the store still bounces ``sso_no_connection``.
    """
    honest_email = leftover_auth_email_or_400(email)
    if not isinstance(honest_email, str):
        return honest_email
    honest_conn = leftover_honest_auth_token(connection)
    if honest_conn is None:
        return HTMLResponse("Unknown connection", status_code=400)
    return honest_email, honest_conn


# OIDC ``amr`` values (RFC 8176) that assert a second factor at the IdP.
_MFA_AMR = frozenset({"mfa", "otp", "hwk", "swk"})


def idp_second_factor(asserted: AssertedIdentity, user: Any, conn: Any) -> SecondFactorProof | None:
    """The second factor the IdP asserted for this sign-in (DD-014), or None.

    Read from the signature-checked id_token only: ``amr`` containing ``mfa``, ``otp``,
    ``hwk`` or ``swk`` records ``mfa_method="idp"`` at ``auth_time`` (now when absent),
    and the sign-in is not challenged again locally. UserInfo-endpoint claims are not
    signed, so they never count.
    """
    if asserted.claims_source != "id_token":
        return None
    amr = asserted.attributes.get("amr")
    values = {str(v).lower() for v in amr} if isinstance(amr, list) else set()
    if not values & _MFA_AMR:
        return None
    auth_time = asserted.attributes.get("auth_time")
    verified_at = (
        datetime.fromtimestamp(auth_time, UTC)
        if isinstance(auth_time, int | float) and not isinstance(auth_time, bool)
        else datetime.now(UTC)
    )
    return SecondFactorProof(
        method="idp",
        verified_at=verified_at,
        reference=factor_reference(str(user.id), "idp", str(conn.id)),
    )


def _resolve_connection(store: Any, request: Request, *, connection_id: str, email: str) -> Any:
    """Resolve the OIDC connection to drive this login, or ``None``.

    Order: explicit ``connection_id`` → verified email-domain → host-pinned tenant.
    Email-domain resolution uses ``get_connection_by_verified_domain`` (verified
    domains only — an unverified claimed domain can't route, anti-hijack).
    """
    if connection_id:
        return store.get_connection(connection_id)
    if email and "@" in email:
        domain = email.rsplit("@", 1)[-1].strip().lower()
        return store.get_connection_by_verified_domain(domain, types=("oidc",))
    host_tid = host_tenant_id_from_request(request)
    if host_tid:
        for conn in store.get_connections_for_tenant(host_tid):
            if conn.type == "oidc" and conn.status == "active":
                return conn
    return None


def create_enterprise_sso_routes(*, cookie_name: str = "dazzle_session") -> APIRouter:
    """Enterprise OIDC initiation + callback endpoints."""
    router = APIRouter(tags=["auth"])

    @router.get("/auth/enterprise/login")
    async def enterprise_login(
        request: Request,
        connection: Annotated[str, Query()] = "",
        email: Annotated[str, Query()] = "",
        next: Annotated[str, Query()] = "/",
    ) -> Response:
        """Resolve the org's connection and redirect to its IdP."""
        store = request.app.state.auth_store
        # Leftover ``?email=zzz`` used to invent the host-pinned IdP.
        # Leftover ``?connection=zzz`` used to invent sso_no_connection.
        honest = _honest_login_query(email, connection)
        if not isinstance(honest, tuple):
            return honest
        honest_email, honest_conn = honest
        conn = _resolve_connection(store, request, connection_id=honest_conn, email=honest_email)
        if conn is None or conn.type != "oidc" or conn.status != "active":
            return RedirectResponse(url="/login?error=sso_no_connection", status_code=303)
        try:
            provider = resolve_provider(conn)
        except ConnectionError:
            return RedirectResponse(url="/login?error=sso_unavailable", status_code=303)

        # Stash the connection id + safe next-URL for the (single, stable) callback.
        request.session[_SESSION_CONN_KEY] = conn.id
        if next and _is_safe_redirect_path(next) and next != "/":
            request.session[_SESSION_NEXT_KEY] = next
        else:
            request.session.pop(_SESSION_NEXT_KEY, None)

        try:
            url = await provider.initiate(conn, request)
        except ConnectionError as exc:
            # Don't leave a stale connection stash behind on a failed initiate.
            request.session.pop(_SESSION_CONN_KEY, None)
            _logger.warning(  # nosemgrep
                "enterprise login: initiate failed for connection %s: %s", conn.id, exc
            )
            return RedirectResponse(url="/login?error=sso_unavailable", status_code=303)
        return RedirectResponse(url=url, status_code=303)

    @router.get("/auth/enterprise/callback")
    async def enterprise_callback(request: Request) -> Response:
        """Validate the IdP response, JIT-join the membership, sign in."""
        # Leftover ``?code=zzz`` / ``?state=zzz`` used to invent sso_failed.
        # Stay-put inlined (clone ratchet vs leftover_auth_email_or_400).
        honest_code = leftover_honest_oauth_code(request.query_params.get("code"))
        if honest_code is None:
            return HTMLResponse("Unknown authorization code", status_code=400)
        honest_state = leftover_honest_oauth_code(request.query_params.get("state"))
        if honest_state is None:
            return HTMLResponse("Unknown OAuth state", status_code=400)
        store = request.app.state.auth_store
        conn_id = request.session.pop(_SESSION_CONN_KEY, "") if hasattr(request, "session") else ""
        if not conn_id:
            # No stashed connection — a stray/forged callback or a lost session.
            return RedirectResponse(url="/login?error=sso_failed", status_code=303)
        conn = store.get_connection(conn_id)
        if conn is None:
            return RedirectResponse(url="/login?error=sso_failed", status_code=303)

        try:
            provider = resolve_provider(conn)
            asserted = await provider.callback(conn, request)
        except ConnectionError as exc:
            _logger.warning("enterprise callback: validation failed: %s", exc)  # nosemgrep
            return RedirectResponse(url="/login?error=sso_failed", status_code=303)
        except Exception as exc:  # noqa: BLE001 — surface in logs, never 500-leak
            _logger.warning("enterprise callback: exchange error: %s", exc)
            return RedirectResponse(url="/login?error=sso_failed", status_code=303)

        try:
            user, membership_id = provision_enterprise_login(store, conn, asserted)
        except EnterpriseLoginError as exc:
            # Stable reason code only (no email / secret) — see EnterpriseLoginError.
            _logger.warning("enterprise callback: join refused (%s)", exc.reason)
            return RedirectResponse(url=f"/login?error=sso_{exc.reason}", status_code=303)
        except Exception as exc:  # noqa: BLE001 — surface in logs, never 500-leak
            _logger.warning("enterprise callback: provisioning error: %s", exc)
            return RedirectResponse(url="/login?error=sso_failed", status_code=303)

        next_url = request.session.pop(_SESSION_NEXT_KEY, "") if hasattr(request, "session") else ""
        safe_next = next_url if next_url and _is_safe_redirect_path(next_url) else "/app"
        # The single sign-in completion point (#1804): the IdP join already proved the
        # membership; an IdP-asserted second factor is recorded, else a user with local
        # 2FA is challenged as on any other primary sign-in (DD-014).
        return await complete_sign_in(
            request,
            store,
            user,
            method="enterprise_oidc",
            mode="redirect",
            next_url=safe_next,
            pinned_membership_id=membership_id,
            membership_pinned=True,
            second_factor=idp_second_factor(asserted, user, conn),
            cookie_name=cookie_name,
        )

    return router
