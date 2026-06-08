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
from typing import Annotated, Any, Protocol, cast

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse

from dazzle.back.runtime.auth.connections import ConnectionError, resolve_provider
from dazzle.back.runtime.auth.cookie_name import names_to_clear
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


class _SamlLogoutProvider(Protocol):
    """The SLO-capable slice of the SAML provider — process_logout is SAML-specific, so it
    is not on the general ConnectionProvider Protocol (OIDC has no SAML logout). The SLS
    route guards ``conn.type == 'saml'`` before casting to this."""

    def process_logout(self, connection: Any, request: Any) -> Any: ...


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
    async def saml_metadata(request: Request, connection: str = "") -> Response:
        """Serve this SP's SAML metadata XML so an IdP can import it instead of an
        operator hand-configuring the ACS URL / entityId / NameID (#1342).

        SP-only + app-level by default. Pass ``?connection=<id>`` to get that connection's
        metadata including its SP signing KeyDescriptor (public cert only) when request
        signing is enabled — re-imported at the IdP so it trusts SP-signed AuthnRequests.
        An unknown id falls back to the app-level metadata (no id-enumeration signal). Only
        mounted when the ``auth.enterprise.saml`` capability is active.
        """
        from dazzle.back.runtime.auth.saml_provider import NativeSAMLProvider

        conn = None
        if connection:
            conn = request.app.state.auth_store.get_connection(connection)
        try:
            xml = NativeSAMLProvider().sp_metadata(request, conn)
        except Exception as exc:  # noqa: BLE001 — never 500-leak a stack trace
            _logger.warning("SAML metadata generation failed: %s", exc)  # nosemgrep
            return Response(
                content="SAML SP metadata unavailable",
                status_code=503,
                media_type="text/plain",
            )
        return Response(content=xml, media_type="application/samlmetadata+xml")

    # HTTP-Redirect binding only (the binding the SP advertises in its metadata SLS): the
    # IdP sends the LogoutRequest as a GET query param. The SAMLRequest is deflate+base64;
    # cap its length BEFORE python3-saml decompresses it (the library inflates with no size
    # limit, before signature validation — a small compressed payload could inflate to GBs
    # and OOM the worker on this unauthenticated endpoint). A real LogoutRequest is ~1-3 KB.
    _MAX_SAML_REQUEST_B64 = 16384

    @router.get("/auth/saml/sls")
    async def saml_sls(request: Request, connection: Annotated[str, Query()] = "") -> Response:
        """SAML Single Logout Service (#1342 A) — process an IdP ``LogoutRequest``
        (signature-verified by the provider) and kill the named user's sessions in the
        connection's org. IdP-initiated SLO; fail-closed — a forged/unsigned request kills
        nothing. Only mounted when the ``auth.enterprise.saml`` capability is active.
        """
        store = request.app.state.auth_store
        if len(request.query_params.get("SAMLRequest", "")) > _MAX_SAML_REQUEST_B64:
            return Response(content="invalid SAML logout", status_code=400, media_type="text/plain")
        conn = _resolve_saml_connection(store, request, connection_id=connection, email="")
        if conn is None or conn.type != "saml" or conn.status != "active":
            return Response(content="invalid SAML logout", status_code=400, media_type="text/plain")
        try:
            provider = cast(_SamlLogoutProvider, resolve_provider(conn))
            result = provider.process_logout(conn, request)
        except ConnectionError as exc:
            _logger.warning("SAML SLS: logout validation failed: %s", exc)  # nosemgrep
            return Response(content="invalid SAML logout", status_code=400, media_type="text/plain")
        except Exception as exc:  # noqa: BLE001 — surface in logs, never 500-leak
            _logger.warning("SAML SLS: logout error: %s", exc)  # nosemgrep
            return Response(content="invalid SAML logout", status_code=400, media_type="text/plain")

        # Org-scoped kill: every session the NameID's user holds in THIS connection's org
        # (only trustworthy because process_logout verified the IdP signature first). The
        # lookups run uniformly whether or not the user/membership exists — no email-existence
        # timing oracle (a known vs unknown NameID takes the same path).
        user = store.get_user_by_email(result.name_id) if result.name_id else None
        memberships = store.get_memberships_for_identity(str(user.id)) if user is not None else []
        for m in memberships:
            if m.tenant_id == conn.tenant_id:
                store.delete_sessions_for_membership(m.id)

        if result.redirect_url:
            response: Response = RedirectResponse(url=result.redirect_url, status_code=303)
        else:
            response = Response(content="logged out", status_code=200, media_type="text/plain")
        # Clear this browser's auth + CSRF cookies (best-effort for the carrier browser).
        for name in names_to_clear(request, default=cookie_name):
            response.delete_cookie(name)
        response.delete_cookie("dazzle_csrf")
        return response

    return router
