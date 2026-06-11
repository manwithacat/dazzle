"""Route generator — generates FastAPI route handlers from EndpointSpec.

SECTION MAP (line anchors approximate — use them to jump directly to a
section rather than scanning the 2,700+ lines):

  L 143  Contracts          HandlerConfig, RouteSpec (shared CRUD bundle)
  L 254  Request utils      _is_htmx_request, _wants_html, _forbidden_detail,
                             _htmx_current_url, _htmx_parent_url,
                             _parse_request_body
  L 323  Access helpers     _normalize_role (shared by audit_wrap,
                             scope_filters, workspace builders, list path)
  L 337  List handler       create_list_handler, _list_handler_body,
                             _is_field_condition
  L 941  Read handler       create_read_handler
  L1113  Ref injection      resolve_backed_entity_refs, inject_current_user_refs
  L1248  Write handlers     create_create_handler, create_update_handler,
                             create_delete_handler, create_custom_handler
  L1682  Graph helpers      _materialize_graph, _neighborhood_handler_body,
                             create_neighborhood_handler  (#619 phases 3–4)
  L1925  Graph algorithms   create_shortest_path_handler,
                             create_components_handler  (#619 phase 4)
  L2058  RouteGenerator     Primary class — wires all factories into APIRouter
  L2621  Convenience        generate_crud_routes (thin wrapper)

Scope / row-RBAC filter resolution (Cedar row filters, condition-tree
extraction, _resolve_scope_filters / _resolve_predicate_filters,
_scoped_pre_read, scope: create:/update: enforcement) moved to
scope_filters.py (#1361 slice 1); the names are re-imported above for
back-compat.

Inline HTMX/HTML response rendering (_render_table_row,
_render_table_pagination, _render_inline_edit, _render_cell_display,
_render_table_empty, _render_table_sentinel, _build_table_url_params,
_with_htmx_triggers, _render_detail_html — 500+ lines of inline HTML;
no Jinja2) moved to htmx_render.py (#1361 slice 2); the names are
re-imported above for back-compat.

Audit context + access logging + auth wrapping (_build_access_context,
_record_to_dict, _compute_field_changes, _log_audit_decision,
_SCOPE_DENY_EFFECT, and the _wrap_with_auth → _build_cedar_handler /
_build_auth_handler / _build_noauth_handler family) moved to
audit_wrap.py (#1361 slice 3); the names are re-imported above for
back-compat. NOTE: _scoped_pre_read is resolved through *audit_wrap's*
namespace by the cedar handler — patch it there, not here.

Closes #1066. Section map added to cut agent repeat-reads; introduced
after `scripts/stall_log_mine.py` flagged this file as friction-148
(135 repeat reads, 4-line docstring).
"""

import logging
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, replace
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter as _APIRouter
from fastapi import Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel

# Audit context + access logging + auth wrapping live in audit_wrap.py
# (#1361 slice 3). Same re-import contract as scope_filters / htmx_render
# below: handler-factory call sites in this module plus
# `route_generator.<name>` importers and patch points keep resolving here.
from dazzle.back.runtime.audit_wrap import (  # noqa: F401  (re-exported for back-compat importers)
    _SCOPE_DENY_EFFECT,
    _build_access_context,
    _build_auth_handler,
    _build_cedar_handler,
    _build_noauth_handler,
    _compute_field_changes,
    _json_safe,
    _log_audit_decision,
    _record_to_dict,
    _wrap_with_auth,
)
from dazzle.back.runtime.auth import AuthContext

# Inline HTMX/HTML response rendering lives in htmx_render.py (#1361 slice 2).
# Same re-import contract as scope_filters below: handler call sites in this
# module plus `route_generator.<name>` importers and patch points keep
# resolving here.
from dazzle.back.runtime.htmx_render import (  # noqa: F401  (re-exported for back-compat importers)
    _build_table_url_params,
    _render_cell_display,
    _render_detail_html,
    _render_inline_edit,
    _render_table_empty,
    _render_table_pagination,
    _render_table_row,
    _render_table_sentinel,
    _with_htmx_triggers,
)
from dazzle.back.runtime.repository import ConstraintViolationError

# Scope / row-RBAC filter resolution lives in scope_filters.py (#1361 slice 1).
# The names are re-imported at module level so existing
# `route_generator.<name>` references (handler call sites below, plus tests
# that import or patch.object through this namespace) keep resolving here.
from dazzle.back.runtime.scope_filters import (  # noqa: F401  (re-exported for back-compat importers)
    _build_fk_path_subquery,
    _build_via_subquery,
    _deny_update_destination,
    _enforce_create_scope,
    _enforce_update_scope,
    _extract_cedar_row_filters,
    _extract_condition_filters,
    _LazyUserAttrs,
    _resolve_predicate_filters,
    _resolve_scope_filters,
    _resolve_user_attribute,
    _row_to_payload_dict,
    _scoped_pre_read,
    _should_bypass_tenant_filter,
    build_create_scope_probe,
)
from dazzle.back.specs.endpoint import EndpointSpec, HttpMethod
from dazzle.back.specs.service import OperationKind, ServiceSpec
from dazzle.core.strings import to_api_plural

if TYPE_CHECKING:
    from dazzle.back.runtime.audit_log import AuditLogger
    from dazzle.back.runtime.service_generator import BaseService
    from dazzle.back.specs.auth import EntityAccessSpec
    from dazzle.core.ir.fk_graph import FKGraph

logger = logging.getLogger(__name__)

# Expose APIRouter name for return-type annotations (the real class is
# imported as _APIRouter to allow a None fallback when FastAPI is absent).
APIRouter = _APIRouter


# ---------------------------------------------------------------------------
# HandlerConfig — stable contract for CRUD factory authorization context (#1011)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HandlerConfig:
    """Auth + authz + audit context shared across CRUD route handlers.

    Bundles the six concerns every CRUD route handler factory needs in
    a typed, frozen contract. Replaces the per-factory parameter sprawl
    that drifted across read/create/update/delete signatures (~68 edits
    to this tuple in the 3 months before the refactor; #1011).

    The five auth/authz/identity fields are stable across verbs in a
    single dispatch (sourced from ``self.auth_dep``, ``self.optional_auth_dep``,
    etc. on the route generator). ``audit_logger`` varies per verb —
    construct a base config once per dispatch, then derive per-verb
    instances with ``dataclasses.replace(base, audit_logger=...)``.

    Convergence note: this matches the route-level concerns Django REST
    (ViewSet attributes), Rails (before_action chain), Spring
    (@PreAuthorize), and WordPress (permission_callback) all converge
    on. Naming is local; the shape is universal. Future cross-cutting
    concerns (rate-limit key, idempotency token, throttle policy)
    extend this dataclass rather than the per-factory signatures.

    Composes into :class:`RouteSpec` (the per-route bundle) — see
    that class for the resource/selection/rendering layer that wraps
    HandlerConfig.
    """

    auth_dep: Callable[..., Any] | None = None
    optional_auth_dep: Callable[..., Any] | None = None
    require_auth_by_default: bool = False
    entity_name: str = "Item"
    cedar_access_spec: "EntityAccessSpec | None" = None
    audit_logger: "AuditLogger | None" = None
    # v0.71.19 (#1123): inputs the scope-filter resolver needs at write
    # time so UPDATE/DELETE handlers can enforce `scope: <op>:` rules
    # the same way LIST does. `fk_graph` lets the predicate compiler
    # follow FK-path predicates; `admin_personas` carries the
    # tenancy-admin bypass list (#957 cycle 5). Both come from the
    # active AppSpec at route-construction time — alongside
    # `cedar_access_spec` which is the parsed scope/permit rules.
    fk_graph: "FKGraph | None" = None
    admin_personas: list[str] | None = None


# ---------------------------------------------------------------------------
# RouteSpec — Target 2: per-route bundle (#1011 closeout)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RouteSpec:
    """Stable per-route contract for CRUD handler factories.

    Wraps :class:`HandlerConfig` (auth/authz/audit) with the resource-,
    schema-, and selection-level fields that recur across two or more
    CRUD verb factories. Each factory accepts a single ``RouteSpec``
    and reads its handler config + service + cross-verb extras from it.

    Verb-specific parameters (htmx_columns, fk_graph, search_fields for
    list; user_ref_fields, persona_ref_map for create; etc.) remain as
    keyword arguments to the factories that need them — bundling them
    here would over-fit the abstraction. The principle: a field belongs
    in RouteSpec only when at least two CRUD verbs would consume it.

    Convergence note: this is the Dazzle equivalent of Django REST's
    ViewSet attributes (``queryset``, ``serializer_class``,
    ``permission_classes``), Rails' controller-level filters, or
    Spring's request-mapping metadata. Naming is local; the shape is
    universal — the per-route bundle of "what this endpoint is, who
    can use it, what it returns".

    Distinct from :class:`dazzle_back.specs.endpoint.EndpointSpec`,
    which is the static URL/method/service-name spec one layer above.
    ``RouteSpec`` is the runtime handler bundle: how to actually
    construct the FastAPI handler for the URL that ``EndpointSpec``
    declares.
    """

    handler: HandlerConfig
    """Auth/authz/audit context (see :class:`HandlerConfig`)."""

    service: "BaseService[Any]"
    """The service that backs this endpoint's data operations."""

    # Schemas (per-verb optional; create/update set input_schema)
    input_schema: type[BaseModel] | None = None
    response_schema: type[BaseModel] | None = None

    # Cross-verb resource fields (read + list use auto_include;
    # create + update use storage_bindings; update + delete use
    # include_field_changes)
    auto_include: list[str] | None = None
    storage_bindings: dict[str, tuple[str, ...]] | None = None
    include_field_changes: bool = False

    # #1218 Option A: when True, the DELETE handler stamps
    # ``deleted_at = NOW()`` via an UPDATE instead of issuing a
    # hard DELETE. Set by the route generator from
    # ``entity.soft_delete``.
    soft_delete: bool = False


def _set_handler_annotations(fn: Any, *, with_id: bool = False, with_auth: bool = False) -> None:
    """Set FastAPI-compatible type annotations on a dynamic handler function."""
    ann: dict[str, Any] = {"request": Request, "return": Any}
    if with_id:
        ann["id"] = UUID
    if with_auth:
        ann["auth_context"] = AuthContext
    fn.__annotations__ = ann


def _is_htmx_request(request: Any) -> bool:
    """Check if this is a genuine HTMX request (HX-Request header present)."""
    from dazzle.back.runtime.htmx_response import HtmxDetails

    return HtmxDetails.from_request(request).is_htmx


# _forbidden_detail moved to dazzle.render.access_messages in #1094 so that
# ui/ page handlers can build the same payload without crossing back↔ui.
# Re-exported here so the existing back-internal call sites keep working.
from datetime import UTC, date, datetime  # noqa: E402

from dazzle.render.access_messages import _forbidden_detail  # noqa: E402, F401


def _wants_html(request: Any) -> bool:
    """Check if the client wants an HTML response (HTMX or browser navigation)."""
    if _is_htmx_request(request):
        return True
    if hasattr(request, "headers"):
        accept = request.headers.get("Accept", "")
        return "text/html" in accept
    return False


def _htmx_current_url(request: Any) -> str | None:
    """Return the HX-Current-URL header if this is an HTMX request, else None."""
    return request.headers.get("hx-current-url") if _is_htmx_request(request) else None


def _htmx_parent_url(request: Any) -> str | None:
    """Return the parent of HX-Current-URL (e.g. /tasks/abc → /tasks) for post-delete redirect."""
    url = _htmx_current_url(request)
    if not url:
        return None
    # Strip trailing ID segment to get list page URL
    from urllib.parse import urlparse

    parsed = urlparse(url)
    parent = parsed.path.rsplit("/", 1)[0] or "/"
    return parent


async def _parse_request_body(request: Any) -> dict[str, Any]:
    """Parse request body as JSON or form data.

    HTMX forms send JSON when the json-enc extension is loaded, but
    fall back to form-urlencoded otherwise.  Accept both so the API
    works regardless of client encoding.

    Empty string values are converted to None so that optional fields
    (e.g. ref/UUID fields) pass Pydantic validation.
    """
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        body = dict(form)
    else:
        # Default: JSON (covers application/json and missing header)
        body = await request.json()
    # Convert empty strings to None for optional field validation
    return {k: (None if v == "" else v) for k, v in body.items()}


# =============================================================================
# Access Control Helpers
# =============================================================================


