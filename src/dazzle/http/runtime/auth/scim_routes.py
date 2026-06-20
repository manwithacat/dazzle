"""SCIM 2.0 User-provisioning endpoints (auth Plan 4c.ii).

The wire layer over the 4c.i provisioning kernel. An IdP (Okta / Entra ID) presents
a per-connection bearer token and pushes user lifecycle:

  POST   /scim/v2/Users           — create/provision
  GET    /scim/v2/Users/{id}      — read one
  GET    /scim/v2/Users?filter=…  — find by userName (ListResponse)
  PUT    /scim/v2/Users/{id}      — replace (active + groups)
  PATCH  /scim/v2/Users/{id}      — partial update (the `active` toggle)
  DELETE /scim/v2/Users/{id}      — deprovision
  GET    /scim/v2/ServiceProviderConfig — capability discovery
  GET    /scim/v2/ResourceTypes[/{id}]  — resource-type discovery (User, Group)
  GET    /scim/v2/Schemas[/{id}]        — schema discovery (faithful subset)

**A SCIM User resource is a membership** (the identity-in-this-org): its SCIM `id` is
the membership id, `userName` the email, `active` the membership status.

Security: every request is authenticated by its bearer → connection (constant-time,
fail-closed). A connection can only ever see/touch memberships in **its own org**
(`connection.tenant_id`); a `{id}` for another org returns 404 (never leak existence).

ADR-0014: no ``from __future__ import annotations`` in FastAPI route files.
"""

import logging
import re
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response

from dazzle.http.runtime.auth import scim_discovery
from dazzle.http.runtime.auth.scim_provisioning import (
    ScimError,
    deprovision_scim_user,
    provision_scim_user,
    set_scim_user_active,
)

_logger = logging.getLogger(__name__)

_SCIM_MEDIA = "application/scim+json"
_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
_LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
_ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"

# `userName eq "x@y.test"` — the only filter SCIM provisioning actually uses.
_FILTER_RE = re.compile(r'userName\s+eq\s+"([^"]+)"', re.IGNORECASE)


def _error(status: int, detail: str, *, scim_type: str | None = None) -> JSONResponse:
    body: dict[str, Any] = {"schemas": [_ERROR_SCHEMA], "detail": detail, "status": str(status)}
    if scim_type:
        body["scimType"] = scim_type
    return JSONResponse(body, status_code=status, media_type=_SCIM_MEDIA)


async def _json_body(request: Request) -> tuple[dict[str, Any] | None, JSONResponse | None]:
    """Parse a SCIM request body. Returns ``(body, None)`` or ``(None, 400-error)`` —
    a malformed body is a SCIM 400 (``invalidSyntax``), not a generic 500."""
    try:
        body = await request.json()
    except ValueError:  # JSONDecodeError ⊂ ValueError
        return None, _error(400, "request body is not valid JSON", scim_type="invalidSyntax")
    if not isinstance(body, dict):
        return None, _error(400, "request body must be a JSON object", scim_type="invalidSyntax")
    return body, None


def _email_for(store: Any, identity_id: str) -> str:
    try:
        user = store.get_user_by_id(UUID(identity_id))
    except (ValueError, TypeError):
        return ""
    return getattr(user, "email", "") if user is not None else ""


def _render_user(
    request: Request, store: Any, membership: Any, connection: Any = None
) -> dict[str, Any]:
    base = str(request.base_url).rstrip("/")
    out: dict[str, Any] = {
        "schemas": [_USER_SCHEMA],
        "id": membership.id,
        "userName": _email_for(store, membership.identity_id),
        "active": membership.status == "active",
        "meta": {
            "resourceType": "User",
            "location": f"{base}/scim/v2/Users/{membership.id}",
        },
    }
    # #1342 gap 1: round-trip the IdP's stable user id (Entra correlates its directory
    # object to this resource by the externalId it sent).
    if getattr(membership, "external_id", None):
        out["externalId"] = membership.external_id
    # #1342: read-only reflection of the membership's persisted SCIM group
    # memberships (RFC: User.groups is server-managed). Only when we have the
    # connection scope to resolve them.
    if connection is not None:
        names = store.get_member_group_names(membership.id, connection.id)
        out["groups"] = [{"value": n, "display": n, "type": "direct"} for n in names]
    return out


