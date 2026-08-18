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
    leftover_honest_scim_body_display_name,
    leftover_honest_scim_body_external_id,
    leftover_honest_scim_body_members,
    leftover_scim_display_name_stay_put,
    leftover_scim_external_id_stay_put,
    leftover_scim_members_stay_put,
    provision_scim_user,
    set_scim_user_active,
)
from dazzle.http.runtime.mailbox_shape import is_mailbox_shape

_logger = logging.getLogger(__name__)

_SCIM_MEDIA = "application/scim+json"
_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
_GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"
_PATCH_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
_LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
_ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"

# Leftover ``schemas: "zzz"`` / ``["ghost"]`` must not invent a provision.
# Linear URN shape — no overlapping quantifiers (oral #106).
_SCIM_SCHEMA_URN = re.compile(
    r"\Aurn:ietf:params:scim:(?:schemas|api:messages):[A-Za-z0-9:._-]{3,200}\Z"
)

# Okta/Entra provisioning sends ``attr eq "value"`` (Users: userName; Groups:
# displayName). Full-string match — a leftover prefix/suffix is not a filter.
_SCIM_EQ_FILTER = re.compile(
    r'\A(?P<attr>userName|displayName)\s+eq\s+"(?P<value>[^"]+)"\Z',
    re.IGNORECASE,
)

# SCIM User.userName is the mailbox here (membership email). Same
# leftover-honest shape as leftover_honest_filter_email /
# leftover_honest_auth_email — linear helper, not the overlapping
# ``[^@\s]+@[^@\s]+\.[^@\s]+`` regex (CodeQL #227).


def leftover_honest_scim_eq_value(raw: Any, *, attr: str) -> str | None:
    """Valid SCIM ``attr eq "value"`` filters ride. Leftover junk restores None.

    Leftover ``?filter=zzz`` / ``ghost`` / unquoted / wrong-attr on
    ``/scim/v2/Users`` and ``/scim/v2/Groups`` used to miss the
    displayName/userName-eq regex and invent the unfiltered list.
    Valid quoted ``eq`` for ``attr`` rides (the quoted value).
    Absent / blank is the honest first-visit default (``""`` —
    list all). Rest is stay-put (None → 400 ``invalidFilter``).
    RFC 7644 §3.4.2.2. Distinct from leftover REST ``filter[key]``
    (oral #74 / #85). Live SCIM Groups + Users. Cycle 2227.
    """
    text = "" if raw is None else str(raw).strip()
    if not text:
        return ""
    match = _SCIM_EQ_FILTER.fullmatch(text)
    if match is None:
        return None
    if match.group("attr").lower() != attr.lower():
        return None
    value = match.group("value").strip()
    if not value:
        return None
    return value


def leftover_honest_scim_username(raw: Any) -> str | None:
    """Valid SCIM ``userName`` emails ride. Leftover junk restores None.

    Leftover ``userName: "zzz"`` / ``ghost`` / list / dict on POST
    ``/scim/v2/Users`` used to miss the mailbox shape and either crash
    on ``.strip()`` (non-string) or invent a provision attempt with
    leftover as the mailbox (``domain_not_verified`` theater). Valid
    emails ride. Absent / blank is the honest first-visit default
    (``""`` → ``no_email``). Rest is stay-put (None → 400
    ``invalidValue``). RFC 7644 §4.1.1. Distinct from leftover
    ``active`` (oral #100) and leftover ``members`` (oral #101).
    Live SCIM Users. Cycle 2230.
    """
    if raw is None:
        return ""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return ""
    if not is_mailbox_shape(text):
        return None
    return text