def _normalize_role(role: str) -> str:
    """Normalize a database role name to match DSL role references.

    Database roles may have a ``role_`` prefix (e.g. ``role_school_admin``)
    while DSL access rules use bare names (e.g. ``role(school_admin)``).
    """
    return role.removeprefix("role_")


# =============================================================================
# Route Handler Factory
# =============================================================================


def create_list_handler(
    spec: RouteSpec,
    *,
    access_spec: dict[str, Any] | None = None,
    select_fields: list[str] | None = None,
    json_projection: list[str] | None = None,
    htmx_columns: list[dict[str, Any]] | None = None,
    htmx_detail_url: str | None = None,
    htmx_entity_name: str | None = None,
    htmx_empty_message: str = "No items found.",
    search_fields: list[str] | None = None,
    filter_fields: list[str] | None = None,
    ref_targets: dict[str, str] | None = None,
    fk_graph: "FKGraph | None" = None,
    graph_spec: tuple[Any, Any | None] | None = None,
    all_services: dict[str, Any] | None = None,
    display_field: str | None = None,
    admin_personas: list[str] | None = None,
) -> Callable[..., Any]:
    """Create a handler for list operations with optional access control.

    See :class:`RouteSpec` for the per-route contract (#1011). The
    list-specific kwargs (htmx_*, search/filter, fk_graph, etc.) stay
    out of RouteSpec because they don't generalize across CRUD
    verbs.

    Args:
        spec: Per-route bundle (handler config + service + cross-verb fields)
        access_spec: Access control specification for this entity
        select_fields: Optional field projection for SQL queries
        json_projection: Optional field names to include in JSON API responses (#360)
        htmx_columns: Column definitions for HTMX table row rendering
        htmx_detail_url: Detail URL template for row click navigation
        htmx_entity_name: Entity name for HTMX rendering context (defaults to spec.handler.entity_name)
        htmx_empty_message: Message when no items found
        search_fields: Optional field names for LIKE-based search (#361)
        filter_fields: Allowed field names for bare query param filtering (#596)
    """
    service = spec.service
    auto_include = spec.auto_include
    optional_auth_dep = spec.handler.optional_auth_dep
    require_auth_by_default = spec.handler.require_auth_by_default
    entity_name = spec.handler.entity_name
    audit_logger = spec.handler.audit_logger
    cedar_access_spec = spec.handler.cedar_access_spec
    if htmx_entity_name is None:
        htmx_entity_name = entity_name

    def _inject_htmx_meta(request: Request) -> None:
        """Set HTMX rendering metadata on request.state for table row fragments."""
        if htmx_columns is not None:
            request.state.htmx_columns = htmx_columns
        if htmx_detail_url is not None:
            request.state.htmx_detail_url = htmx_detail_url
        request.state.htmx_entity_name = htmx_entity_name
        request.state.htmx_empty_message = htmx_empty_message

    if optional_auth_dep is not None:

        async def _auth_handler(
            request: Request,
            auth_context: AuthContext = Depends(optional_auth_dep),
            page: int = Query(1, ge=1, description="Page number"),
            page_size: int = Query(20, ge=1, le=100, description="Items per page"),
            sort: str | None = Query(None, description="Sort field"),
            dir: str = Query("asc", description="Sort direction (asc/desc)"),
            search: str | None = Query(None, description="Search query"),
            q: str | None = Query(None, description="Search query (alias for search)"),
        ) -> Any:
            is_authenticated = auth_context.is_authenticated
            user_id = str(auth_context.user.id) if auth_context.user else None

            # Deny-default: require authentication when enabled and no explicit access rules
            if require_auth_by_default and not access_spec and not is_authenticated:
                raise HTTPException(
                    status_code=401,
                    detail="Authentication required",
                )

            # Support ?q= as alias for ?search= (#596)
            effective_search = search or q

            _inject_htmx_meta(request)
            return await _list_handler_body(
                service,
                access_spec,
                is_authenticated,
                user_id,
                request,
                page,
                page_size,
                sort,
                dir,
                effective_search,
                select_fields=select_fields,
                json_projection=json_projection,
                auto_include=auto_include,
                cedar_access_spec=cedar_access_spec,
                auth_context=auth_context,
                audit_logger=audit_logger,
                entity_name=entity_name,
                user=auth_context.user if auth_context and auth_context.is_authenticated else None,
                search_fields=search_fields,
                filter_fields=filter_fields,
                ref_targets=ref_targets,
                fk_graph=fk_graph,
                graph_spec=graph_spec,
                all_services=all_services,
                display_field=display_field,
                admin_personas=admin_personas,
            )

        _auth_handler.__annotations__ = {
            "request": Request,
            "auth_context": AuthContext,
            "page": int,
            "page_size": int,
            "sort": str | None,
            "dir": str,
            "search": str | None,
            "q": str | None,
            "return": Any,
        }
        return _auth_handler

    async def _noauth_handler(
        request: Request,
        page: int = Query(1, ge=1, description="Page number"),
        page_size: int = Query(20, ge=1, le=100, description="Items per page"),
        sort: str | None = Query(None, description="Sort field"),
        dir: str = Query("asc", description="Sort direction (asc/desc)"),
        search: str | None = Query(None, description="Search query"),
        q: str | None = Query(None, description="Search query (alias for search)"),
    ) -> Any:
        # Support ?q= as alias for ?search= (#596)
        effective_search = search or q

        _inject_htmx_meta(request)
        return await _list_handler_body(
            service,
            access_spec,
            False,
            None,
            request,
            page,
            page_size,
            sort,
            dir,
            effective_search,
            select_fields=select_fields,
            json_projection=json_projection,
            auto_include=auto_include,
            cedar_access_spec=cedar_access_spec,
            audit_logger=audit_logger,
            entity_name=entity_name,
            search_fields=search_fields,
            filter_fields=filter_fields,
            ref_targets=ref_targets,
            fk_graph=fk_graph,
            graph_spec=graph_spec,
            all_services=all_services,
            display_field=display_field,
            admin_personas=admin_personas,
        )

    _noauth_handler.__annotations__ = {
        "request": Request,
        "page": int,
        "page_size": int,
        "sort": str | None,
        "dir": str,
        "search": str | None,
        "q": str | None,
        "return": Any,
    }
    return _noauth_handler


def _is_field_condition(condition: Any) -> bool:
    """Return True if condition requires record data to evaluate.

    Role checks need only the user's roles — evaluable at the gate without a record.
    Comparisons and grant checks reference entity fields — need record data.
    Logical nodes recurse: if either branch needs record data, the whole
    condition is a field condition.
    """
    if condition is None:
        return False
    kind = getattr(condition, "kind", None)
    if kind == "role_check":
        return False
    if kind in ("comparison", "grant_check", "via_check"):
        return True
    if kind == "logical":
        return _is_field_condition(getattr(condition, "logical_left", None)) or _is_field_condition(
            getattr(condition, "logical_right", None)
        )
    return False


