"""Org-admin connection surface (auth Plan: in-app connection management).

The in-app, RBAC-gated counterpart to the operator `dazzle auth connection` CLI: an
authenticated org admin manages *their own org's* enterprise connections through the web UI.

Every request runs the gate:
  1. the caller has an ACTIVE membership in their active org whose roles satisfy the
     ``manage_connections`` capability (``app.state.admin_policy``; fail-closed). This is the
     technical/IT-admin concern, distinct from ``manage_members``.
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

from dazzle.http.runtime.auth.cookie_name import read_session_id


def _product_name(request: Request) -> str:
    sitespec = getattr(request.app.state, "sitespec", None) or {}
    brand = sitespec.get("brand", {}) if isinstance(sitespec, dict) else {}
    return str(brand.get("product_name", "Dazzle"))


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


_NO_KEY_MSG = (
    "Creating an OIDC or SCIM connection needs DAZZLE_CONNECTION_SECRET set (the at-rest key "
    "for the encrypted secret). Ask your operator to set it, then retry."
)


def _fetch_saml_metadata(metadata_url: str) -> dict[str, str] | None:
    """Fetch + parse IdP metadata from an operator-supplied https URL, or None if none given.

    Reuses the SSRF-guarded ``saml_metadata.fetch_idp_metadata`` (https-only, public-IP-only via
    ``not ip.is_global``, no redirects, size-capped) — the SAME gate the CLI ``create-saml`` uses.
    This IS network I/O on a request path, but it is org-admin-gated and the fetch is SSRF-validated;
    a bad/blocked URL becomes a user-facing 400 (``CreateFormError``), never a 500 or an internal hit.
    """
    from dazzle.http.runtime.auth.connection_create_form import CreateFormError

    if not metadata_url:
        return None
    from dazzle.http.runtime.auth.saml_metadata import (
        SamlMetadataError,
        fetch_idp_metadata,
        parse_idp_metadata_xml,
    )

    try:
        return parse_idp_metadata_xml(fetch_idp_metadata(metadata_url))
    except SamlMetadataError as exc:
        # Surface only the structured, curated `.reason` to the client — not the raw
        # `str(exc)`, which can carry internal fetch/parse detail (CodeQL
        # py/stack-trace-exposure). The full exception is preserved via `from exc`
        # for server-side logging.
        raise CreateFormError(f"IdP metadata import failed: {exc.reason}") from exc


def create_connection_admin_routes() -> APIRouter:
    router = APIRouter(tags=["auth"])

    def _gate(request: Request) -> tuple[Any, Any, str] | None:
        """Return (store, ctx, org_id) if the caller holds the ``manage_connections`` capability,
        else None. Connection management is the technical/IT-admin concern — distinct from member
        management (``manage_members``)."""
        from dazzle.http.runtime.auth.admin_policy import request_policy
        from dazzle.http.runtime.auth.models import effective_roles_of

        store = request.app.state.auth_store
        session_id = read_session_id(request)
        ctx = store.validate_session(session_id) if session_id else None
        if ctx is None or not ctx.is_authenticated or ctx.user is None:
            return None
        if ctx.active_membership is None:
            return None
        if not request_policy(request).may("manage_connections", list(effective_roles_of(ctx))):
            return None
        return store, ctx, ctx.active_membership.tenant_id

    def _resolve_conn(store: Any, org_id: str, connection_id: str) -> Any:
        """The connection IFF it belongs to ``org_id`` (4a fenced getter; cross-org → None)."""
        if not connection_id:
            return None
        return store.get_connection(connection_id, tenant_id=org_id)

    def _render_page(
        request: Request,
        store: Any,
        org_id: str,
        *,
        new_form: str = "",
        scim_bearer_once: str = "",
    ) -> HTMLResponse:
        """Build the org's connections page. Shared by the GET route and the SCIM-create
        response (which renders the minted bearer once). Secret-free except the one-time bearer."""
        from dazzle.http.runtime.auth.connection_admin_views import build_connections_view
        from dazzle.http.runtime.auth.connection_crypto import ConnectionSecretError
        from dazzle.http.runtime.auth.connection_doctor import (
            diagnose_connection,
            environment_flags,
        )
        from dazzle.http.runtime.auth.domain_verification import txt_record
        from dazzle.http.runtime.auth.org_settings import OrgSettings
        from dazzle.render.fragment.renderer import FragmentRenderer

        flags = environment_flags()
        connections: list[dict[str, Any]] = []
        # Only the caller's-org connections are iterated, so every per-connection read
        # below (readiness / events / grace) is org-fenced for free — no cross-org leak.
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
            # Activation readiness — the SAME diagnosis the CLI `doctor` reports (no drift).
            # Secret-free: checks carry presence/detail/remedy, never a secret value.
            try:
                diag = diagnose_connection(
                    conn,
                    secret_key_ok=flags[0],
                    sso_extra_ok=flags[1],
                    dns_extra_ok=flags[2],
                )
                readiness = {
                    "ready": diag.ready,
                    "checks": [
                        {"name": c.name, "ok": c.status == "ok", "detail": c.detail}
                        for c in diag.checks
                        if c.level == "required"
                    ],
                    # Just the failing required remedies (not the full runbook's always-on
                    # OIDC test/redirect steps) — the org admin's "what's left".
                    "next_steps": [
                        c.remedy
                        for c in diag.checks
                        if c.level == "required" and c.status != "ok" and c.remedy
                    ],
                }
            except ConnectionSecretError:
                readiness = {
                    "ready": False,
                    "checks": [],
                    "next_steps": [
                        "The operator must set DAZZLE_CONNECTION_SECRET to assess readiness."
                    ],
                }
            events = [
                {
                    "at": e.at.isoformat() if hasattr(e.at, "isoformat") else str(e.at),
                    "event": e.event,
                    "actor": e.actor or "-",
                    "grace_until": (e.detail or {}).get("grace_until"),
                }
                for e in store.get_connection_secret_events(conn.id, tenant_id=org_id)[:5]
            ]
            grace_active, grace_exp = store.get_connection_grace_status(conn.id, tenant_id=org_id)
            connections.append(
                {
                    "id": conn.id,
                    "type": conn.type,
                    "status": conn.status,
                    "verified": sorted(verified),
                    "unverified": unverified,
                    "active_for_sso": bool(verified),
                    "readiness": readiness,
                    "events": events,
                    "grace": {"active": grace_active, "expires_at": grace_exp},
                }
            )

        org = store.get_organization(org_id)
        org_settings = OrgSettings.from_dict(store.get_org_settings(org_id))
        page = build_connections_view(
            product_name=_product_name(request),
            org_name=org.name if org is not None else org_id,
            connections=connections,
            new_form=new_form if new_form in ("oidc", "scim", "saml", "domain") else "",
            secret_key_ok=flags[0],
            scim_bearer_once=scim_bearer_once,
            base_url=str(request.base_url).rstrip("/"),
            org_settings=org_settings,
        )
        return HTMLResponse(FragmentRenderer().render(page))

    @router.get("/auth/connections", response_class=HTMLResponse, include_in_schema=False)
    async def connections_page(request: Request, new: Annotated[str, Query()] = "") -> HTMLResponse:
        gated = _gate(request)
        if gated is None:
            return HTMLResponse("Forbidden", status_code=403)
        store, _ctx, org_id = gated
        return _render_page(request, store, org_id, new_form=new)

    @router.post("/auth/connections/create", include_in_schema=False)
    async def create_connection_action(
        request: Request, type: Annotated[str, Query()] = ""
    ) -> Response:
        """Create an OIDC/SCIM/SAML connection for the caller's org. Org-fenced (tenant_id is the
        caller's active membership, never input), CSRF-protected, secrets encrypted at rest by
        ``create_connection``. The SCIM bearer is minted here and shown exactly once."""
        import secrets as _secrets

        from dazzle.http.runtime.auth.connection_create_form import (
            CONNECTION_TYPES,
            CreateFormError,
            assemble_saml_config,
            plan_domain,
            plan_oidc,
            plan_saml,
            plan_scim,
        )
        from dazzle.http.runtime.auth.connection_doctor import environment_flags

        gated = _gate(request)
        if gated is None:
            return HTMLResponse("Forbidden", status_code=403)
        store, _ctx, org_id = gated
        if type not in CONNECTION_TYPES:
            return HTMLResponse("Unknown connection type", status_code=400)

        form = await request.form()
        secret_key_ok = environment_flags()[0]
        bearer = ""
        try:
            if type == "oidc":
                if not secret_key_ok:
                    return HTMLResponse(_NO_KEY_MSG, status_code=400)
                plan = plan_oidc(
                    issuer=str(form.get("issuer", "")),
                    client_id=str(form.get("client_id", "")),
                    group_map=str(form.get("group_map", "")),
                )
                client_secret = str(form.get("client_secret", "")).strip()
                if not client_secret:
                    raise CreateFormError("Client secret is required")
                secrets_payload: dict[str, Any] = {"client_secret": client_secret}
            elif type == "scim":
                if not secret_key_ok:
                    return HTMLResponse(_NO_KEY_MSG, status_code=400)
                plan = plan_scim(group_map=str(form.get("group_map", "")))
                bearer = _secrets.token_urlsafe(32)
                secrets_payload = {"scim_bearer": bearer}
            elif type == "domain":
                # Provider-less domain connection — no IdP secrets, no at-rest key required.
                # After creation the existing add-domain / verify-domain actions apply unchanged.
                plan = plan_domain()
                secrets_payload = {}
            else:  # saml — no secret (the IdP signing cert is public)
                # Offload the (bounded, SSRF-guarded) metadata fetch to a thread so a slow IdP
                # can't block the event loop for the full timeout on this async handler.
                from starlette.concurrency import run_in_threadpool

                metadata = await run_in_threadpool(
                    _fetch_saml_metadata, str(form.get("idp_metadata_url", "")).strip()
                )
                config = assemble_saml_config(
                    metadata=metadata,
                    idp_entity_id=str(form.get("idp_entity_id", "")),
                    idp_sso_url=str(form.get("idp_sso_url", "")),
                    idp_x509_cert=str(form.get("idp_x509_cert", "")),
                    email_attribute=str(form.get("email_attribute", "")),
                    groups_attribute=str(form.get("groups_attribute", "")),
                )
                plan = plan_saml(config=config, group_map=str(form.get("group_map", "")))
                secrets_payload = {}
        except CreateFormError as exc:
            # text/plain, not HTML: the message can echo user-supplied input (e.g. a SAML
            # metadata URL/host from the SSRF-reject path) — never reflect it as HTML.
            return Response(str(exc), status_code=400, media_type="text/plain")

        store.create_connection(
            tenant_id=org_id,
            type=plan.type,
            config=plan.config,
            secrets=secrets_payload,
            domains=[],
            group_mapping=plan.group_mapping,
        )
        if plan.show_bearer_once:
            # Render the minted bearer exactly once — no redirect (would lose it), never stored
            # plaintext, never put in a URL.
            return _render_page(request, store, org_id, scim_bearer_once=bearer)
        return _back(request)

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
        from dazzle.http.runtime.auth.domain_verification import (
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

    @router.post("/auth/connections/policy", include_in_schema=False)
    async def update_policy_action(request: Request) -> Response:
        """Persist the org's join-policy settings (domain_join_policy + restrict toggle).

        Gated by ``manage_connections`` (same as every other action on this surface).
        The org_id is always the caller's active membership — never taken from form input.
        Unknown policy values are coerced to ``admin_approval`` via ``OrgSettings.from_dict``.
        """
        from dazzle.http.runtime.auth.org_settings import OrgSettings

        gated = _gate(request)
        if gated is None:
            return HTMLResponse("Forbidden", status_code=403)
        store, _ctx, org_id = gated

        form = await request.form()
        raw_policy = str(form.get("domain_join_policy", ""))
        # HTML checkboxes submit "on" when checked; absent means unchecked.
        restrict = str(form.get("restrict_membership_to_verified_domains", "")).lower() == "on"

        # Validate + coerce via OrgSettings.from_dict (unknown → admin_approval).
        coerced = OrgSettings.from_dict({"domain_join_policy": raw_policy})
        settings = OrgSettings(
            domain_join_policy=coerced.domain_join_policy,
            restrict_membership_to_verified_domains=restrict,
        )
        store.set_org_settings(org_id, settings.to_dict())
        return _back(request)

    return router
