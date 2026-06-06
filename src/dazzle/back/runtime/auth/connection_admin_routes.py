"""Org-admin connection surface (auth Plan: in-app connection management).

The in-app, RBAC-gated counterpart to the operator `dazzle auth connection` CLI: an
authenticated org admin manages *their own org's* enterprise connections through the web UI.

Every request runs the same gate as the member-admin surface (3b):
  1. the caller has an ACTIVE membership in their active org whose roles intersect
     ``app.state.org_admin_roles`` (fail-closed ``may_manage_members``);
  2. the target connection belongs to the caller's active org (cross-org guard — the 4a
     fenced ``get_connection(id, tenant_id=org)`` returns None for another org → 404).
The org is always the caller's active membership's tenant_id — never request input.

**Secret-free:** this surface never reads or renders a connection's secret material. It
manages domains (claim + DNS-TXT verify) and shows status only; creating connections (which
needs IdP secrets) stays in the CLI. The POST actions are CSRF-protected (in ``protected_paths``)
— they are authenticated, same-origin mutations, NOT the cross-origin SAML ACS.

ADR-0014: no ``from __future__ import annotations`` in FastAPI route files.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from dazzle.back.runtime.auth.cookie_name import read_session_id


def _product_name(request: Request) -> str:
    sitespec = getattr(request.app.state, "sitespec", None) or {}
    brand = sitespec.get("brand", {}) if isinstance(sitespec, dict) else {}
    return str(brand.get("product_name", "Dazzle"))


def _org_admin_roles(request: Request) -> list[str]:
    return list(getattr(request.app.state, "org_admin_roles", []) or [])


def _back(request: Request) -> Response:
    """HX-Redirect for htmx action buttons, 303 for a plain form post."""
    if request.headers.get("HX-Request") == "true":
        return Response(status_code=204, headers={"HX-Redirect": "/auth/connections"})
    return RedirectResponse(url="/auth/connections", status_code=303)


_DOMAIN_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789.-")


def _normalize_domain(domain: str) -> str:
    return domain.strip().lower().rstrip(".")


def _is_valid_domain(domain: str) -> bool:
    """A conservative hostname check — labels of [a-z0-9-] separated by dots, no
    leading/trailing hyphen. Rejects empties, colons, spaces, schemes (so a stored
    value can never wedge the page's ``URL(...&domain=...)`` rendering)."""
    if not domain or "." not in domain or len(domain) > 253:
        return False
    if any(c not in _DOMAIN_CHARS for c in domain):
        return False
    labels = domain.split(".")
    return all(lbl and not lbl.startswith("-") and not lbl.endswith("-") for lbl in labels)


def create_connection_admin_routes() -> APIRouter:
    router = APIRouter(tags=["auth"])

    def _gate(request: Request) -> tuple[Any, Any, str] | None:
        """Return (store, ctx, org_id) if the caller may manage the org, else None."""
        from dazzle.back.runtime.auth.invitations import may_manage_members
        from dazzle.back.runtime.auth.models import effective_roles_of

        store = request.app.state.auth_store
        session_id = read_session_id(request)
        ctx = store.validate_session(session_id) if session_id else None
        if ctx is None or not ctx.is_authenticated or ctx.user is None:
            return None
        if ctx.active_membership is None:
            return None
        if not may_manage_members(
            list(effective_roles_of(ctx)), org_admin_roles=_org_admin_roles(request)
        ):
            return None
        return store, ctx, ctx.active_membership.tenant_id

    def _resolve_conn(store: Any, org_id: str, connection_id: str) -> Any:
        """The connection IFF it belongs to ``org_id`` (4a fenced getter; cross-org → None)."""
        if not connection_id:
            return None
        return store.get_connection(connection_id, tenant_id=org_id)

    @router.get("/auth/connections", response_class=HTMLResponse, include_in_schema=False)
    async def connections_page(request: Request) -> HTMLResponse:
        from dazzle.back.runtime.auth.connection_admin_views import build_connections_view
        from dazzle.back.runtime.auth.connection_crypto import ConnectionSecretError
        from dazzle.back.runtime.auth.domain_verification import txt_record
        from dazzle.render.fragment.renderer import FragmentRenderer

        gated = _gate(request)
        if gated is None:
            return HTMLResponse("Forbidden", status_code=403)
        store, _ctx, org_id = gated

        connections: list[dict[str, Any]] = []
        for conn in store.get_connections_for_tenant(org_id):
            verified = {d.strip().lower() for d in (conn.verified_domains or [])}
            unverified = []
            for domain in conn.domains or []:
                norm = _normalize_domain(domain)
                if norm in verified:
                    continue
                try:
                    txt = txt_record(conn.id, norm)
                except ConnectionSecretError:
                    txt = "(set DAZZLE_CONNECTION_SECRET to compute the record)"
                unverified.append({"domain": norm, "txt": txt})
            connections.append(
                {
                    "id": conn.id,
                    "type": conn.type,
                    "status": conn.status,
                    "verified": sorted(verified),
                    "unverified": unverified,
                    "active_for_sso": bool(verified),
                }
            )

        org = store.get_organization(org_id)
        page = build_connections_view(
            product_name=_product_name(request),
            org_name=org.name if org is not None else org_id,
            connections=connections,
        )
        return HTMLResponse(FragmentRenderer().render(page))

    @router.post("/auth/connections/add-domain", include_in_schema=False)
    async def add_domain(
        request: Request,
        connection_id: Annotated[str, Query()] = "",
        domain: Annotated[str, Form()] = "",
    ) -> Response:
        gated = _gate(request)
        if gated is None:
            return HTMLResponse("Forbidden", status_code=403)
        store, _ctx, org_id = gated
        conn = _resolve_conn(store, org_id, connection_id)
        if conn is None:
            return HTMLResponse("Not found", status_code=404)
        norm = _normalize_domain(domain)
        if not _is_valid_domain(norm):
            return HTMLResponse("A valid domain is required", status_code=400)
        store.set_connection_domains(connection_id, sorted({*conn.domains, norm}))
        return _back(request)

    @router.post("/auth/connections/verify-domain", include_in_schema=False)
    async def verify_domain_action(
        request: Request,
        connection_id: Annotated[str, Query()] = "",
        domain: Annotated[str, Query()] = "",
    ) -> Response:
        from dazzle.back.runtime.auth.domain_verification import (
            DnspythonResolver,
            DomainVerificationError,
            verify_domain,
        )

        gated = _gate(request)
        if gated is None:
            return HTMLResponse("Forbidden", status_code=403)
        store, _ctx, org_id = gated
        conn = _resolve_conn(store, org_id, connection_id)
        if conn is None:
            return HTMLResponse("Not found", status_code=404)
        norm = _normalize_domain(domain)
        if not _is_valid_domain(norm):
            return HTMLResponse("A valid domain is required", status_code=400)
        try:
            verify_domain(store, conn, norm, resolver=DnspythonResolver())
        except DomainVerificationError as exc:
            # already_verified_elsewhere — a clean conflict, not a 500.
            return HTMLResponse(str(exc), status_code=409)
        # Whether or not the TXT matched yet, redirect back — the page re-renders showing
        # the domain as verified (success) or still pending (publish the TXT, retry).
        return _back(request)

    return router