async def _list_handler_body(
    service: Any,
    access_spec: dict[str, Any] | None,
    is_authenticated: bool,
    user_id: str | None,
    request: Any,
    page: int,
    page_size: int,
    sort: str | None,
    dir: str,
    search: str | None,
    select_fields: list[str] | None = None,
    json_projection: list[str] | None = None,
    auto_include: list[str] | None = None,
    cedar_access_spec: "EntityAccessSpec | None" = None,
    auth_context: "AuthContext | None" = None,
    audit_logger: "AuditLogger | None" = None,
    entity_name: str = "Item",
    user: Any | None = None,
    search_fields: list[str] | None = None,
    filter_fields: list[str] | None = None,
    ref_targets: dict[str, str] | None = None,
    fk_graph: "FKGraph | None" = None,
    graph_spec: tuple[Any, Any | None] | None = None,
    all_services: dict[str, Any] | None = None,
    display_field: str | None = None,
    admin_personas: list[str] | None = None,
) -> Any:
    """Shared list handler logic for both auth and no-auth paths."""
    from dazzle.back.runtime.condition_evaluator import (
        build_visibility_filter,
        filter_records_by_condition,
    )

    # Gate: Cedar LIST permission check (entity-level, before row filters).
    # Only enforced when ALL list rules are pure role checks. Rules with
    # field conditions (e.g. school = current_user.school) are row-level
    # filters that can't be evaluated without a record — those pass the gate
    # and are enforced at query time by scope predicates. (#502, #503)
    if cedar_access_spec and is_authenticated and auth_context:
        from dazzle.core.access import AccessOperationKind

        list_rules = [
            r for r in cedar_access_spec.permissions if r.operation == AccessOperationKind.LIST
        ]
        # Only gate when all list rules are pure role checks (no field conditions)
        has_field_conditions = any(_is_field_condition(r.condition) for r in list_rules)
        if list_rules and not has_field_conditions:
            from dazzle.render.access_evaluator import evaluate_permission

            _user, _ctx = _build_access_context(auth_context)
            decision = evaluate_permission(
                cedar_access_spec, AccessOperationKind.LIST, None, _ctx, entity_name=entity_name
            )
            if not decision.allowed:
                raise HTTPException(
                    status_code=403,
                    detail=_forbidden_detail(
                        entity_name=entity_name,
                        operation=AccessOperationKind.LIST,
                        cedar_access_spec=cedar_access_spec,
                        current_roles=list(getattr(_user, "roles", [])) if _user else [],
                    ),
                )

    # Build visibility filters
    sql_filters, post_filter = build_visibility_filter(access_spec, is_authenticated, user_id)

    # Apply scope filters (v0.44 — scope: blocks with predicate-compiled SQL).
    # When scopes list is non-empty, use _resolve_scope_filters which delegates
    # to the predicate compiler when predicates are available.
    if cedar_access_spec and is_authenticated and user_id:
        # Collect normalized user roles for scope matching
        _scope_user_roles: set[str] = set()
        if auth_context is not None:
            _scope_user_obj = getattr(auth_context, "user", None)
            if _scope_user_obj:
                for _r in getattr(_scope_user_obj, "roles", []):
                    _rname = _r if isinstance(_r, str) else getattr(_r, "name", str(_r))
                    _scope_user_roles.add(_normalize_role(_rname))

        _has_scopes = bool(getattr(cedar_access_spec, "scopes", None))
        if _has_scopes:
            scope_result = _resolve_scope_filters(
                cedar_access_spec,
                "list",
                _scope_user_roles,
                user_id,
                auth_context,
                ref_targets,
                entity_name=entity_name,
                fk_graph=fk_graph,
                admin_personas=admin_personas,
            )
            if scope_result is None:
                # No scope rule matched this role — default-deny at scope layer
                return {
                    "items": [],
                    "total": 0,
                    "page": page,
                    "page_size": page_size,
                }
            if scope_result:
                sql_filters = {**(sql_filters or {}), **scope_result}

    # Extract filter[field] params from query string
    filters: dict[str, Any] = {}
    # Reserved query param names that should never be treated as field filters
    _reserved_params = {"page", "page_size", "sort", "dir", "search", "q", "format"}
    for key, value in request.query_params.items():
        if key.startswith("filter[") and key.endswith("]") and value:
            filters[key[7:-1]] = value
        elif filter_fields and key in filter_fields and key not in _reserved_params and value:
            # Accept bare ?field=value when field is in the DSL-declared filter list (#596)
            filters[key] = value

    # Merge visibility filters with user filters
    merged_filters: dict[str, Any] | None = None
    if sql_filters or filters:
        merged_filters = {**(sql_filters or {}), **filters}

    # #1223 Phase 3a.iv — `?as_of=YYYY-MM-DD` URL parameter for temporal
    # entities. The Repository layer reads the special `__as_of` filter
    # dict key and replaces the default tombstone filter with the
    # open-interval predicate. The URL param name is configurable via
    # `entity.temporal.as_of_param` (default `as_of`).
    _entity_spec = getattr(service, "entity_spec", None)
    _entity_temporal = _entity_spec.temporal if _entity_spec is not None else None
    if _entity_temporal is not None:
        _as_of_raw = request.query_params.get(_entity_temporal.as_of_param)
        if _as_of_raw:
            from datetime import date as _date

            try:
                _as_of_value = _date.fromisoformat(_as_of_raw)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Invalid {_entity_temporal.as_of_param}={_as_of_raw!r}: "
                        f"expected YYYY-MM-DD"
                    ),
                )
            if merged_filters is None:
                merged_filters = {}
            merged_filters["__as_of"] = _as_of_value

        # `?include_closed=true` — friendly alias for opting out of the
        # default "active rows only" filter on a temporal entity. Sets
        # `<end_field>__isnull=False` which the Repository layer honours
        # via its setdefault contract: an explicit caller-provided value
        # for the tombstone key wins over the default.
        _include_closed_raw = request.query_params.get("include_closed", "").lower()
        if _include_closed_raw in ("true", "1", "yes"):
            if merged_filters is None:
                merged_filters = {}
            merged_filters[f"{_entity_temporal.end_field}__isnull"] = False

    # Build sort list for repository
    sort_list = [f"-{sort}" if dir == "desc" else sort] if sort else None

    # Execute list with filters, sort, and search
    result = await service.execute(
        operation="list",
        page=page,
        page_size=page_size,
        filters=merged_filters,
        sort=sort_list,
        search=search,
        select_fields=select_fields,
        include=auto_include,
        search_fields=search_fields,
    )

    # Audit log the list access
    if audit_logger:
        await _log_audit_decision(
            audit_logger,
            request,
            operation="list",
            entity_name=entity_name,
            entity_id=None,
            decision="allow",
            matched_policy="authenticated" if is_authenticated else "public",
            policy_effect="permit",
            user=user,
        )

    # Apply post-filtering if needed (for OR conditions)
    if post_filter and result and "items" in result:
        context = {"current_user_id": user_id}
        # Convert Pydantic models to dicts for filtering
        items = result["items"]
        if items and hasattr(items[0], "model_dump"):
            items = [item.model_dump() for item in items]
        filtered_items = filter_records_by_condition(items, post_filter, context)
        result["items"] = filtered_items
        result["total"] = len(filtered_items)

    # #928: inject `__display__` on top-level list rows when the entity
    # has a registered `display_field`. The relation_loader does the
    # same injection when eager-loading FKs as nested objects, but
    # FK `<select>` widgets fetch the target entity's plain list
    # endpoint — that path bypassed relation_loader entirely, so option
    # text fell back to the UUID. With this hop the JS display() lambda
    # in `form_field.html` (which already prefers `item.__display__`)
    # surfaces the human-readable label.
    if display_field and result and isinstance(result, dict) and "items" in result:
        materialised: list[Any] = []
        for item in result["items"]:
            if hasattr(item, "model_dump"):
                row = item.model_dump(mode="json")
            elif isinstance(item, dict):
                row = dict(item)
            else:
                materialised.append(item)
                continue
            if display_field in row and "__display__" not in row:
                row["__display__"] = row[display_field]
            materialised.append(row)
        result["items"] = materialised

    # Graph format serialization (#619 Phase 2)
    format_param = request.query_params.get("format")
    if format_param and format_param != "raw":
        from starlette.responses import JSONResponse

        if format_param not in ("cytoscape", "d3"):
            return JSONResponse(
                {"detail": "Invalid format. Supported: cytoscape, d3, raw"},
                status_code=400,
            )
        if graph_spec is None:
            return JSONResponse(
                {"detail": f"Entity '{entity_name}' does not declare graph_edge:"},
                status_code=400,
            )

        from dazzle.back.runtime.graph_serializer import GraphSerializer

        graph_edge_spec, node_specs = graph_spec

        # Extract items as dicts
        items = result.get("items", []) if isinstance(result, dict) else []
        edge_dicts = []
        for item in items:
            if hasattr(item, "model_dump"):
                edge_dicts.append(item.model_dump(mode="json"))
            elif isinstance(item, dict):
                edge_dicts.append(item)

        # Collect node IDs grouped by target entity type
        node_ids_by_entity: dict[str, set[str]] = {}
        for edge in edge_dicts:
            for field_name in (graph_edge_spec.source, graph_edge_spec.target):
                ref_id = edge.get(field_name)
                if ref_id is None:
                    continue
                ref_entity = (ref_targets or {}).get(field_name, "")
                if ref_entity:
                    node_ids_by_entity.setdefault(ref_entity, set()).add(str(ref_id))

        # Batch-fetch nodes per entity type
        all_nodes: list[dict[str, Any]] = []
        for ref_entity_name, ids in node_ids_by_entity.items():
            node_service = (all_services or {}).get(ref_entity_name)
            if node_service is None:
                continue
            try:
                node_result = await node_service.execute(
                    operation="list",
                    page=1,
                    page_size=len(ids),
                    filters={"id__in": list(ids)},
                )
                node_items = node_result.get("items", []) if isinstance(node_result, dict) else []
                for ni in node_items:
                    if hasattr(ni, "model_dump"):
                        all_nodes.append(ni.model_dump(mode="json"))
                    elif isinstance(ni, dict):
                        all_nodes.append(ni)
            except Exception:
                # Node fetch failure — edges returned, nodes omitted (#smells-1.1).
                logger.debug("Graph-node fetch failed; returning edges only", exc_info=True)

        # Pick graph_node spec (first available for the serializer)
        gn_spec = next(iter(node_specs.values()), None) if node_specs else None
        serializer = GraphSerializer(graph_edge=graph_edge_spec, graph_node=gn_spec)

        if format_param == "cytoscape":
            return serializer.to_cytoscape(edge_dicts, all_nodes)
        else:
            return serializer.to_d3(edge_dicts, all_nodes)

    # Browser navigation: redirect to UI list page (#356)
    if _wants_html(request) and not _is_htmx_request(request):
        from starlette.responses import RedirectResponse

        _slug = entity_name.lower().replace("_", "-")
        redirect_url = f"/app/{_slug}"
        if request.query_params:
            redirect_url += f"?{request.url.query}"
        return RedirectResponse(url=redirect_url, status_code=302)

    # HTMX content negotiation: return HTML fragment for HX-Request
    if _is_htmx_request(request):
        try:
            from dazzle.back.runtime.htmx_response import HtmxDetails

            htmx = HtmxDetails.from_request(request)

            # Derive table_id from HX-Target (e.g. "dt-tasks-body" → "dt-tasks")
            table_id = "dt-table"
            if htmx.target and htmx.target.endswith("-body"):
                table_id = htmx.target.removesuffix("-body")

            items = result.get("items", []) if isinstance(result, dict) else []
            # Convert Pydantic models to dicts
            if items and hasattr(items[0], "model_dump"):
                items = [item.model_dump() for item in items]

            total = result.get("total", 0) if isinstance(result, dict) else 0
            table_dict = {
                "rows": items,
                "columns": request.state.htmx_columns
                if hasattr(request.state, "htmx_columns")
                else [],
                "detail_url_template": getattr(request.state, "htmx_detail_url", None),
                "entity_name": getattr(request.state, "htmx_entity_name", "Item"),
                "api_endpoint": str(request.url.path),
                "table_id": table_id,
                "sort_field": sort or "",
                "sort_dir": dir,
                "filter_values": filters,
                "page": page,
                "page_size": page_size,
                "total": total,
                "empty_message": getattr(request.state, "htmx_empty_message", "No items found."),
            }

            # Phase 4 (v0.67.68): full inline-render — both the empty
            # branch and the row branch are now Python. The legacy
            # `fragments/table_rows.html` + `fragments/inline_edit.html`
            # templates are no longer reached from this code path.
            if not items:
                html = _render_table_empty(table_dict, request)
            else:
                html = "".join(_render_table_row(table_dict, item) for item in items)

            # Check if table uses infinite scroll mode
            pagination_mode = getattr(request.state, "htmx_pagination_mode", "pages")

            if pagination_mode == "infinite":
                # Phase 4 (v0.67.65): inline-render the infinite-scroll sentinel.
                html += _render_table_sentinel(table_dict)
            else:
                # Phase 4 (v0.67.65): inline-render the pagination row.
                pagination_html = _render_table_pagination(table_dict)
                html += f'<div id="{table_id}-pagination" hx-swap-oob="true">{pagination_html}</div>'  # nosemgrep

            return HTMLResponse(content=html)
        except ImportError:
            pass  # Template renderer not available, fall through to JSON
        except Exception:
            import logging as _logging

            _logging.getLogger("dazzle.runtime").exception(
                "HTMX fragment render failed for %s", entity_name
            )
            # Return an error row so the skeleton resolves with a visible message
            # instead of hanging indefinitely (#496).
            return HTMLResponse(
                content=(
                    '<tr><td colspan="99" class="text-center py-8 text-[hsl(var(--destructive))]">'
                    "Something went wrong loading this list.</td></tr>"
                ),
                status_code=200,
            )

    # Apply field projection to JSON responses (#360)
    if json_projection and result and isinstance(result, dict) and "items" in result:
        # Auto-include relation names must survive projection so eager-loaded
        # nested data reaches the client (#777).
        allowed = set(json_projection)
        if auto_include:
            allowed.update(auto_include)
        # #928: __display__ is added by the FK display injection above —
        # surface it through projection so create-form FK selects can use it.
        allowed.add("__display__")
        projected_items = []
        for item in result["items"]:
            if hasattr(item, "model_dump"):
                d = item.model_dump(mode="json")
            elif isinstance(item, dict):
                d = item
            else:
                projected_items.append(item)
                continue
            projected_items.append({k: v for k, v in d.items() if k in allowed})
        result = {**result, "items": projected_items}

    return result


def create_read_handler(spec: RouteSpec) -> Callable[..., Any]:
    """Create a handler for read operations with optional Cedar-style access control.

    See :class:`RouteSpec` for the per-route contract (#1011).
    """
    service = spec.service
    auto_include = spec.auto_include
    auth_dep = spec.handler.auth_dep
    optional_auth_dep = spec.handler.optional_auth_dep
    require_auth_by_default = spec.handler.require_auth_by_default
    entity_name = spec.handler.entity_name
    audit_logger = spec.handler.audit_logger
    cedar_access_spec = spec.handler.cedar_access_spec

    async def _core(
        id: UUID,
        request: Request,
        *,
        current_user: str | None = None,
        existing: Any = None,
        **_extra: Any,
    ) -> Any:
        # #1223 Phase 3a.iv (read-path follow-up): honour `?as_of=YYYY-MM-DD`
        # on the single-row read endpoint for temporal entities. List + aggregate
        # paths already handle this via the __as_of filter dict key (v0.71.164);
        # read() doesn't take a filters dict so as_of threads through as a
        # service-execute kwarg. Repository.read consumes it directly.
        _entity_spec = getattr(service, "entity_spec", None)
        _entity_temporal = _entity_spec.temporal if _entity_spec is not None else None
        _read_kwargs: dict[str, Any] = {"include": auto_include}
        if _entity_temporal is not None:
            _as_of_raw = request.query_params.get(_entity_temporal.as_of_param)
            if _as_of_raw:
                try:
                    _read_kwargs["as_of"] = date.fromisoformat(_as_of_raw)
                except ValueError:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Invalid {_entity_temporal.as_of_param}={_as_of_raw!r}: "
                            f"expected YYYY-MM-DD"
                        ),
                    )
        result = await service.execute(operation="read", id=id, **_read_kwargs)
        if result is None:
            raise HTTPException(status_code=404, detail="Not found")
        html = _render_detail_html(request, result, entity_name)
        return html if html is not None else result

    # READ is special: Cedar needs the *fetched* record for policy eval, but
    # the core already does the fetch.  The generic wrapper's pre-read would
    # double-fetch.  So for Cedar-READ we inline a lightweight wrapper that
    # fetches once, evaluates, then returns.
    _use_cedar = cedar_access_spec is not None and optional_auth_dep is not None
    fk_graph = spec.handler.fk_graph
    admin_personas = spec.handler.admin_personas
    if _use_cedar:

        async def _read_cedar(
            id: UUID, request: Request, auth_context: AuthContext = Depends(optional_auth_dep)
        ) -> Any:
            from dazzle.back.runtime.audit_log import measure_evaluation_time
            from dazzle.core.access import AccessDecision, AccessOperationKind
            from dazzle.render.access_evaluator import evaluate_permission

            # Apply `scope: read:` row-level enforcement (#1174). Before this,
            # the single-id READ path fetched the row unscoped and only ran the
            # Cedar permit/forbid evaluator — so a role holding `permit: read`
            # plus a `scope: read:` row-filter (e.g. `project.org =
            # current_user.org`) could IDOR-fetch *any* row by id, cross-tenant.
            # `_scoped_pre_read` re-queries through the scope predicate (the
            # same path UPDATE/DELETE use) and returns None — yielding a 404 —
            # when the row is outside the caller's scope.
            assert cedar_access_spec is not None
            result = await _scoped_pre_read(
                service=service,
                operation="read",
                id=id,
                cedar_access_spec=cedar_access_spec,
                auth_context=auth_context,
                entity_name=entity_name,
                fk_graph=fk_graph,
                admin_personas=admin_personas,
            )
            if result is None:
                # Scope filter hid the row (or it does not exist). Record the
                # deny in the audit trail — a scope-denied read is an
                # access-control decision and `audit: all` entities must
                # capture it — then 404 (row-existence opaque to the caller).
                if audit_logger:
                    _u, _ = _build_access_context(auth_context)
                    await _log_audit_decision(
                        audit_logger,
                        request,
                        operation="read",
                        entity_name=entity_name,
                        entity_id=str(id),
                        decision="deny",
                        matched_policy=_SCOPE_DENY_EFFECT,
                        policy_effect=_SCOPE_DENY_EFFECT,
                        user=_u,
                    )
                raise HTTPException(status_code=404, detail="Not found")
            # `_scoped_pre_read` may return a row fetched via the list path,
            # which does not carry `include=auto_include` relations. Re-fetch
            # through the read path so the response shape is unchanged when a
            # scope filter was applied. The re-fetch is intentionally unscoped:
            # scope has already passed for this id above — this only restores
            # the relation hydration the list-path row lacks.
            if auto_include:
                hydrated = await service.execute(operation="read", id=id, include=auto_include)
                if hydrated is not None:
                    result = hydrated

            user, ctx = _build_access_context(auth_context)
            assert cedar_access_spec is not None
            decision: AccessDecision
            decision, eval_us = measure_evaluation_time(
                lambda: evaluate_permission(
                    cedar_access_spec,
                    AccessOperationKind.READ,
                    _record_to_dict(result),
                    ctx,
                    entity_name=entity_name,
                )
            )

            if audit_logger:
                await _log_audit_decision(
                    audit_logger,
                    request,
                    operation="read",
                    entity_name=entity_name,
                    entity_id=str(id),
                    decision="allow" if decision.allowed else "deny",
                    matched_policy=decision.matched_policy,
                    policy_effect=decision.effect,
                    user=user,
                    evaluation_time_us=eval_us,
                )

            if not decision.allowed:
                raise HTTPException(status_code=404, detail="Not found")
            html = _render_detail_html(request, result, entity_name)
            return html if html is not None else result

        _set_handler_annotations(_read_cedar, with_id=True, with_auth=True)
        return _read_cedar

    # Non-cedar: use the generic wrapper (no pre-read needed)
    return _wrap_with_auth(
        _core,
        service=service,
        cedar_access_spec=None,
        auth_dep=auth_dep,
        optional_auth_dep=optional_auth_dep,
        require_auth_by_default=require_auth_by_default,
        operation="read",
        entity_name=entity_name,
        audit_logger=audit_logger,
    )