def _coerce_active(value: Any) -> bool | None:
    """SCIM clients send ``active`` as a bool or (Entra) a string. Returns the bool, or
    ``None`` if the value isn't a recognizable active flag."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    return None


def _active_from_patch(body: dict[str, Any]) -> bool | None:
    """Extract the target ``active`` value from a SCIM PatchOp body, tolerating both
    ``{"path":"active","value":false}`` and ``{"value":{"active":false}}`` (Entra)."""
    for op in body.get("Operations", []) or []:
        if str(op.get("op", "")).lower() not in ("replace", "add"):
            continue
        path = str(op.get("path", "")).lower()
        value = op.get("value")
        if path == "active":
            coerced = _coerce_active(value)
            if coerced is not None:
                return coerced
        elif isinstance(value, dict) and "active" in value:
            coerced = _coerce_active(value["active"])
            if coerced is not None:
                return coerced
    return None


def _groups_from_body(body: dict[str, Any]) -> list[str]:
    """Display names from a SCIM ``groups`` array (best-effort; usually empty — group
    membership is normally pushed via the Groups endpoint, deferred)."""
    out: list[str] = []
    for g in body.get("groups", []) or []:
        name = g.get("display") or g.get("value") if isinstance(g, dict) else None
        if name:
            out.append(str(name))
    return out


def _require_scim_connection(request: Request) -> Any:
    """Authenticate the SCIM bearer → its connection, or raise 401. The connection
    pins the org for every operation in the request."""
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="missing SCIM bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = header[7:].strip()
    conn = request.app.state.auth_store.get_scim_connection_by_bearer(token)
    if conn is None:
        raise HTTPException(
            status_code=401,
            detail="invalid SCIM bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return conn


def _membership_in_org(store: Any, membership_id: str, tenant_id: str) -> Any:
    """A membership by id, but only if it belongs to ``tenant_id`` (else None — the
    cross-org isolation gate; callers turn None into a 404)."""
    membership = store.get_membership(membership_id)
    if membership is None or membership.tenant_id != tenant_id:
        return None
    return membership


def create_scim_routes() -> APIRouter:
    """SCIM 2.0 User endpoints (bearer-authenticated, org-scoped)."""
    router = APIRouter(tags=["scim"])

    @router.get("/scim/v2/ServiceProviderConfig")
    async def service_provider_config(request: Request) -> JSONResponse:
        _require_scim_connection(request)
        base = str(request.base_url).rstrip("/")
        return JSONResponse(
            {
                "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
                "patch": {"supported": True},
                "filter": {"supported": True, "maxResults": 200},
                "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
                "changePassword": {"supported": False},
                "sort": {"supported": False},
                "etag": {"supported": False},
                "authenticationSchemes": [
                    {
                        "type": "oauthbearertoken",
                        "name": "OAuth Bearer Token",
                        "description": "Per-connection bearer token",
                    }
                ],
                "meta": {
                    "location": f"{base}/scim/v2/ServiceProviderConfig",
                    "resourceType": "ServiceProviderConfig",
                },
            },
            media_type=_SCIM_MEDIA,
        )

    @router.get("/scim/v2/ResourceTypes")
    async def resource_types(request: Request) -> JSONResponse:
        _require_scim_connection(request)
        base = str(request.base_url).rstrip("/")
        resources = scim_discovery.resource_types(base)
        return JSONResponse(
            {
                "schemas": [_LIST_SCHEMA],
                "totalResults": len(resources),
                "Resources": resources,
                "itemsPerPage": len(resources),
                "startIndex": 1,
            },
            media_type=_SCIM_MEDIA,
        )

    @router.get("/scim/v2/ResourceTypes/{type_id}")
    async def resource_type(type_id: str, request: Request) -> JSONResponse:
        _require_scim_connection(request)
        base = str(request.base_url).rstrip("/")
        rt = scim_discovery.resource_type_by_id(type_id, base)
        if rt is None:
            return _error(404, f"no ResourceType {type_id!r}")
        return JSONResponse(rt, media_type=_SCIM_MEDIA)

    @router.get("/scim/v2/Schemas")
    async def schemas(request: Request) -> JSONResponse:
        _require_scim_connection(request)
        base = str(request.base_url).rstrip("/")
        resources = scim_discovery.all_schemas(base)
        return JSONResponse(
            {
                "schemas": [_LIST_SCHEMA],
                "totalResults": len(resources),
                "Resources": resources,
                "itemsPerPage": len(resources),
                "startIndex": 1,
            },
            media_type=_SCIM_MEDIA,
        )

    @router.get("/scim/v2/Schemas/{schema_id}")
    async def schema(schema_id: str, request: Request) -> JSONResponse:
        _require_scim_connection(request)
        base = str(request.base_url).rstrip("/")
        doc = scim_discovery.schema_by_id(schema_id, base)
        if doc is None:
            return _error(404, f"no Schema {schema_id!r}")
        return JSONResponse(doc, media_type=_SCIM_MEDIA)

    @router.post("/scim/v2/Users")
    async def create_user(request: Request) -> JSONResponse:
        conn = _require_scim_connection(request)
        store = request.app.state.auth_store
        body, err = await _json_body(request)
        if err is not None:
            return err
        assert body is not None
        email = (body.get("userName") or body.get("emails", [{}])[0].get("value") or "").strip()
        active = body.get("active", True)
        active = _coerce_active(active) if not isinstance(active, bool) else active
        try:
            result = provision_scim_user(
                store,
                conn,
                email=email,
                active=bool(active),
                groups=_groups_from_body(body),
                external_id=body.get("externalId"),
            )
        except ScimError as exc:
            status = 400 if exc.reason in ("no_email", "domain_not_verified") else 409
            return _error(status, str(exc), scim_type="invalidValue")
        membership = store.get_membership(result.membership_id)
        return JSONResponse(
            _render_user(request, store, membership), status_code=201, media_type=_SCIM_MEDIA
        )

    @router.get("/scim/v2/Users/{membership_id}")
    async def get_user(request: Request, membership_id: str) -> JSONResponse:
        conn = _require_scim_connection(request)
        store = request.app.state.auth_store
        membership = _membership_in_org(store, membership_id, conn.tenant_id)
        if membership is None:
            return _error(404, "user not found")
        return JSONResponse(_render_user(request, store, membership, conn), media_type=_SCIM_MEDIA)

    @router.get("/scim/v2/Users")
    async def list_users(request: Request, filter: Annotated[str, Query()] = "") -> JSONResponse:
        conn = _require_scim_connection(request)
        store = request.app.state.auth_store
        memberships = store.get_memberships_for_tenant(conn.tenant_id)
        match = _FILTER_RE.search(filter) if filter else None
        if match:
            wanted = match.group(1).strip().lower()
            memberships = [
                m for m in memberships if _email_for(store, m.identity_id).lower() == wanted
            ]
        resources = [_render_user(request, store, m) for m in memberships]
        return JSONResponse(
            {
                "schemas": [_LIST_SCHEMA],
                "totalResults": len(resources),
                "startIndex": 1,
                "itemsPerPage": len(resources),
                "Resources": resources,
            },
            media_type=_SCIM_MEDIA,
        )

    @router.put("/scim/v2/Users/{membership_id}")
    async def replace_user(request: Request, membership_id: str) -> JSONResponse:
        conn = _require_scim_connection(request)
        store = request.app.state.auth_store
        membership = _membership_in_org(store, membership_id, conn.tenant_id)
        if membership is None:
            return _error(404, "user not found")
        body, err = await _json_body(request)
        if err is not None:
            return err
        assert body is not None
        email = _email_for(store, membership.identity_id)  # identity is fixed by the id
        active = body.get("active", True)
        active = _coerce_active(active) if not isinstance(active, bool) else active
        try:
            provision_scim_user(
                store,
                conn,
                email=email,
                active=bool(active),
                groups=_groups_from_body(body),
                external_id=body.get("externalId"),
            )
        except ScimError as exc:
            return _error(400, str(exc), scim_type="invalidValue")
        refreshed = store.get_membership(membership_id)
        return JSONResponse(_render_user(request, store, refreshed), media_type=_SCIM_MEDIA)

    @router.patch("/scim/v2/Users/{membership_id}")
    async def patch_user(request: Request, membership_id: str) -> JSONResponse:
        conn = _require_scim_connection(request)
        store = request.app.state.auth_store
        membership = _membership_in_org(store, membership_id, conn.tenant_id)
        if membership is None:
            return _error(404, "user not found")
        body, err = await _json_body(request)
        if err is not None:
            return err
        assert body is not None
        active = _active_from_patch(body)
        if active is None:
            # Nothing we act on (only `active` is supported) — return current state.
            return JSONResponse(_render_user(request, store, membership), media_type=_SCIM_MEDIA)
        try:
            set_scim_user_active(store, conn, identity_id=membership.identity_id, active=active)
        except ScimError as exc:
            return _error(404, str(exc))
        refreshed = store.get_membership(membership_id)
        return JSONResponse(_render_user(request, store, refreshed), media_type=_SCIM_MEDIA)

    @router.delete("/scim/v2/Users/{membership_id}")
    async def delete_user(request: Request, membership_id: str) -> Response:
        conn = _require_scim_connection(request)
        store = request.app.state.auth_store
        membership = _membership_in_org(store, membership_id, conn.tenant_id)
        if membership is None:
            return _error(404, "user not found")
        deprovision_scim_user(store, conn, identity_id=membership.identity_id)
        return Response(status_code=204)

    # ------------------------------------------------------------------ #
    # SCIM Groups (#1342) — persisted, org-scoped; member changes recompute roles.
    # ------------------------------------------------------------------ #

    def _group_to_scim(group: Any, member_ids: list[str], base: str) -> dict[str, Any]:
        resource = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
            "id": group.id,
            "displayName": group.display_name,
            "members": [
                {"value": mid, "$ref": f"{base}/scim/v2/Users/{mid}"} for mid in member_ids
            ],
            "meta": {
                "resourceType": "Group",
                "location": f"{base}/scim/v2/Groups/{group.id}",
            },
        }
        # Echo the IdP's stable group id (#1342) — Entra reconciles its objectId against it.
        if getattr(group, "external_id", None):
            resource["externalId"] = group.external_id
        return resource

    @router.post("/scim/v2/Groups", status_code=201)
    async def scim_create_group(request: Request) -> Any:
        from dazzle.http.runtime.auth import scim_provisioning as sp

        conn = _require_scim_connection(request)
        store = request.app.state.auth_store
        body, err = await _json_body(request)
        if err is not None:
            return err
        assert body is not None
        member_ids = [m["value"] for m in (body.get("members") or []) if "value" in m]
        try:
            group = sp.create_group(
                store,
                conn,
                body.get("displayName", ""),
                member_ids,
                external_id=body.get("externalId"),  # the Entra group objectId GUID
            )
        except sp.SCIMGroupError as e:
            return _error(e.status, str(e))
        base = str(request.base_url).rstrip("/")
        return _group_to_scim(group, store.get_group_member_ids(group.id), base)

    @router.get("/scim/v2/Groups/{group_id}")
    async def scim_get_group(group_id: str, request: Request) -> Any:
        from dazzle.http.runtime.auth import scim_provisioning as sp

        conn = _require_scim_connection(request)
        store = request.app.state.auth_store
        try:
            group = sp.get_group(store, conn, group_id)
        except sp.SCIMGroupError as e:
            return _error(e.status, str(e))
        base = str(request.base_url).rstrip("/")
        return _group_to_scim(group, store.get_group_member_ids(group_id), base)

    @router.get("/scim/v2/Groups")
    async def scim_list_groups(request: Request) -> Any:
        from dazzle.http.runtime.auth import scim_provisioning as sp

        conn = _require_scim_connection(request)
        store = request.app.state.auth_store
        flt = request.query_params.get("filter", "")
        match = re.search(r'displayName\s+eq\s+"([^"]+)"', flt)
        name = match.group(1) if match else None
        groups = sp.list_groups(store, conn, display_name=name)
        base = str(request.base_url).rstrip("/")
        resources = [_group_to_scim(g, store.get_group_member_ids(g.id), base) for g in groups]
        return {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
            "totalResults": len(resources),
            "Resources": resources,
            "itemsPerPage": len(resources),
            "startIndex": 1,
        }

    @router.put("/scim/v2/Groups/{group_id}")
    async def scim_put_group(group_id: str, request: Request) -> Any:
        from dazzle.http.runtime.auth import scim_provisioning as sp

        conn = _require_scim_connection(request)
        store = request.app.state.auth_store
        body, err = await _json_body(request)
        if err is not None:
            return err
        assert body is not None
        # PUT is a full replace — displayName is a required Group attribute, so a
        # missing/empty one is a 400 (matches create), not a silent no-op rename.
        if not body.get("displayName"):
            return _error(400, "displayName is required", scim_type="invalidValue")
        try:
            sp.rename_group(store, conn, group_id, body["displayName"])
            if "externalId" in body:  # #1342: keep the IdP's stable group id fresh on replace
                store.update_scim_group_external_id(group_id, conn.id, body.get("externalId"))
            member_ids = [m["value"] for m in (body.get("members") or []) if "value" in m]
            sp.set_group_members(store, conn, group_id, member_ids)
            group = sp.get_group(store, conn, group_id)
        except sp.SCIMGroupError as e:
            return _error(e.status, str(e))
        base = str(request.base_url).rstrip("/")
        return _group_to_scim(group, store.get_group_member_ids(group_id), base)

    @router.patch("/scim/v2/Groups/{group_id}")
    async def scim_patch_group(group_id: str, request: Request) -> Any:
        from dazzle.http.runtime.auth import scim_provisioning as sp

        conn = _require_scim_connection(request)
        store = request.app.state.auth_store
        body, err = await _json_body(request)
        if err is not None:
            return err
        assert body is not None
        try:
            sp.get_group(store, conn, group_id)  # 404 if absent / wrong org
            for kind, arg in sp.parse_group_patch(body):
                if kind == "add_members":
                    sp.add_group_members(store, conn, group_id, arg)
                elif kind == "remove_member":
                    sp.remove_group_member(store, conn, group_id, arg)
                elif kind == "replace_members":
                    sp.set_group_members(store, conn, group_id, arg)
                elif kind == "rename":
                    sp.rename_group(store, conn, group_id, arg)
            group = sp.get_group(store, conn, group_id)
        except sp.SCIMGroupError as e:
            return _error(e.status, str(e))
        base = str(request.base_url).rstrip("/")
        return _group_to_scim(group, store.get_group_member_ids(group_id), base)

    @router.delete("/scim/v2/Groups/{group_id}")
    async def scim_delete_group(group_id: str, request: Request) -> Response:
        from dazzle.http.runtime.auth import scim_provisioning as sp

        conn = _require_scim_connection(request)
        store = request.app.state.auth_store
        try:
            sp.delete_group(store, conn, group_id)
        except sp.SCIMGroupError as e:
            return _error(e.status, str(e))
        return Response(status_code=204)

    return router
