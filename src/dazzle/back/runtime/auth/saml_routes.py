"""SAML SSO routes (auth Plan 5.ii).

  GET  /auth/saml/login  — resolve the org's SAML connection, redirect to the IdP
  POST /auth/saml/acs    — Assertion Consumer Service: validate the IdP's Response, sign in

Mirrors the OIDC enterprise routes (4b.iii) but SAML's callback is a POST (the IdP POSTs the
signed Response to the ACS). The ACS lives under the ``/auth/`` CSRF-exempt prefix — correct,
because a SAML ACS is an intentional cross-origin POST from the IdP and its integrity rests on
the **signed assertion + InResponseTo** (validated by ``NativeSAMLProvider``), not a CSRF token.

Connection resolution at login: ``?connection=<id>`` · ``?email=`` (verified-domain routing) ·
host-pinned tenant. The connection id is stashed in the session so the single stable ACS URL
can recover it (and ``initiate`` stashes the AuthnRequest id there too — InResponseTo).

ADR-0014: no ``from __future__ import annotations`` in FastAPI route files.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse

from dazzle.back.runtime.auth.connections import ConnectionError, resolve_provider
from dazzle.back.runtime.auth.enterprise_login import (
    EnterpriseLoginError,
    provision_enterprise_login,
)
from dazzle.back.runtime.auth.org_activation import host_tenant_id_from_request
from dazzle.back.runtime.auth.redirect_safety import (
    is_safe_redirect_path as _is_safe_redirect_path,
)
from dazzle.back.runtime.auth.sso_session import finish_login_session

_logger = logging.getLogger(__name__)

_SESSION_CONN_KEY = "saml_conn_id"
_SESSION_NEXT_KEY = "saml_next"


def _resolve_saml_connection(
    store: Any, request: Request, *, connection_id: str, email: str
) -> Any:
    """Resolve the SAML connection to drive this login, or ``None`` (explicit id →
    verified email-domain → host-pinned tenant)."""
    if connection_id:
        return store.get_connection(connection_id)
    if email and "@" in email:
        domain = email.rsplit("@", 1)[-1].strip().lower()
        return store.get_connection_by_verified_domain(domain)
    host_tid = host_tenant_id_from_request(request)
    if host_tid:
        for conn in store.get_connections_for_tenant(host_tid):
            if conn.type == "saml" and conn.status == "active":
                return conn
    return None


def create_saml_routes(*, cookie_name: str = "dazzle_session") -> APIRouter:
    """SAML initiation + ACS endpoints."""
    router = APIRouter(tags=["auth"])

    @router.get("/auth/saml/login")
    async def saml_login(
        request: Request,
        connection: Annotated[str, Query()] = "",
        email: Annotated[str, Query()] = "",
        next: Annotated[str, Query()] = "/",
    ) -> RedirectResponse:
        """Resolve the org's SAML connection and redirect to its IdP."""
        store = request.app.state.auth_store
        conn = _resolve_saml_connection(store, request, connection_id=connection, email=email)
        if conn is None or conn.type != "saml" or conn.status != "active":
            return RedirectResponse(url="/login?error=sso_no_connection", status_code=303)
        try:
            provider = resolve_provider(conn)
        except ConnectionError:
            return RedirectResponse(url="/login?error=sso_unavailable", status_code=303)

        request.session[_SESSION_CONN_KEY] = conn.id
        if next and _is_safe_redirect_path(next) and next != "/":
            request.session[_SESSION_NEXT_KEY] = next
        else:
            request.session.pop(_SESSION_NEXT_KEY, None)

        try:
            url = await provider.initiate(conn, request)
        except ConnectionError as exc:
            request.session.pop(_SESSION_CONN_KEY, None)
            _logger.warning(  # nosemgrep
                "SAML login: initiate failed for connection %s: %s", conn.id, exc
            )
            return RedirectResponse(url="/login?error=sso_unavailable", status_code=303)
        return RedirectResponse(url=url, status_code=303)

    @router.post("/auth/saml/acs")
    async def saml_acs(request: Request) -> RedirectResponse:
        """Assertion Consumer Service — validate the POSTed SAML Response and sign in."""
        store = request.app.state.auth_store
        conn_id = request.session.pop(_SESSION_CONN_KEY, "") if hasattr(request, "session") else ""
        if not conn_id:
            return RedirectResponse(url="/login?error=sso_failed", status_code=303)
        conn = store.get_connection(conn_id)
        # Re-assert the connection is still an active SAML connection (defense-in-depth
        # + symmetry with the login gate — guards against a connection disabled/retyped
        # between login and the ACS POST).
        if conn is None or conn.type != "saml" or conn.status != "active":
            return RedirectResponse(url="/login?error=sso_failed", status_code=303)

        try:
            provider = resolve_provider(conn)
            asserted = await provider.callback(conn, request)
        except ConnectionError as exc:
            _logger.warning("SAML ACS: validation failed: %s", exc)  # nosemgrep
            return RedirectResponse(url="/login?error=sso_failed", status_code=303)
        except Exception as exc:  # noqa: BLE001 — surface in logs, never 500-leak
            _logger.warning("SAML ACS: response error: %s", exc)
            return RedirectResponse(url="/login?error=sso_failed", status_code=303)

        try:
            user, membership_id = provision_enterprise_login(store, conn, asserted)
        except EnterpriseLoginError as exc:
            _logger.warning("SAML ACS: join refused (%s)", exc.reason)
            return RedirectResponse(url=f"/login?error=sso_{exc.reason}", status_code=303)
        except Exception as exc:  # noqa: BLE001 — surface in logs, never 500-leak
            _logger.warning("SAML ACS: provisioning error: %s", exc)
            return RedirectResponse(url="/login?error=sso_failed", status_code=303)

        next_url = request.session.pop(_SESSION_NEXT_KEY, "") if hasattr(request, "session") else ""
        safe_next = next_url if next_url and _is_safe_redirect_path(next_url) else "/app"
        # Session-fixation defence + cookie minting — shared with the OIDC callback.
        return finish_login_session(
            request, store, user, membership_id, cookie_name=cookie_name, safe_next=safe_next
        )

    @router.get("/auth/saml/metadata")
    async def saml_metadata(request: Request) -> Response:
        """Serve this SP's SAML metadata XML so an IdP can import it instead of an
        operator hand-configuring the ACS URL / entityId / NameID (#1342).

        SP-only + app-level — no connection or IdP config needed; the SP identity
        is the same registered with every IdP. Only mounted when the
        ``auth.enterprise.saml`` capability is active.
        """
        from dazzle.back.runtime.auth.saml_provider import NativeSAMLProvider

        try:
            xml = NativeSAMLProvider().sp_metadata(request)
        except Exception as exc:  # noqa: BLE001 — never 500-leak a stack trace
            _logger.warning("SAML metadata generation failed: %s", exc)  # nosemgrep
            return Response(
                content="SAML SP metadata unavailable",
                status_code=503,
                media_type="text/plain",
            )
        return Response(content=xml, media_type="application/samlmetadata+xml")

    return router