def _extract_result_id(result: Any) -> str | None:
    """Extract the id from a create result (Pydantic model or dict)."""
    if hasattr(result, "id"):
        return str(result.id)
    if isinstance(result, dict) and "id" in result:
        return str(result["id"])
    return None


async def resolve_backed_entity_refs(
    body: dict[str, Any],
    input_schema: type[BaseModel],
    persona_ref_map: dict[str, tuple[str, str, Any]] | None,
    user_roles: list[str],
    current_user: str | None,
    user_email: str | None,
) -> None:
    """Auto-inject persona-backed entity refs into missing form fields.

    Cycle 249 (closes EX-049). When a ``ref Tester`` field is missing
    from the request body AND the current user's role is ``tester``
    AND persona ``tester`` declares ``backed_by: Tester``, this
    helper looks up the Tester row via the ``link_via`` field and
    injects the Tester's ID.

    Args:
        body: Parsed request body dict (mutated in place).
        input_schema: Pydantic schema for required-field detection.
        persona_ref_map: Maps ``fk_field_name`` →
            ``(target_entity, link_via, repository)`` for each ref
            field that targets a persona-backed entity. Built at
            route-registration time from ``entity_ref_targets`` +
            the appspec's ``backed_by`` declarations.
        user_roles: The current user's roles (with or without
            ``role_`` prefix).
        current_user: Auth user id string (used for ``link_via: id``).
        user_email: Auth user email (used for ``link_via: email``).
    """
    if not persona_ref_map or not user_roles:
        return

    for fk_field, (target_entity, link_via, repo) in persona_ref_map.items():
        # Skip if the body already has a value for this field
        existing = body.get(fk_field)
        if existing is not None:
            continue

        # Skip if the field isn't required on the schema
        field_info = input_schema.model_fields.get(fk_field)
        if field_info is None or not field_info.is_required():
            continue

        # Resolve the lookup value based on link_via
        if link_via == "id" and current_user:
            # Convention: auth user ID == entity ID (zero-cost, no DB lookup)
            body[fk_field] = current_user
        elif link_via == "email" and user_email and repo:
            # DB lookup: find the entity row where email matches
            try:
                result = await repo.get_one(filters={link_via: user_email})
                if result:
                    entity_id = getattr(result, "id", None) or (
                        result.get("id") if isinstance(result, dict) else None
                    )
                    if entity_id:
                        body[fk_field] = str(entity_id)
            except Exception:
                import logging

                logging.getLogger(__name__).debug(
                    "backed_by lookup failed for %s.%s=%s",
                    target_entity,
                    link_via,
                    user_email,
                    exc_info=True,
                )
        elif user_email and repo:
            # Generic link_via field — DB lookup
            try:
                result = await repo.get_one(filters={link_via: user_email})
                if result:
                    entity_id = getattr(result, "id", None) or (
                        result.get("id") if isinstance(result, dict) else None
                    )
                    if entity_id:
                        body[fk_field] = str(entity_id)
            except Exception:
                import logging

                logging.getLogger(__name__).debug(
                    "backed_by lookup failed for %s.%s=%s",
                    target_entity,
                    link_via,
                    user_email,
                    exc_info=True,
                )


def inject_current_user_refs(
    body: dict[str, Any],
    input_schema: type[BaseModel],
    user_ref_fields: list[str] | None,
    current_user: str | None,
) -> None:
    """Auto-inject ``current_user`` into missing required ``ref User`` fields.

    Mutates ``body`` in place. Rules (all must hold for a field to be injected):

    1. ``current_user`` is non-empty (we know who to inject)
    2. ``user_ref_fields`` is non-empty (caller has identified ref-User fields)
    3. The field exists on ``input_schema.model_fields``
    4. The field is declared required on the schema (no default, not Optional)
    5. The body either does NOT contain the field OR contains ``None`` for it

    Closes manwithacat/dazzle#774. Before this helper existed, create surfaces that
    omitted ``created_by`` (or similar ``ref User required`` fields) from
    their DSL section would produce a pydantic ``Field required`` error on
    a field the user was never shown. The helper closes the gap by letting
    the framework supply ``current_user`` for any ref-User field the DSL
    author left out, without silently overriding explicit values.

    Args:
        body: Parsed request body dict (mutated in place)
        input_schema: The pydantic schema the handler will ``model_validate``
            against. Used to detect required fields.
        user_ref_fields: Names of fields on this entity whose ``ref_entity``
            is "User". Typically computed from the entity's
            ``entity_ref_targets`` at route-registration time.
        current_user: String representation of the current user's id.
    """
    if not current_user or not user_ref_fields:
        return
    for fname in user_ref_fields:
        existing = body.get(fname)
        if existing is not None:
            continue
        field_info = input_schema.model_fields.get(fname)
        if field_info is None:
            continue
        if not field_info.is_required():
            continue
        body[fname] = current_user


def create_create_handler(
    spec: RouteSpec,
    *,
    entity_slug: str = "",
    user_ref_fields: list[str] | None = None,
    persona_ref_map: dict[str, tuple[str, str, Any]] | None = None,
) -> Callable[..., Any]:
    """Create a handler for create operations with optional Cedar-style access control.

    See :class:`RouteSpec` for the per-route contract (#1011).
    ``spec.input_schema`` is required for create handlers.

    Args:
        user_ref_fields: Names of fields on this entity that are ``ref User``
            foreign keys. When the request body omits any of these (because
            the DSL create surface didn't expose them — e.g. ``created_by``),
            the handler auto-injects ``current_user`` before schema
            validation, provided the field is declared required in the
            Pydantic input schema. See ``inject_current_user_refs``.
            Closes manwithacat/dazzle#774.
        persona_ref_map: Maps ``fk_field_name`` →
            ``(target_entity, link_via, repository)`` for each ref
            field that targets a persona-backed entity. Cycle 249
            (closes EX-049). See ``resolve_backed_entity_refs``.
    """
    service = spec.service
    if spec.input_schema is None:
        raise ValueError("create_create_handler requires spec.input_schema")
    input_schema = spec.input_schema
    storage_bindings = spec.storage_bindings
    auth_dep = spec.handler.auth_dep
    optional_auth_dep = spec.handler.optional_auth_dep
    require_auth_by_default = spec.handler.require_auth_by_default
    entity_name = spec.handler.entity_name
    audit_logger = spec.handler.audit_logger
    cedar_access_spec = spec.handler.cedar_access_spec

    def _build_redirect_url(result: Any) -> str | None:
        if not entity_slug:
            return None
        result_id = _extract_result_id(result)
        if result_id:
            return f"/app/{entity_slug}/{result_id}"
        return None

    async def _core(
        _id: Any,
        request: Request,
        *,
        current_user: str | None = None,
        existing: Any = None,
        **_extra: Any,
    ) -> Any:
        body = await _parse_request_body(request)

        # #932 cycle 4: verify any storage-bound s3_key in the body
        # against the caller's prefix sandbox + object existence. Runs
        # BEFORE Pydantic validation so an invalid key short-circuits
        # the create with the right 4xx/5xx and a precise message
        # rather than silently persisting an unverified key.
        if storage_bindings:
            from dazzle.back.runtime.storage import (
                StorageVerificationError,
                verify_storage_field_keys,
            )

            registry = getattr(request.app.state, "storage_registry", None)
            try:
                verify_storage_field_keys(body, storage_bindings, registry, current_user)
            except StorageVerificationError as exc:
                raise HTTPException(
                    status_code=exc.status_code,
                    detail={
                        "error": "storage_verification_failed",
                        "field": exc.field,
                        "storage": exc.storage,
                        "reason": exc.reason,
                    },
                ) from exc

        # Inject idempotency key from header if present (#693)
        idem_key = request.headers.get("x-idempotency-key")
        if idem_key and "idempotency_key" not in body:
            body["idempotency_key"] = idem_key

        # Auto-inject current_user for missing required `ref User` fields
        # (manwithacat/dazzle#774). See inject_current_user_refs for the full rule set.
        inject_current_user_refs(body, input_schema, user_ref_fields, current_user)

        # Auto-inject persona-backed entity refs for missing required fields
        # (cycle 249, closes EX-049). See resolve_backed_entity_refs for
        # the full rule set. Uses user_email from the auth context to do
        # an async DB lookup when link_via != "id".
        _user_email = _extra.get("user_email")
        _user_roles = _extra.get("user_roles", [])
        if persona_ref_map:
            await resolve_backed_entity_refs(
                body,
                input_schema,
                persona_ref_map,
                _user_roles or [],
                current_user,
                _user_email,
            )

        data = input_schema.model_validate(body)

        # #1124 / #1311: scope: create: enforcement. Predicate is
        # evaluated AFTER current_user / persona-backed-ref injection
        # (so `created_by = current_user as: member` evaluates against
        # the resolved payload) but BEFORE service.execute, so a
        # predicate rejection 403s before the insert. Simple leaves
        # (ColumnCheck, UserAttrCheck, PathCheck depth 1, BoolComposite)
        # evaluate in-Python against the payload; FK-path (depth > 1) and
        # EXISTS leaves resolve via a payload-time SQL probe on the
        # entity's repository (ADR-0028). See docs/reference/rbac-scope.md.
        _scope_user_roles = list(_extra.get("user_roles") or [])
        # `mode="json"` so UUID / datetime payload fields are normalised to
        # their string form. The create-scope walker compares them against
        # `current_user.<attr>` values, which `_resolve_user_attribute`
        # always returns as `str` — a bare `model_dump()` would leave a
        # `ref` field as a `UUID` object, and `UUID(...) == "..."` is always
        # False, so an own-org create would 403 on a pure type mismatch (#1174).
        _enforce_create_scope(
            cedar_access_spec=cedar_access_spec,
            payload=data.model_dump(mode="json"),
            user_id=current_user,
            user_roles=_scope_user_roles,
            entity_name=entity_name,
            auth_context=_extra.get("auth_context"),
            service=service,
            fk_graph=spec.handler.fk_graph,
        )

        # Handle idempotent duplicate: unique constraint on idempotency_key
        # returns a 200 instead of the normal 422 constraint error.
        try:
            result = await service.execute(operation="create", data=data)
        except ConstraintViolationError as exc:
            if idem_key and exc.field == "idempotency_key":
                return {"status": "duplicate", "message": "Already submitted"}
            raise

        return _with_htmx_triggers(
            request, result, entity_name, "created", redirect_url=_build_redirect_url(result)
        )

    return _wrap_with_auth(
        _core,
        service=service,
        cedar_access_spec=cedar_access_spec,
        auth_dep=auth_dep,
        optional_auth_dep=optional_auth_dep,
        require_auth_by_default=require_auth_by_default,
        operation="create",
        entity_name=entity_name,
        audit_logger=audit_logger,
    )