def leftover_honest_scim_emails(raw: Any) -> str | None:
    """Valid SCIM ``emails[0].value`` ride. Leftover junk restores None.

    Leftover ``emails: "zzz"`` / ``[{}]`` used to crash
    (``"zzz"[0].get`` / ``IndexError`` on ``[]``) or invent empty.
    Valid ``[{"value": "ada@acme.test"}]`` ride. Empty list is
    absent (``""``). Rest is stay-put (None).
    """
    if raw is None:
        return ""
    if not isinstance(raw, list):
        return None
    if not raw:
        return ""
    first = raw[0]
    if not isinstance(first, dict) or "value" not in first:
        return None
    return leftover_honest_scim_username(first.get("value"))


def leftover_honest_scim_body_username(body: dict[str, Any]) -> str | None:
    """POST ``userName`` / ``emails[0].value``. Missing key defaults ``""``.

    Leftover restores None. Blank ``userName`` still falls through to
    ``emails`` (the historic ``or``-chain).
    """
    if "userName" in body:
        honest = leftover_honest_scim_username(body.get("userName"))
        if honest is None or honest:
            return honest
    if "emails" in body:
        return leftover_honest_scim_emails(body.get("emails"))
    return ""


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


# PATCH with no ``active`` op — distinct from leftover ``active`` (None).
_SCIM_ACTIVE_ABSENT = object()


def leftover_honest_scim_active(raw: Any) -> bool | None:
    """Valid SCIM ``active`` tokens ride. Leftover junk restores None.

    Leftover ``active: "zzz"`` / ``ghost`` on POST/PUT ``/scim/v2/Users``
    missed the bool / ``true``/``false`` coerce and invented inactive
    via ``bool(None)``. Leftover PATCH invented a 200 no-op. Valid
    bools and Entra string ``true``/``false`` ride. Absent key is the
    caller's default (create=True). Rest is stay-put (None → 400
    ``invalidValue``). RFC 7644 §3.3. Distinct from leftover consent
    bool (oral #90) and leftover GET ``?filter=`` (oral #99). Live
    SCIM Users. Cycle 2228.
    """
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str) and raw.strip().lower() in ("true", "false"):
        return raw.strip().lower() == "true"
    return None


def leftover_honest_scim_body_active(body: dict[str, Any]) -> bool | None:
    """POST/PUT ``active``. Missing key defaults True. Leftover restores None."""
    if "active" not in body:
        return True
    return leftover_honest_scim_active(body.get("active"))