def create_update_handler(spec: RouteSpec) -> Callable[..., Any]:
    """Create a handler for update operations with optional Cedar-style access control.

    See :class:`RouteSpec` for the per-route contract (#1011).
    ``spec.input_schema`` is required for update handlers.
    """
    service = spec.service
    if spec.input_schema is None:
        raise ValueError("create_update_handler requires spec.input_schema")
    input_schema = spec.input_schema
    storage_bindings = spec.storage_bindings
    include_field_changes = spec.include_field_changes
    auth_dep = spec.handler.auth_dep
    optional_auth_dep = spec.handler.optional_auth_dep
    require_auth_by_default = spec.handler.require_auth_by_default
    entity_name = spec.handler.entity_name
    audit_logger = spec.handler.audit_logger
    cedar_access_spec = spec.handler.cedar_access_spec

    async def _core(
        id: UUID,
        request: Request,
        *,
        current_user: str | None = None,
        existing: Any = None,
        user_roles: list[str] | None = None,
        is_superuser: bool = False,
        **_extra: Any,
    ) -> Any:
        body = await _parse_request_body(request)

        # #932 cycle 4: same verification gate as the create path —
        # an update that swaps in a new s3_key must satisfy the
        # caller's prefix sandbox + object existence. Body fields not
        # present (or null) are skipped: an update that doesn't touch
        # the file column re-uses the previously-stored key.
        if storage_bindings:
            from dazzle.back.runtime.storage import (
                StorageVerificationError,
                verify_storage_field_keys,
            )

            registry = getattr(request.app.state, "storage_registry", None)
            try:
                verify_storage_field_keys(body, storage_bindings, registry, current_user)
            except StorageVerificationError as exc:
                raise HTTPException(
                    status_code=exc.status_code,
                    detail={
                        "error": "storage_verification_failed",
                        "field": exc.field,
                        "storage": exc.storage,
                        "reason": exc.reason,
                    },
                ) from exc

        data = input_schema.model_validate(body)

        # #1312 (ADR-0028): scope: update: DESTINATION enforcement. The
        # pre-read validated the source row; this re-validates the row's
        # would-be-final state (existing ⊕ changed fields) so an update can't
        # repoint an FK to move the row INTO a foreign scope. Runs BEFORE the
        # write; 404 on denial (IDOR-avoidance, matching the pre-read). Uses
        # `exclude_unset` so untouched scope-key columns keep their existing
        # (already-validated) value rather than being treated as nulled.
        _enforce_update_scope(
            cedar_access_spec=cedar_access_spec,
            existing=existing,
            new_values=data.model_dump(mode="json", exclude_unset=True),
            user_id=current_user,
            user_roles=list(user_roles or []),
            entity_name=entity_name,
            auth_context=_extra.get("auth_context"),
            service=service,
            fk_graph=spec.handler.fk_graph,
        )

        kwargs: dict[str, Any] = {"operation": "update", "id": id, "data": data}
        if current_user is not None:
            kwargs["current_user"] = current_user
        if user_roles is not None:
            kwargs["user_roles"] = user_roles
        kwargs["is_superuser"] = is_superuser
        # #1319 / ADR-0032 Slice B — thread the full AuthContext so a status
        # transition's `invoke <flow>` runs each effect step scope-enforced as the
        # triggering principal (only a bare `current_user` string survived before).
        auth_ctx = _extra.get("auth_context")
        if auth_ctx is not None:
            kwargs["auth_context"] = auth_ctx
        result = await service.execute(**kwargs)
        if result is None:
            raise HTTPException(status_code=404, detail="Not found")
        return _with_htmx_triggers(
            request, result, entity_name, "updated", redirect_url=_htmx_current_url(request)
        )

    return _wrap_with_auth(
        _core,
        service=service,
        cedar_access_spec=cedar_access_spec,
        auth_dep=auth_dep,
        optional_auth_dep=optional_auth_dep,
        require_auth_by_default=require_auth_by_default,
        operation="update",
        entity_name=entity_name,
        audit_logger=audit_logger,
        include_field_changes=include_field_changes,
        needs_pre_read=True,
        # #1123 — scope: update: enforcement at request time.
        fk_graph=spec.handler.fk_graph,
        admin_personas=spec.handler.admin_personas,
    )


def create_delete_handler(spec: RouteSpec) -> Callable[..., Any]:
    """Create a handler for delete operations with optional Cedar-style access control.

    See :class:`RouteSpec` for the per-route contract (#1011).
    """
    service = spec.service
    include_field_changes = spec.include_field_changes
    auth_dep = spec.handler.auth_dep
    optional_auth_dep = spec.handler.optional_auth_dep
    require_auth_by_default = spec.handler.require_auth_by_default
    entity_name = spec.handler.entity_name
    audit_logger = spec.handler.audit_logger
    cedar_access_spec = spec.handler.cedar_access_spec
    soft_delete_enabled = spec.soft_delete

    async def _core(
        id: UUID,
        request: Request,
        *,
        current_user: str | None = None,
        existing: Any = None,
        **_extra: Any,
    ) -> Any:
        try:
            if soft_delete_enabled:
                # #1218 Option A: stamp deleted_at instead of hard DELETE.
                # `existing` is populated by the `needs_pre_read` wrapper
                # below; if missing (e.g. already tombstoned), the read
                # path's tombstone filter has hidden the row → 404.
                result = await service.execute(
                    operation="update",
                    id=id,
                    data={"deleted_at": datetime.now(UTC)},
                )
            else:
                result = await service.execute(operation="delete", id=id)
        except ValueError as exc:
            # FK constraint violation — entity is referenced by child records.
            # `Repository.delete()` re-raises the psycopg IntegrityError as a
            # ValueError; without this guard it surfaces as an unhandled 500.
            raise HTTPException(status_code=409, detail=str(exc))
        if not result:
            raise HTTPException(status_code=404, detail="Not found")
        return _with_htmx_triggers(
            request,
            {"deleted": True},
            entity_name,
            "deleted",
            redirect_url=_htmx_parent_url(request),
        )

    return _wrap_with_auth(
        _core,
        service=service,
        cedar_access_spec=cedar_access_spec,
        auth_dep=auth_dep,
        optional_auth_dep=optional_auth_dep,
        require_auth_by_default=require_auth_by_default,
        operation="delete",
        entity_name=entity_name,
        audit_logger=audit_logger,
        include_field_changes=include_field_changes,
        needs_pre_read=True,
        # #1123 — scope: delete: enforcement at request time.
        fk_graph=spec.handler.fk_graph,
        admin_personas=spec.handler.admin_personas,
    )


def create_custom_handler(
    service: Any,
    input_schema: type[BaseModel] | None = None,
) -> Callable[..., Any]:
    """Create a handler for custom operations."""
    if input_schema:

        async def handler_with_input(request: Request) -> Any:
            body = await request.json()
            # Pydantic-validated input → Dazzle service layer → parameterized
            # Repository (cursor.execute(sql, params)); no string-built SQL.
            data = input_schema.model_validate(body)
            result = await service.execute(**data.model_dump())  # nosemgrep
            return result

        # Override annotations with the proper type so FastAPI recognizes it
        _set_handler_annotations(handler_with_input)

        return handler_with_input
    else:

        async def handler_no_input() -> Any:
            result = await service.execute()
            return result

        return handler_no_input


# =============================================================================
# Graph helpers (#619 Phase 3–4)
# =============================================================================


def _check_networkx() -> bool:
    """Return True if NetworkX is available."""
    try:
        import networkx  # noqa: F401

        return True
    except ImportError:
        return False


def _extract_domain_filters(request: Any, filter_fields: list[str] | None) -> dict[str, Any]:
    """Extract domain-scope filters from query params for graph algorithms."""
    filters: dict[str, Any] = {}
    if not filter_fields:
        return filters
    reserved = {
        "format",
        "to",
        "weighted",
        "depth",
        "page",
        "page_size",
        "sort",
        "dir",
        "search",
        "q",
    }
    for key, value in request.query_params.items():
        if key in filter_fields and key not in reserved and value:
            filters[key] = value
        elif key.startswith("filter[") and key.endswith("]"):
            field = key[7:-1]
            if field in filter_fields and value:
                filters[field] = value
    return filters


def _build_graph_filter_sql(
    filters: dict[str, Any] | None,
    params: dict[str, Any],
) -> str:
    """Build a WHERE clause from domain-scope filters.

    Uses parameterised placeholders — column names are DSL-derived identifiers
    passed through ``quote_identifier`` for defense-in-depth.
    """
    if not filters:
        return ""
    from dazzle.back.runtime.query_builder import quote_identifier as _qi

    clauses: list[str] = []
    for i, (field, value) in enumerate(filters.items()):
        param_name = f"_f{i}"
        clauses.append(f"{_qi(field)} = %({param_name})s")
        params[param_name] = value
    return " WHERE " + " AND ".join(clauses)


async def _materialize_graph(
    db_manager: Any,
    node_table: str,
    edge_table: str,
    graph_edge_spec: Any,
    filters: dict[str, Any] | None = None,
) -> tuple[Any, list[dict[str, Any]], list[dict[str, Any]]]:
    """Load nodes + edges from DB and build a NetworkX graph.

    Returns (nx_graph, node_dicts, edge_dicts).
    """
    from dazzle.back.runtime.graph_materializer import GraphMaterializer
    from dazzle.back.runtime.query_builder import quote_identifier

    filter_params: dict[str, Any] = {}
    filter_sql: str = _build_graph_filter_sql(filters, filter_params)

    src = graph_edge_spec.source
    tgt = graph_edge_spec.target

    # Table names are DSL-derived identifiers (not user input), but we
    # quote them properly via quote_identifier for defense-in-depth.
    edge_tbl = quote_identifier(edge_table)
    node_tbl = quote_identifier(node_table)

    def _safe_sql(stmt: str) -> str:
        """Identity — inputs are quote_identifier-sanitised DSL names."""
        return stmt

    def _fetch_edges(cursor: Any) -> list[dict[str, Any]]:
        """Execute edge query. Table/column names are DSL-derived identifiers."""
        cursor.execute(_safe_sql("SELECT * FROM " + edge_tbl + filter_sql), filter_params)
        return cursor.fetchall()

    def _fetch_nodes(cursor: Any, ids: tuple[str, ...]) -> list[dict[str, Any]]:
        """Execute node query. Table name is a DSL-derived identifier."""
        cursor.execute(
            _safe_sql("SELECT * FROM " + node_tbl + ' WHERE "id" IN %(node_ids)s'),
            {"node_ids": ids},
        )
        return cursor.fetchall()

    with db_manager.connection() as conn:
        cursor = conn.cursor()

        edges = _fetch_edges(cursor)

        node_ids: set[str] = set()
        for edge in edges:
            if edge.get(src):
                node_ids.add(str(edge[src]))
            if edge.get(tgt):
                node_ids.add(str(edge[tgt]))

        nodes: list[dict[str, Any]] = []
        if node_ids:
            nodes = _fetch_nodes(cursor, tuple(node_ids))

    def _stringify(rows: list) -> list[dict]:  # type: ignore[type-arg]
        result = []
        for row in rows:
            out = {}
            for k, v in row.items():
                out[k] = str(v) if hasattr(v, "hex") else v
            result.append(out)
        return result

    str_nodes = _stringify(nodes)
    str_edges = _stringify(edges)
    materializer = GraphMaterializer(graph_edge=graph_edge_spec)
    return materializer.build(str_nodes, str_edges), str_nodes, str_edges


_VALID_GRAPH_FORMATS = frozenset({"cytoscape", "d3", "raw"})


async def _neighborhood_handler_body(
    seed_id: UUID,
    depth: int,
    format: str,
    entity_name: str,
    graph_edge_spec: Any,
    graph_node_spec: Any | None,
    node_table: str,
    edge_table: str,
    db_manager: Any,
    node_service: Any,
) -> Any:
    """Core logic for the neighborhood graph endpoint."""
    from starlette.responses import JSONResponse

    from dazzle.back.runtime.graph_serializer import GraphSerializer
    from dazzle.back.runtime.neighborhood import NeighborhoodQueryBuilder

    # 1. Validate format
    if format not in _VALID_GRAPH_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid format '{format}'. Must be one of: {', '.join(sorted(_VALID_GRAPH_FORMATS))}",
        )

    # 2. Check seed node exists
    seed_record = await node_service.execute(operation="read", id=seed_id)
    if seed_record is None:
        raise HTTPException(status_code=404, detail=f"{entity_name} not found")

    # 3. Build CTE
    builder = NeighborhoodQueryBuilder(
        node_table=node_table,
        edge_table=edge_table,
        graph_edge=graph_edge_spec,
    )
    cte_sql, cte_params = builder.cte_query(str(seed_id), depth)

    # 4. Execute: CTE → node fetch → edge fetch
    with db_manager.connection() as conn:
        cursor = conn.cursor()

        # Discover reachable node IDs
        cursor.execute(cte_sql, cte_params)
        cte_rows = cursor.fetchall()
        node_ids = [str(row["node_id"]) for row in cte_rows]

        if not node_ids:
            # Seed exists but has no connections — return it alone
            node_ids = [str(seed_id)]

        # Fetch full node records
        node_sql, node_params = builder.node_fetch_query(node_ids)
        cursor.execute(node_sql, node_params)
        nodes = cursor.fetchall()

        # Fetch edges between discovered nodes
        edge_sql, edge_params = builder.edge_fetch_query(node_ids)
        cursor.execute(edge_sql, edge_params)
        edges = cursor.fetchall()

    # 5. Serialize UUIDs to strings
    def _stringify_uuids(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for row in rows:
            out = {}
            for k, v in row.items():
                out[k] = str(v) if isinstance(v, UUID) else v
            result.append(out)
        return result

    nodes = _stringify_uuids(nodes)
    edges = _stringify_uuids(edges)

    # 6. Return via GraphSerializer or raw
    if format == "raw":
        return JSONResponse(content={"nodes": nodes, "edges": edges})

    serializer = GraphSerializer(
        graph_edge=graph_edge_spec,
        graph_node=graph_node_spec,
    )
    if format == "cytoscape":
        return JSONResponse(content=serializer.to_cytoscape(edges, nodes))
    else:
        return JSONResponse(content=serializer.to_d3(edges, nodes))


def create_neighborhood_handler(
    entity_name: str,
    graph_edge_spec: Any,
    graph_node_spec: Any | None,
    node_table: str,
    edge_table: str,
    db_manager: Any,
    node_service: Any,
    optional_auth_dep: Callable[..., Any] | None = None,
    cedar_access_spec: "EntityAccessSpec | None" = None,
    fk_graph: "FKGraph | None" = None,
    ref_targets: dict[str, str] | None = None,
) -> Callable[..., Any]:
    """Create a handler for graph neighborhood traversal (#619 Phase 3).

    Returns reachable nodes and edges from a seed node up to a given depth.
    """
    if optional_auth_dep is not None:

        async def _auth_handler(
            id: UUID,
            auth_context: AuthContext = Depends(optional_auth_dep),
            depth: int = Query(1, ge=1, le=3, description="Traversal depth"),
            format: str = Query("cytoscape", description="Response format: cytoscape, d3, or raw"),
        ) -> Any:
            return await _neighborhood_handler_body(
                seed_id=id,
                depth=depth,
                format=format,
                entity_name=entity_name,
                graph_edge_spec=graph_edge_spec,
                graph_node_spec=graph_node_spec,
                node_table=node_table,
                edge_table=edge_table,
                db_manager=db_manager,
                node_service=node_service,
            )

        _auth_handler.__annotations__ = {
            "id": UUID,
            "auth_context": AuthContext,
            "depth": int,
            "format": str,
            "return": Any,
        }
        return _auth_handler

    async def _noauth_handler(
        id: UUID,
        depth: int = Query(1, ge=1, le=3, description="Traversal depth"),
        format: str = Query("cytoscape", description="Response format: cytoscape, d3, or raw"),
    ) -> Any:
        return await _neighborhood_handler_body(
            seed_id=id,
            depth=depth,
            format=format,
            entity_name=entity_name,
            graph_edge_spec=graph_edge_spec,
            graph_node_spec=graph_node_spec,
            node_table=node_table,
            edge_table=edge_table,
            db_manager=db_manager,
            node_service=node_service,
        )

    _noauth_handler.__annotations__ = {
        "id": UUID,
        "depth": int,
        "format": str,
        "return": Any,
    }
    return _noauth_handler


# =============================================================================
# Algorithm endpoint handlers (#619 Phase 4)
# =============================================================================


def create_shortest_path_handler(
    entity_name: str,
    graph_edge_spec: Any,
    graph_node_spec: Any | None,
    node_table: str,
    edge_table: str,
    db_manager: Any,
    filter_fields: list[str] | None = None,
    optional_auth_dep: Callable[..., Any] | None = None,
) -> Callable[..., Any]:
    """Create handler for GET /{entity}/{id}/graph/shortest-path?to={target_id}."""

    async def _handler(
        request: Request,
        id: UUID,
        to: UUID = Query(..., description="Target node ID"),
        format: str = Query("cytoscape", description="Response format"),
        weighted: bool = Query(False, description="Use edge weights"),
    ) -> Any:
        from starlette.responses import JSONResponse

        from dazzle.back.runtime.graph_algorithms import shortest_path
        from dazzle.back.runtime.graph_serializer import GraphSerializer

        if format not in _VALID_GRAPH_FORMATS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid format. Supported: {', '.join(sorted(_VALID_GRAPH_FORMATS))}",
            )

        filters = _extract_domain_filters(request, filter_fields)
        g, all_nodes, all_edges = await _materialize_graph(
            db_manager,
            node_table,
            edge_table,
            graph_edge_spec,
            filters,
        )

        result = shortest_path(g, source=str(id), target=str(to), weighted=weighted)

        if format == "raw":
            return JSONResponse(content=result)

        path_ids = set(result.get("path", []))
        serializer = GraphSerializer(graph_edge=graph_edge_spec, graph_node=graph_node_spec)

        if not path_ids:
            empty = (
                serializer.to_cytoscape([], [])
                if format == "cytoscape"
                else serializer.to_d3([], [])
            )
            empty["shortest_path"] = result
            return JSONResponse(content=empty)

        path_nodes = [n for n in all_nodes if str(n.get("id")) in path_ids]
        path_edges = [
            e
            for e in all_edges
            if str(e.get(graph_edge_spec.source)) in path_ids
            and str(e.get(graph_edge_spec.target)) in path_ids
        ]

        if format == "cytoscape":
            out = serializer.to_cytoscape(path_edges, path_nodes)
        else:
            out = serializer.to_d3(path_edges, path_nodes)
        out["shortest_path"] = result
        return JSONResponse(content=out)

    _handler.__name__ = f"shortest_path_{entity_name.lower()}"
    return _handler


def create_components_handler(
    entity_name: str,
    graph_edge_spec: Any,
    graph_node_spec: Any | None,
    node_table: str,
    edge_table: str,
    db_manager: Any,
    filter_fields: list[str] | None = None,
    optional_auth_dep: Callable[..., Any] | None = None,
) -> Callable[..., Any]:
    """Create handler for GET /{entity}/graph/components."""

    async def _handler(
        request: Request,
        format: str = Query("raw", description="Response format"),
    ) -> Any:
        from starlette.responses import JSONResponse

        from dazzle.back.runtime.graph_algorithms import connected_components
        from dazzle.back.runtime.graph_serializer import GraphSerializer

        if format not in _VALID_GRAPH_FORMATS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid format. Supported: {', '.join(sorted(_VALID_GRAPH_FORMATS))}",
            )

        filters = _extract_domain_filters(request, filter_fields)
        g, all_nodes, all_edges = await _materialize_graph(
            db_manager,
            node_table,
            edge_table,
            graph_edge_spec,
            filters,
        )

        result = connected_components(g)

        if format == "raw":
            return JSONResponse(content=result)

        serializer = GraphSerializer(graph_edge=graph_edge_spec, graph_node=graph_node_spec)
        if format == "cytoscape":
            out = serializer.to_cytoscape(all_edges, all_nodes)
        else:
            out = serializer.to_d3(all_edges, all_nodes)
        out["components"] = result
        return JSONResponse(content=out)

    _handler.__name__ = f"components_{entity_name.lower()}"
    return _handler


# =============================================================================
# Route Generator
# =============================================================================