def leftover_honest_scim_operations(raw: Any) -> list[dict[str, Any]] | None:
    """Valid SCIM PatchOp ``Operations`` lists ride. Leftover junk restores None.

    Leftover ``Operations: "zzz"`` / ``ghost`` / dict / int on PATCH
    ``/scim/v2/Users/{id}`` used to iterate a non-list and crash
    (``str.get`` → 500). The same leftover on Groups PATCH invented
    a 200 no-op (``parse_group_patch`` treated non-list as empty).
    Valid ``[{"op": "replace", ...}]`` ride. Absent / empty list is
    the honest first-visit default (``[]`` — no-op). Rest is
    stay-put (None → 400 ``invalidSyntax``). RFC 7644 §3.5.2.
    Distinct from leftover ``members`` (oral #101) and leftover
    ``active`` (oral #100). Live SCIM Users + Groups. Cycle 2231.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        return None
    out: list[dict[str, Any]] = []
    for op in raw:
        if not isinstance(op, dict):
            return None
        out.append(op)
    return out


def leftover_honest_scim_body_operations(body: dict[str, Any]) -> list[dict[str, Any]] | None:
    """PATCH ``Operations``. Missing key defaults empty. Leftover restores None."""
    if "Operations" not in body:
        return []
    return leftover_honest_scim_operations(body.get("Operations"))


def leftover_scim_operations_stay_put(body: dict[str, Any]) -> bool:
    """True when leftover PATCH ``Operations`` would invent a 500 or a 200 no-op."""
    return leftover_honest_scim_body_operations(body) is None


def leftover_honest_scim_schemas(raw: Any, *, required: str) -> list[str] | None:
    """Valid SCIM ``schemas`` lists that include ``required`` ride. Leftover restores None.

    Leftover ``schemas: "zzz"`` / ``ghost`` / ``["zzz"]`` / dict / int on
    POST/PUT ``/scim/v2/Users`` and ``/scim/v2/Groups`` used to miss the
    schema-URN list and invent a provision (the field was ignored). The
    same leftover on PATCH invented a 200 no-op or a write. Valid lists
    that include ``required`` ride. Absent / empty is the honest
    first-visit default (``[]`` — omit, current writers still work).
    Rest is stay-put (None → 400 ``invalidSyntax``). RFC 7644 §3.3.
    Distinct from leftover ``Operations`` (oral #103) and leftover
    ``externalId`` (oral #111). Live SCIM Users + Groups. Cycle 2244.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        return None
    if not raw:
        return []
    out: list[str] = []
    for item in raw:
        if type(item) is not str:
            return None
        text = item.strip()
        if not text or _SCIM_SCHEMA_URN.fullmatch(text) is None:
            return None
        out.append(text)
    if required not in out:
        return None
    return out


def leftover_honest_scim_body_schemas(body: dict[str, Any], *, required: str) -> list[str] | None:
    """POST/PUT/PATCH ``schemas``. Missing key defaults ``[]``. Leftover restores None."""
    if "schemas" not in body:
        return []
    return leftover_honest_scim_schemas(body.get("schemas"), required=required)


def _coerce_active(value: Any) -> bool | None:
    """SCIM clients send ``active`` as a bool or (Entra) a string. Returns the bool, or
    ``None`` if the value isn't a recognizable active flag."""
    return leftover_honest_scim_active(value)


def _active_from_patch(body: dict[str, Any]) -> Any:
    """Extract the target ``active`` value from a SCIM PatchOp body, tolerating both
    ``{"path":"active","value":false}`` and ``{"value":{"active":false}}`` (Entra).

    Returns ``_SCIM_ACTIVE_ABSENT`` when no ``active`` op is present
    (supported subset — return current). Leftover ``active`` is
    ``None`` (stay-put 400). Valid tokens are ``bool``.
    """
    ops = leftover_honest_scim_body_operations(body)
    if ops is None:
        # Leftover Operations invented a 500 via op.get on a string.
        # Route stay-puts first; this is defense in depth.
        return None
    for op in ops:
        if str(op.get("op", "")).lower() not in ("replace", "add"):
            continue
        path = str(op.get("path", "")).lower()
        value = op.get("value")
        if path == "active":
            return leftover_honest_scim_active(value)
        if isinstance(value, dict) and "active" in value:
            return leftover_honest_scim_active(value["active"])
    return _SCIM_ACTIVE_ABSENT


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
        # Leftover ``schemas: "zzz"`` / ``["ghost"]`` used to invent a
        # provision (ignored envelope). JSONResponse — oral #93.
        # RFC 7644 invalidSyntax.
        if leftover_honest_scim_body_schemas(body, required=_USER_SCHEMA) is None:
            return _error(400, "invalid schemas", scim_type="invalidSyntax")
        # Leftover ``userName: "zzz"`` / ``emails: "zzz"`` used to crash
        # (``.strip()`` / ``"zzz"[0].get``) or invent a provision
        # attempt with leftover as the mailbox. JSONResponse — oral #93.
        email = leftover_honest_scim_body_username(body)
        if email is None:
            return _error(400, "invalid userName", scim_type="invalidValue")
        # Leftover ``active: "zzz"`` used to invent inactive via
        # ``bool(None)``. JSONResponse (not Response(content=)) —
        # oral #93. RFC 7644 invalidValue.
        active = leftover_honest_scim_body_active(body)
        if active is None:
            return _error(400, "invalid active", scim_type="invalidValue")
        # Leftover ``externalId: ["zzz"]`` / dict / int invented a 500
        # via ``.strip()`` or persisted leftover as the IdP id.
        # JSONResponse — oral #93. RFC 7644 invalidValue.
        honest_eid = leftover_honest_scim_body_external_id(body)
        if honest_eid is None:
            return _error(400, "invalid externalId", scim_type="invalidValue")
        try:
            result = provision_scim_user(
                store,
                conn,
                email=email,
                active=active,
                groups=_groups_from_body(body),
                external_id=honest_eid or None,
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
        # Leftover ``?filter=zzz`` used to miss userName-eq and invent
        # the unfiltered Users list. JSONResponse (not Response(content=))
        # — oral #93. RFC 7644 invalidFilter.
        honest = leftover_honest_scim_eq_value(filter, attr="userName")
        if honest is None:
            return _error(400, "invalid filter", scim_type="invalidFilter")
        memberships = store.get_memberships_for_tenant(conn.tenant_id)
        if honest:
            wanted = honest.lower()
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
        # Leftover PUT ``schemas`` invented a replace. Stay put.
        if leftover_honest_scim_body_schemas(body, required=_USER_SCHEMA) is None:
            return _error(400, "invalid schemas", scim_type="invalidSyntax")
        email = _email_for(store, membership.identity_id)  # identity is fixed by the id
        active = leftover_honest_scim_body_active(body)
        if active is None:
            return _error(400, "invalid active", scim_type="invalidValue")
        # Leftover ``externalId`` invented a 500 / persist. Stay put.
        honest_eid = leftover_honest_scim_body_external_id(body)
        if honest_eid is None:
            return _error(400, "invalid externalId", scim_type="invalidValue")
        try:
            provision_scim_user(
                store,
                conn,
                email=email,
                active=active,
                groups=_groups_from_body(body),
                external_id=honest_eid or None,
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
        # Leftover PATCH ``schemas: "zzz"`` invented a 200 no-op / write.
        # JSONResponse — oral #93. RFC 7644 invalidSyntax.
        if leftover_honest_scim_body_schemas(body, required=_PATCH_SCHEMA) is None:
            return _error(400, "invalid schemas", scim_type="invalidSyntax")
        # Leftover ``Operations: "zzz"`` invented a 500 (``str.get``).
        # JSONResponse (not Response(content=)) — oral #93.
        # RFC 7644 invalidSyntax.
        if leftover_scim_operations_stay_put(body):
            return _error(400, "invalid Operations", scim_type="invalidSyntax")
        # Leftover PATCH ``externalId`` invented a 200 no-op (unknown
        # op skipped). Stay put. JSONResponse — oral #93.
        if leftover_scim_external_id_stay_put(body):
            return _error(400, "invalid externalId", scim_type="invalidValue")
        active = _active_from_patch(body)
        if active is _SCIM_ACTIVE_ABSENT:
            # Nothing we act on (only `active` is supported) — return current state.
            return JSONResponse(_render_user(request, store, membership), media_type=_SCIM_MEDIA)
        if active is None:
            # Leftover ``active`` invented a 200 no-op. Stay put.
            return _error(400, "invalid active", scim_type="invalidValue")
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
            "schemas": [_GROUP_SCHEMA],
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
        # Leftover ``schemas: "zzz"`` invented a group persist. Stay put.
        if leftover_honest_scim_body_schemas(body, required=_GROUP_SCHEMA) is None:
            return _error(400, "invalid schemas", scim_type="invalidSyntax")
        # Leftover ``members: "zzz"`` invented an empty group. Valid
        # ``[{"value": id}]`` ride; absent still creates empty.
        # JSONResponse (not Response(content=)) — oral #93.
        member_ids = leftover_honest_scim_body_members(body)
        if member_ids is None:
            return _error(400, "invalid members", scim_type="invalidValue")
        # Leftover ``displayName: ["zzz"]`` / dict / int invented a
        # group persist. JSONResponse — oral #93. RFC 7644 invalidValue.
        display_name = leftover_honest_scim_body_display_name(body)
        if display_name is None:
            return _error(400, "invalid displayName", scim_type="invalidValue")
        # Leftover ``externalId: ["zzz"]`` invented a persist / 500.
        # JSONResponse — oral #93. RFC 7644 invalidValue.
        honest_eid = leftover_honest_scim_body_external_id(body)
        if honest_eid is None:
            return _error(400, "invalid externalId", scim_type="invalidValue")
        try:
            group = sp.create_group(
                store,
                conn,
                display_name,
                member_ids,
                external_id=honest_eid or None,
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
        # Leftover ``?filter=zzz`` used to miss displayName-eq and invent
        # the unfiltered Groups list. JSONResponse (not Response(content=))
        # — oral #93. RFC 7644 invalidFilter.
        honest = leftover_honest_scim_eq_value(
            request.query_params.get("filter", ""), attr="displayName"
        )
        if honest is None:
            return _error(400, "invalid filter", scim_type="invalidFilter")
        groups = sp.list_groups(store, conn, display_name=honest or None)
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
        # Leftover PUT ``schemas`` invented a replace. Stay put.
        if leftover_honest_scim_body_schemas(body, required=_GROUP_SCHEMA) is None:
            return _error(400, "invalid schemas", scim_type="invalidSyntax")
        # PUT is a full replace — displayName is a required Group attribute, so a
        # missing/empty one is a 400 (matches create), not a silent no-op rename.
        # Leftover type invented a rename persist. JSONResponse — oral #93.
        display_name = leftover_honest_scim_body_display_name(body)
        if display_name is None:
            return _error(400, "invalid displayName", scim_type="invalidValue")
        if not display_name:
            return _error(400, "displayName is required", scim_type="invalidValue")
        # Leftover ``members`` invented a wipe. Validate before rename.
        # JSONResponse — oral #93. RFC 7644 invalidValue.
        member_ids = leftover_honest_scim_body_members(body)
        if member_ids is None:
            return _error(400, "invalid members", scim_type="invalidValue")
        # Leftover PUT ``externalId`` invented a persist. Stay put.
        honest_eid = leftover_honest_scim_body_external_id(body)
        if honest_eid is None:
            return _error(400, "invalid externalId", scim_type="invalidValue")
        try:
            sp.rename_group(store, conn, group_id, display_name)
            if "externalId" in body:  # #1342: keep the IdP's stable group id fresh on replace
                store.update_scim_group_external_id(group_id, conn.id, honest_eid or None)
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
        # Leftover PATCH ``schemas: "zzz"`` invented a 200 no-op / write.
        if leftover_honest_scim_body_schemas(body, required=_PATCH_SCHEMA) is None:
            return _error(400, "invalid schemas", scim_type="invalidSyntax")
        # Leftover ``Operations: "zzz"`` invented a 200 no-op
        # (parse_group_patch treated non-list as empty). Stay put.
        # JSONResponse — oral #93. RFC 7644 invalidSyntax.
        if leftover_scim_operations_stay_put(body):
            return _error(400, "invalid Operations", scim_type="invalidSyntax")
        # Leftover PATCH ``members: "zzz"`` invented replace-with-empty
        # (wipe). Stay put. JSONResponse — oral #93.
        if leftover_scim_members_stay_put(body):
            return _error(400, "invalid members", scim_type="invalidValue")
        # Leftover PATCH ``displayName`` invented a rename via ``str()``.
        # Stay put. JSONResponse — oral #93. RFC 7644 invalidValue.
        if leftover_scim_display_name_stay_put(body):
            return _error(400, "invalid displayName", scim_type="invalidValue")
        # Leftover PATCH ``externalId`` invented a 200 no-op. Stay put.
        if leftover_scim_external_id_stay_put(body):
            return _error(400, "invalid externalId", scim_type="invalidValue")
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