class RouteGenerator:
    """
    Generates FastAPI routes from endpoint specifications.

    Creates routes with appropriate HTTP methods, paths, and handlers.
    """

    def __init__(
        self,
        services: dict[str, Any],
        models: dict[str, type[BaseModel]],
        schemas: dict[str, dict[str, type[BaseModel]]] | None = None,
        entity_access_specs: dict[str, dict[str, Any]] | None = None,
        auth_dep: Callable[..., Any] | None = None,
        optional_auth_dep: Callable[..., Any] | None = None,
        require_auth_by_default: bool = False,
        auth_store: Any | None = None,
        audit_logger: "AuditLogger | None" = None,
        cedar_access_specs: "dict[str, EntityAccessSpec] | None" = None,
        entity_list_projections: dict[str, list[str]] | None = None,
        entity_search_fields: dict[str, list[str]] | None = None,
        entity_filter_fields: dict[str, list[str]] | None = None,
        entity_auto_includes: dict[str, list[str]] | None = None,
        entity_htmx_meta: dict[str, dict[str, Any]] | None = None,
        entity_audit_configs: dict[str, Any] | None = None,
        entity_ref_targets: dict[str, dict[str, str]] | None = None,
        fk_graph: "FKGraph | None" = None,
        entity_graph_specs: dict[str, tuple[Any, Any | None]] | None = None,
        node_graph_specs: dict[str, dict[str, Any]] | None = None,
        entity_display_fields: dict[str, str] | None = None,
        db_manager: Any | None = None,
        entity_storage_bindings: dict[str, dict[str, tuple[str, ...]]] | None = None,
        entity_soft_delete: dict[str, bool] | None = None,
        admin_personas: list[str] | None = None,
        security_profile: str = "basic",
    ):
        """
        Initialize the route generator.

        Args:
            services: Dictionary mapping service names to service instances
            models: Dictionary mapping entity names to Pydantic models
            schemas: Optional dictionary with create/update schemas per entity
            entity_access_specs: Optional dictionary mapping entity names to access specs
            auth_dep: FastAPI dependency that requires authentication (raises 401)
            optional_auth_dep: FastAPI dependency for optional auth (returns empty AuthContext)
            require_auth_by_default: If True, require auth for all routes when no access spec
            auth_store: AuthStore instance for creating per-route role-based dependencies
            audit_logger: Optional AuditLogger for recording access decisions
            cedar_access_specs: Optional dict of entity_name -> EntityAccessSpec for Cedar evaluation
            entity_list_projections: Optional dict mapping entity names to projected field lists
            entity_auto_includes: Optional dict mapping entity names to auto-eager-loaded relations
            entity_htmx_meta: Optional dict mapping entity names to HTMX rendering metadata
            entity_audit_configs: Optional dict of entity_name -> AuditConfig for per-entity filtering
            entity_ref_targets: Optional dict mapping entity_name -> {fk_field: target_entity} for
                dotted-path scope resolution (#556)
            fk_graph: Optional FKGraph from the linked AppSpec for predicate compilation
            node_graph_specs: Optional dict mapping node entity names to graph metadata (#619)
            db_manager: Optional database manager for neighborhood queries (#619)
        """
        self.services = services
        self.models = models
        self.schemas = schemas or {}
        self.entity_access_specs = entity_access_specs or {}
        self.auth_dep = auth_dep
        self.optional_auth_dep = optional_auth_dep
        self.require_auth_by_default = require_auth_by_default
        self.auth_store = auth_store
        self.audit_logger = audit_logger
        self.cedar_access_specs = cedar_access_specs or {}
        self.entity_list_projections = entity_list_projections or {}
        self.entity_search_fields = entity_search_fields or {}
        self.entity_filter_fields = entity_filter_fields or {}
        self.entity_auto_includes = entity_auto_includes or {}
        self.entity_htmx_meta = entity_htmx_meta or {}
        self.entity_audit_configs = entity_audit_configs or {}
        self.entity_ref_targets = entity_ref_targets or {}
        self.fk_graph = fk_graph
        self.entity_graph_specs = entity_graph_specs or {}
        self.node_graph_specs = node_graph_specs or {}
        # #928: per-entity display_field map. Used by `_list_handler_body`
        # to inject `__display__` on top-level list responses so FK
        # `<select>` widgets show the human-readable label (component_name,
        # title, etc.) instead of the UUID PK. Mirrors the per-row
        # injection that `relation_loader` does when eager-loading FKs.
        self.entity_display_fields = entity_display_fields or {}
        self.db_manager = db_manager
        # #932 cycle 4: per-entity storage-bound field map. Empty dict
        # for entities without `field foo: file storage=<name>` bindings;
        # the create/update handlers no-op cheaply in that case.
        self.entity_storage_bindings = entity_storage_bindings or {}
        # #1218 Option A: per-entity soft_delete flag. DELETE handlers
        # for entities marked True stamp `deleted_at` instead of
        # issuing a hard DELETE; the read-path tombstone filter on
        # Repository.list/read/aggregate hides those rows.
        self.entity_soft_delete = entity_soft_delete or {}
        # #957 cycle 6: tenant-admin personas drawn from
        # `appspec.tenancy.admin_personas`. Threaded into list handlers
        # so the predicate compiler can short-circuit the scope filter
        # when the active user matches one of them.
        self.admin_personas: list[str] = list(admin_personas or [])
        # #1196: the active security profile drives the per-route rate-limit
        # wrap in `_add_route`. On "basic" (or when slowapi is absent) the
        # rate_limit module's _NoOpLimiter makes the decorator a no-op, so the
        # wrap is safe to apply unconditionally.
        self.security_profile: str = security_profile
        # Cycle 249 (EX-049): persona-backed entity map.
        # Maps entity_name → (persona_id, link_via) for each persona that
        # declares ``backed_by``. Built by the caller from appspec.personas.
        self.persona_backed_entities: dict[str, tuple[str, str]] = {}
        self._router = _APIRouter()

    def generate_route(
        self,
        endpoint: EndpointSpec,
        service_spec: ServiceSpec | None = None,
    ) -> None:
        """
        Generate a single route from an endpoint specification.

        Args:
            endpoint: Endpoint specification
            service_spec: Optional service specification for type hints
        """
        service = self.services.get(endpoint.service)
        if not service:
            raise ValueError(f"Service not found: {endpoint.service}")

        # Determine entity name for schemas
        entity_name = None
        is_crud_service = False

        if service_spec:
            entity_name = service_spec.domain_operation.entity
            is_crud_service = service_spec.is_crud

        # Get schemas for the entity
        entity_schemas = self.schemas.get(entity_name or "", {})
        model = self.models.get(entity_name or "")

        # For CRUD services, determine operation from HTTP method
        # For non-CRUD services, use the service's domain_operation.kind
        operation_kind = None
        if service_spec and not is_crud_service:
            operation_kind = service_spec.domain_operation.kind

        # Create appropriate handler based on HTTP method (primary) or operation kind (secondary)
        handler: Callable[..., Any]

        # Derive entity slug for post-create redirect
        _entity_slug = (entity_name or "").lower().replace("_", "-")

        # Resolve audit logger and Cedar access spec for this entity
        _cedar_spec = self.cedar_access_specs.get(entity_name or "")
        _audit_config = self.entity_audit_configs.get(entity_name or "")
        # Per-entity audit gate: if entity has an AuditConfig, respect its
        # `enabled` flag. Entities with Cedar access specs always get audit
        # logging (access-decision logging). Entities with no audit config
        # and no Cedar spec get no logging.
        _audit_enabled = False
        if _audit_config and getattr(_audit_config, "enabled", False):
            _audit_enabled = True
        elif _cedar_spec is not None:
            # Cedar entities always log access decisions
            _audit_enabled = True
        _audit = self.audit_logger if _audit_enabled else None
        # Pre-compute which operations this entity wants audited (empty = all)
        _audit_ops: set[str] = set()
        if _audit_config and getattr(_audit_config, "operations", None):
            _audit_ops = {str(op) for op in _audit_config.operations}
        # Check whether to capture field-level diffs for update/delete
        _include_fc = bool(_audit_config and getattr(_audit_config, "include_field_changes", False))

        def _audit_for(op: str) -> Any:
            """Return the audit logger if this operation should be audited."""
            if _audit is None:
                return None
            if _audit_ops and op not in _audit_ops:
                return None
            return _audit

        # Base HandlerConfig shared across CRUD verbs in this dispatch.
        # audit_logger is overridden per-verb via dataclasses.replace
        # since each operation gates audit independently (#1011).
        _base_config = HandlerConfig(
            auth_dep=self.auth_dep,
            optional_auth_dep=self.optional_auth_dep,
            require_auth_by_default=self.require_auth_by_default,
            entity_name=entity_name or "Item",
            cedar_access_spec=_cedar_spec,
            fk_graph=self.fk_graph,
            admin_personas=self.admin_personas,
        )

        # POST -> CREATE
        if endpoint.method == HttpMethod.POST or operation_kind == OperationKind.CREATE:
            create_schema = entity_schemas.get("create", model)
            if create_schema:
                # Identify ref-User fields on this entity for current_user
                # auto-injection (manwithacat/dazzle#774). `entity_ref_targets` already maps
                # fk_field -> target_entity_name; we filter to targets whose
                # name is exactly "User".
                _refs = self.entity_ref_targets.get(entity_name or "", {})
                _user_ref_fields = [
                    fk_field for fk_field, target in _refs.items() if target == "User"
                ]
                # Cycle 249 (EX-049): build persona_ref_map for backed_by auto-injection.
                # For each ref field that targets a persona-backed entity, record
                # the link_via + repository so the create handler can do the async
                # lookup at request time.
                _persona_ref_map: dict[str, tuple[str, str, Any]] | None = None
                _backed = getattr(self, "persona_backed_entities", None) or {}
                if _backed:
                    _prm: dict[str, tuple[str, str, Any]] = {}
                    for fk_field, target in _refs.items():
                        if target in _backed and target != "User":
                            _persona_id, _link_via = _backed[target]
                            _target_repo = self.services.get(target)
                            if _target_repo:
                                _prm[fk_field] = (target, _link_via, _target_repo)
                    _persona_ref_map = _prm or None

                handler = create_create_handler(
                    RouteSpec(
                        handler=replace(_base_config, audit_logger=_audit_for("create")),
                        service=service,
                        input_schema=create_schema,
                        response_schema=model,
                        storage_bindings=self.entity_storage_bindings.get(entity_name or "")
                        or None,
                    ),
                    entity_slug=_entity_slug,
                    user_ref_fields=_user_ref_fields or None,
                    persona_ref_map=_persona_ref_map,
                )
                self._add_route(endpoint, handler, response_model=model)
            else:
                raise ValueError(f"No create schema for endpoint: {endpoint.name}")

        # GET with {id} -> READ
        elif (
            endpoint.method == HttpMethod.GET and "{id}" in endpoint.path
        ) or operation_kind == OperationKind.READ:
            includes = self.entity_auto_includes.get(entity_name or "")
            handler = create_read_handler(
                RouteSpec(
                    handler=replace(_base_config, audit_logger=_audit_for("read")),
                    service=service,
                    response_schema=model,
                    auto_include=includes,
                )
            )
            self._add_route(endpoint, handler, response_model=None)

        # GET without {id} -> LIST
        elif (
            endpoint.method == HttpMethod.GET and "{id}" not in endpoint.path
        ) or operation_kind == OperationKind.LIST:
            # Get access spec for this entity
            access_spec = self.entity_access_specs.get(entity_name or "")
            # Get field projection for this entity (from view-backed list surfaces)
            projection = self.entity_list_projections.get(entity_name or "")
            # Get search fields for this entity (from surface config)
            _search_fields = self.entity_search_fields.get(entity_name or "")
            # Get filter fields for this entity (from surface UX config)
            _filter_fields = self.entity_filter_fields.get(entity_name or "")
            # Get auto-include refs for this entity (prevents N+1 queries)
            includes = self.entity_auto_includes.get(entity_name or "")
            # Get HTMX rendering metadata (columns, detail URL, etc.)
            _htmx = self.entity_htmx_meta.get(entity_name or "", {})
            # Get graph metadata for edge entities (#619 Phase 2)
            _graph_spec = self.entity_graph_specs.get(entity_name or "")
            handler = create_list_handler(
                RouteSpec(
                    handler=replace(_base_config, audit_logger=_audit_for("list")),
                    service=service,
                    response_schema=model,
                    auto_include=includes,
                ),
                access_spec=access_spec,
                select_fields=projection,
                json_projection=projection,
                htmx_columns=_htmx.get("columns"),
                htmx_detail_url=_htmx.get("detail_url"),
                htmx_entity_name=_htmx.get("entity_name", entity_name or "Item"),
                htmx_empty_message=_htmx.get("empty_message", "No items found."),
                search_fields=_search_fields,
                filter_fields=_filter_fields,
                ref_targets=self.entity_ref_targets.get(entity_name or ""),
                fk_graph=self.fk_graph,
                graph_spec=_graph_spec,
                all_services=self.services,
                display_field=self.entity_display_fields.get(entity_name or ""),
                admin_personas=self.admin_personas,
            )
            self._add_route(endpoint, handler, response_model=None)

            # Register /graph neighborhood endpoint for graph_node entities (#619)
            _node_graph = self.node_graph_specs.get(entity_name or "")
            if _node_graph:
                _graph_path = endpoint.path.rstrip("/") + "/{id}/graph"
                _graph_handler = create_neighborhood_handler(
                    entity_name=entity_name or "Item",
                    graph_edge_spec=_node_graph["graph_edge"],
                    graph_node_spec=_node_graph.get("graph_node"),
                    node_table=_node_graph["node_table"],
                    edge_table=_node_graph["edge_table"],
                    db_manager=self.db_manager,
                    node_service=service,
                    optional_auth_dep=self.optional_auth_dep,
                    cedar_access_spec=_cedar_spec,
                    fk_graph=self.fk_graph,
                    ref_targets=self.entity_ref_targets.get(entity_name or ""),
                )
                self._router.add_api_route(
                    _graph_path,
                    _graph_handler,
                    methods=["GET"],
                    tags=[entity_name or "Item"],
                    summary=f"Neighborhood graph for {entity_name}",
                )

            # Register algorithm endpoints for graph_node entities (#619 Phase 4)
            if _node_graph and _check_networkx():
                _alg_filter_fields = self.entity_filter_fields.get(entity_name or "")

                # Shortest path: /{entity}/{id}/graph/shortest-path
                _sp_path = endpoint.path.rstrip("/") + "/{id}/graph/shortest-path"
                _sp_handler = create_shortest_path_handler(
                    entity_name=entity_name or "Item",
                    graph_edge_spec=_node_graph["graph_edge"],
                    graph_node_spec=_node_graph.get("graph_node"),
                    node_table=_node_graph["node_table"],
                    edge_table=_node_graph["edge_table"],
                    db_manager=self.db_manager,
                    filter_fields=_alg_filter_fields,
                    optional_auth_dep=self.optional_auth_dep,
                )
                self._router.add_api_route(
                    _sp_path,
                    _sp_handler,
                    methods=["GET"],
                    tags=[entity_name or "Item"],
                    summary=f"Shortest path for {entity_name}",
                )

                # Connected components: /{entity}/graph/components
                _cc_path = endpoint.path.rstrip("/") + "/graph/components"
                _cc_handler = create_components_handler(
                    entity_name=entity_name or "Item",
                    graph_edge_spec=_node_graph["graph_edge"],
                    graph_node_spec=_node_graph.get("graph_node"),
                    node_table=_node_graph["node_table"],
                    edge_table=_node_graph["edge_table"],
                    db_manager=self.db_manager,
                    filter_fields=_alg_filter_fields,
                    optional_auth_dep=self.optional_auth_dep,
                )
                self._router.add_api_route(
                    _cc_path,
                    _cc_handler,
                    methods=["GET"],
                    tags=[entity_name or "Item"],
                    summary=f"Connected components for {entity_name}",
                )

        # PUT/PATCH -> UPDATE
        elif (
            endpoint.method in (HttpMethod.PUT, HttpMethod.PATCH)
            or operation_kind == OperationKind.UPDATE
        ):
            update_schema = entity_schemas.get("update", model)
            if update_schema:
                handler = create_update_handler(
                    RouteSpec(
                        handler=replace(_base_config, audit_logger=_audit_for("update")),
                        service=service,
                        input_schema=update_schema,
                        response_schema=model,
                        include_field_changes=_include_fc,
                        storage_bindings=self.entity_storage_bindings.get(entity_name or "")
                        or None,
                    )
                )
                self._add_route(endpoint, handler, response_model=model)
            else:
                raise ValueError(f"No update schema for endpoint: {endpoint.name}")

        # DELETE -> DELETE
        elif endpoint.method == HttpMethod.DELETE or operation_kind == OperationKind.DELETE:
            handler = create_delete_handler(
                RouteSpec(
                    handler=replace(_base_config, audit_logger=_audit_for("delete")),
                    service=service,
                    include_field_changes=_include_fc,
                    soft_delete=self.entity_soft_delete.get(entity_name or "", False),
                )
            )
            self._add_route(endpoint, handler, response_model=None)

        else:
            # Custom operation
            handler = create_custom_handler(service)
            self._add_route(endpoint, handler, response_model=None)

    def _add_route(
        self,
        endpoint: EndpointSpec,
        handler: Callable[..., Any],
        response_model: type[BaseModel] | None = None,
    ) -> None:
        """Add a route to the router."""
        # Map HTTP methods to router methods
        method_map = {
            HttpMethod.GET: self._router.get,
            HttpMethod.POST: self._router.post,
            HttpMethod.PUT: self._router.put,
            HttpMethod.PATCH: self._router.patch,
            HttpMethod.DELETE: self._router.delete,
        }

        router_method = method_map.get(endpoint.method)
        if not router_method:
            raise ValueError(f"Unsupported HTTP method: {endpoint.method}")

        # Detail / update / delete routes register their `{id}` segment
        # with Starlette's `uuid` path convertor. A literal segment like
        # `create` is not uuid-shaped, so it simply won't match the
        # detail route and falls through — no sentinel guard route
        # needed (this retired the `_create_guard` hack from #598).
        # Dazzle entity PKs are uuids and the generated handlers already
        # type `id: UUID`, so the convertor and the signature agree.
        path = endpoint.path.replace("{id}", "{id:uuid}")

        # Build route decorator kwargs
        route_kwargs: dict[str, Any] = {
            "summary": endpoint.description or endpoint.name,
            "tags": endpoint.tags or [],
        }

        if response_model:
            route_kwargs["response_model"] = response_model

        # Add role-based dependencies (RBAC)
        dependencies: list[Any] = []
        if endpoint.require_roles and self.auth_store:
            from dazzle.back.runtime.auth import create_auth_dependency

            role_dep = create_auth_dependency(self.auth_store, require_roles=endpoint.require_roles)
            dependencies.append(Depends(role_dep))

        if endpoint.deny_roles and self.auth_store:
            from dazzle.back.runtime.auth import create_deny_dependency

            deny_dep = create_deny_dependency(self.auth_store, deny_roles=endpoint.deny_roles)
            dependencies.append(Depends(deny_dep))

        if dependencies:
            route_kwargs["dependencies"] = dependencies

        # #1196: apply the active security profile's API rate limit to every
        # generated entity route. `rate_limit.limits.api_limit` is set by
        # `apply_rate_limiting(app, profile)` at server boot; on the "basic"
        # profile (or when slowapi is absent) the limiter is a no-op stub, so
        # the wrap is backward-safe — no behaviour change on `basic`.
        from dazzle.back.runtime import rate_limit as _rl

        handler = _rl.limits.limiter.limit(_rl.limits.api_limit)(handler)  # type: ignore[misc,untyped-decorator,unused-ignore]

        # Add the route
        router_method(path, **route_kwargs)(handler)

    def generate_all_routes(
        self,
        endpoints: list[EndpointSpec],
        service_specs: dict[str, ServiceSpec] | None = None,
        claimed_routes: set[tuple[str, str]] | None = None,
    ) -> APIRouter:
        """
        Generate routes for all endpoints.

        Endpoints are sorted so that static paths are registered before
        parameterized paths at the same depth.  This prevents FastAPI from
        matching a path parameter (e.g. ``{id}``) against a literal segment
        like ``create`` — the same strategy used by the UI page router.

        Args:
            endpoints: List of endpoint specifications
            service_specs: Optional dictionary mapping service names to specs
            claimed_routes: ``(method, path)`` pairs already mounted by a
                project override or extension router. Endpoints matching one
                of these are skipped — the override is the intended handler
                and the generic CRUD mount would only trip the conflict
                warning on every boot (#1101).

        Returns:
            FastAPI router with all routes
        """
        service_specs = service_specs or {}
        claimed_routes = claimed_routes or set()

        from dazzle.perf.tracer import dazzle_span

        with dazzle_span("route.gen", endpoint_count=len(endpoints)):
            # Detail routes register as `/{plural}/{id:uuid}` (see
            # `_add_route`), so a literal segment like `create` can't be
            # mistaken for an `{id}` — it doesn't match the uuid
            # convertor and falls through to a clean router 404. The old
            # `_create_guard` sentinel routes (#598) are no longer
            # needed and have been removed.

            def _route_sort_key(ep: EndpointSpec) -> tuple[int, int]:
                # More segments first, then static before dynamic at same depth.
                return (-ep.path.count("/"), 0 if "{" not in ep.path else 1)

            # #1140: backstop dedup. AegisMark hit a case where AssessmentEvent
            # (referenced by both an `analytics:` block and regular workspace
            # surfaces) produced two `EndpointSpec` entries for each of GET
            # /assessmentevents and POST /assessmentevents, so the CRUD list +
            # create handlers double-registered. Tracking emitted (method, path)
            # here catches the duplicate regardless of upstream cause — the
            # generic CRUD shape doesn't accept two different handlers for the
            # same operation anyway.
            emitted: set[tuple[str, str]] = set()
            for endpoint in sorted(endpoints, key=_route_sort_key):
                method = (
                    endpoint.method.value
                    if hasattr(endpoint.method, "value")
                    else str(endpoint.method)
                )
                if (method, endpoint.path) in claimed_routes:
                    logger.info(
                        "Skipping generic CRUD %s %s — already provided by a project override",
                        method,
                        endpoint.path,
                    )
                    continue
                if (method, endpoint.path) in emitted:
                    logger.warning(
                        "Skipping duplicate CRUD endpoint %s %s — already emitted earlier "
                        "in this generate_all_routes pass (#1140). Check upstream endpoint "
                        "discovery for double-visitation.",
                        method,
                        endpoint.path,
                    )
                    continue
                emitted.add((method, endpoint.path))
                service_spec = service_specs.get(endpoint.service)
                self.generate_route(endpoint, service_spec)

        return self._router

    @property
    def router(self) -> APIRouter:
        """Get the generated router."""
        return self._router


# =============================================================================
# Convenience Functions
# =============================================================================


def generate_crud_routes(
    entity_name: str,
    service: Any,
    model: type[BaseModel],
    create_schema: type[BaseModel],
    update_schema: type[BaseModel],
    prefix: str | None = None,
    tags: list[str | Enum] | None = None,
) -> APIRouter:
    """
    Generate standard CRUD routes for an entity.

    This is a convenience function for quickly creating RESTful routes.

    Args:
        entity_name: Name of the entity
        service: CRUD service instance
        model: Pydantic model for the entity
        create_schema: Schema for create operations
        update_schema: Schema for update operations
        prefix: Optional URL prefix (defaults to /entity_name)
        tags: Optional tags for grouping in OpenAPI docs

    Returns:
        FastAPI router with CRUD routes
    """
    router = _APIRouter()
    prefix = prefix or f"/{to_api_plural(entity_name)}"
    tags = tags or [entity_name]

    # List
    @router.get(prefix, tags=tags, summary=f"List {entity_name}s")
    async def list_items(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
    ) -> Any:
        return await service.execute(operation="list", page=page, page_size=page_size)

    # Read
    @router.get(f"{prefix}/{{id}}", tags=tags, summary=f"Get {entity_name}", response_model=model)
    async def get_item(id: UUID) -> Any:
        result = await service.execute(operation="read", id=id)
        if result is None:
            raise HTTPException(status_code=404, detail="Not found")
        return result

    # Create
    @router.post(prefix, tags=tags, summary=f"Create {entity_name}", response_model=model)
    async def create_item(request: Request, data: create_schema) -> Any:
        result = await service.execute(operation="create", data=data)
        return _with_htmx_triggers(request, result, entity_name, "created")

    # Update
    @router.put(
        f"{prefix}/{{id}}", tags=tags, summary=f"Update {entity_name}", response_model=model
    )
    async def update_item(id: UUID, request: Request, data: update_schema) -> Any:
        result = await service.execute(operation="update", id=id, data=data)
        if result is None:
            raise HTTPException(status_code=404, detail="Not found")
        return _with_htmx_triggers(
            request, result, entity_name, "updated", redirect_url=_htmx_current_url(request)
        )

    # Delete
    @router.delete(f"{prefix}/{{id}}", tags=tags, summary=f"Delete {entity_name}")
    async def delete_item(id: UUID, request: Request) -> Any:
        try:
            result = await service.execute(operation="delete", id=id)
        except ValueError as exc:
            # FK constraint violation — entity is referenced by child records
            raise HTTPException(status_code=409, detail=str(exc))
        if not result:
            raise HTTPException(status_code=404, detail="Not found")
        return _with_htmx_triggers(
            request,
            {"deleted": True},
            entity_name,
            "deleted",
            redirect_url=_htmx_parent_url(request),
        )

    # Patch field — inline edit support for data tables
    @router.patch(
        f"{prefix}/{{entity_id}}/field/{{field_name}}",
        tags=tags,
        summary=f"Update a single field on {entity_name}",
    )
    async def patch_field(entity_id: UUID, field_name: str, request: Request) -> Any:
        # Validate: reject protected / computed fields
        _PROTECTED_FIELDS = {"id", "created_at", "updated_at"}
        if field_name in _PROTECTED_FIELDS or field_name.endswith("_id"):
            raise HTTPException(
                status_code=422,
                detail=f"Field '{field_name}' is not inline-editable",
            )

        # Validate: field must exist on the model
        model_fields = set(model.model_fields.keys()) if hasattr(model, "model_fields") else set()
        if model_fields and field_name not in model_fields:
            raise HTTPException(
                status_code=422,
                detail=f"Field '{field_name}' does not exist on {entity_name}",
            )

        # Parse form body
        form_data = await request.form()
        value = form_data.get("value")

        result = await service.execute(
            operation="update",
            id=entity_id,
            data={field_name: value},
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Not found")

        # Return the new value as plain text; the template handles rendering
        updated_value = (
            result.get(field_name, "")
            if isinstance(result, dict)
            else getattr(result, field_name, "")
        )
        return PlainTextResponse(content=str(updated_value) if updated_value is not None else "")

    # Bulk delete — batch removal for data table bulk actions
    @router.post(
        f"{prefix}/bulk-delete",
        tags=tags,
        summary=f"Bulk delete {entity_name} records",
    )
    async def bulk_delete(request: Request) -> Any:
        body = await request.json()
        ids: list[Any] = body.get("ids", [])
        if not ids:
            return JSONResponse({"error": "No IDs provided"}, status_code=422)

        deleted = 0
        for item_id in ids:
            # Skip items the user cannot access or that no longer exist (#smells-1.1).
            with suppress(Exception):
                await service.execute(operation="delete", id=item_id)
                deleted += 1

        return JSONResponse({"deleted": deleted, "total": len(ids)})

    return router
