"""Route generator — generates FastAPI route handlers from EndpointSpec.

SECTION MAP (line anchors approximate — use them to jump directly to a
section rather than scanning the file):

  L 150  Contracts          HandlerConfig, RouteSpec (shared CRUD bundle)
  L 255  Request utils      _set_handler_annotations, _is_htmx_request,
                             _wants_html, _forbidden_detail,
                             _htmx_current_url, _htmx_parent_url
  L 300  Access helpers     _normalize_role (shared by audit_wrap,
                             scope_filters, workspace builders, list path)
  L 315  Result utils       _extract_result_id (shared by audit_wrap +
                             the create handler)
  L 325  RouteGenerator     Primary class — wires all factories into APIRouter
  L 880  Convenience        generate_crud_routes (thin wrapper)

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

The CRUD + graph handler factories themselves (create_list_handler /
_list_handler_body / _is_field_condition; create_read_handler;
create_create_handler / create_update_handler / create_delete_handler /
create_custom_handler / _parse_request_body / resolve_backed_entity_refs /
inject_current_user_refs; and the graph family _check_networkx /
_extract_domain_filters / _build_graph_filter_sql / _materialize_graph /
_VALID_GRAPH_FORMATS / _neighborhood_handler_body /
create_neighborhood_handler / create_shortest_path_handler /
create_components_handler) moved to the handlers/ package (#1361 final
slice — list_handlers.py, read_handlers.py, write_handlers.py,
graph_handlers.py); the names are re-imported above for back-compat and
RouteGenerator resolves the factories through this module's namespace.

Closes #1066. Section map added to cut agent repeat-reads; introduced
after `scripts/stall_log_mine.py` flagged this file as friction-148
(135 repeat reads, 4-line docstring).
"""

import logging
from collections.abc import Callable
from contextlib import suppress
from dataclasses import replace
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter as _APIRouter
from fastapi import Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

from dazzle.core.strings import entity_slug, to_api_plural

# Audit context + access logging + auth wrapping live in audit_wrap.py
# (#1361 slice 3). Same re-import contract as scope_filters / htmx_render
# below: handler-factory call sites in this module plus
# `route_generator.<name>` importers and patch points keep resolving here.
from dazzle.http.runtime.audit_wrap import (  # noqa: F401  (re-exported for back-compat importers)
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

# CRUD + graph handler factories live in the handlers/ package (#1361 final
# slice). Same re-import contract as scope_filters / htmx_render / audit_wrap:
# the RouteGenerator call sites below plus `route_generator.<name>` importers
# and patch points keep resolving here. handlers/* are leaf modules — they
# import route_generator only lazily inside function bodies, so these
# module-level imports are acyclic.
from dazzle.http.runtime.handlers.graph_handlers import (  # noqa: F401  (re-exported for back-compat importers)
    _VALID_GRAPH_FORMATS,
    _build_graph_filter_sql,
    _check_networkx,
    _extract_domain_filters,
    _materialize_graph,
    _neighborhood_handler_body,
    create_components_handler,
    create_neighborhood_handler,
    create_shortest_path_handler,
)
from dazzle.http.runtime.handlers.list_handlers import (  # noqa: F401  (re-exported for back-compat importers)
    _is_field_condition,
    _list_handler_body,
    create_list_handler,
)
from dazzle.http.runtime.handlers.read_handlers import (  # noqa: F401  (re-exported for back-compat importers)
    create_read_handler,
)
from dazzle.http.runtime.handlers.write_handlers import (  # noqa: F401  (re-exported for back-compat importers)
    _parse_request_body,
    create_create_handler,
    create_custom_handler,
    create_delete_handler,
    create_update_handler,
    inject_current_user_refs,
    resolve_backed_entity_refs,
)

# Inline HTMX/HTML response rendering lives in htmx_render.py (#1361 slice 2).
# Same re-import contract as scope_filters below: handler call sites in this
# module plus `route_generator.<name>` importers and patch points keep
# resolving here.
from dazzle.http.runtime.htmx_render import (  # noqa: F401  (re-exported for back-compat importers)
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
from dazzle.http.runtime.http_errors import require_found

# Scope / row-RBAC filter resolution lives in scope_filters.py (#1361 slice 1).
# The names are re-imported at module level so existing
# `route_generator.<name>` references (handler call sites below, plus tests
# that import or patch.object through this namespace) keep resolving here.
from dazzle.http.runtime.scope_filters import (  # noqa: F401  (re-exported for back-compat importers)
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
from dazzle.http.specs.endpoint import EndpointSpec, HttpMethod
from dazzle.http.specs.service import OperationKind, ServiceSpec

if TYPE_CHECKING:
    from dazzle.core.ir.fk_graph import FKGraph
    from dazzle.http.runtime.audit_log import AuditLogger
    from dazzle.http.specs.auth import EntityAccessSpec

logger = logging.getLogger(__name__)

# Expose APIRouter name for return-type annotations (the real class is
# imported as _APIRouter to allow a None fallback when FastAPI is absent).
APIRouter = _APIRouter


# CRUD route-dispatch contracts (HandlerConfig, RouteSpec) + request/role/result
# helpers moved to the route_support LEAF (smells round 2026-06-20) so the satellite
# modules (scope_filters, audit_wrap, htmx_render, handlers/*) import DOWN into the
# leaf instead of back UP into this module — breaking the import cycle that forced
# ~18 in-function imports. Re-exported here so `route_generator.<name>` keeps resolving
# for back-compat importers and patch points.
from dazzle.http.runtime.route_support import (  # noqa: E402, F401  (re-exported for back-compat importers + patch points; route_support declares __all__)
    HandlerConfig,
    RouteSpec,
    _extract_result_id,
    _forbidden_detail,
    _htmx_current_url,
    _htmx_parent_url,
    _is_htmx_request,
    _normalize_role,
    _set_handler_annotations,
    _wants_html,
)

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
        # #1422: per-entity in-process CREATE invokers (the cedar create handler's
        # `_inprocess_create`), so the experience-form POST mutates in-process via
        # the SAME enforced create path instead of self-fetching the REST endpoint.
        self.create_invokers: dict[str, Any] = {}
        # ADR-0039 D3b (#778/#1398): when the `User` entity declares `auth_identity:`,
        # this holds its `link_via` so `ref User` create-injection resolves the domain
        # `User` row by the link (e.g. email) instead of assuming domain id == auth id
        # (#774). None = no binding → keep the #774 auth-id injection (D5). Set by the
        # caller from `appspec.domain` after construction.
        self.auth_identity_user_link: str | None = None
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
        _entity_slug = entity_slug(entity_name or "")

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
                _prm: dict[str, tuple[str, str, Any]] = {}
                _backed = getattr(self, "persona_backed_entities", None) or {}
                if _backed:
                    for fk_field, target in _refs.items():
                        if target in _backed and target != "User":
                            _persona_id, _link_via = _backed[target]
                            _target_repo = self.services.get(target)
                            if _target_repo:
                                _prm[fk_field] = (target, _link_via, _target_repo)
                # ADR-0039 D3b (#778/#1398): when `User` declares `auth_identity:`, resolve
                # `ref User` create-injection by the declared link (e.g. email) — inject the
                # domain `User` row's own id, not the auth id (#774's domain-id == auth-id
                # assumption). Route these fields through the same link-resolution as backed
                # entities and drop them from the auth-id `_user_ref_fields` path so they
                # aren't double-injected. Undeclared `User` keeps #774 (D5).
                _user_link = getattr(self, "auth_identity_user_link", None)
                if _user_link is not None and _user_ref_fields:
                    _user_repo = self.services.get("User")
                    if _user_repo is not None:
                        for fk_field in _user_ref_fields:
                            _prm[fk_field] = ("User", _user_link, _user_repo)
                        _user_ref_fields = []
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
                # #1422: register the in-process create invoker. Every create
                # handler variant (cedar / auth / noauth) now exposes
                # `_inprocess_create`, so every create route registers an invoker
                # and the experience-form POST never needs the loopback self-fetch.
                _inproc = getattr(handler, "_inprocess_create", None)
                if entity_name and _inproc is not None:
                    self.create_invokers[entity_name] = _inproc
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
            from dazzle.http.runtime.auth import create_auth_dependency

            role_dep = create_auth_dependency(self.auth_store, require_roles=endpoint.require_roles)
            dependencies.append(Depends(role_dep))

        if endpoint.deny_roles and self.auth_store:
            from dazzle.http.runtime.auth import create_deny_dependency

            deny_dep = create_deny_dependency(self.auth_store, deny_roles=endpoint.deny_roles)
            dependencies.append(Depends(deny_dep))

        if dependencies:
            route_kwargs["dependencies"] = dependencies

        # #1196: apply the active security profile's API rate limit to every
        # generated entity route. `rate_limit.limits.api_limit` is set by
        # `apply_rate_limiting(app, profile)` at server boot; on the "basic"
        # profile (or when slowapi is absent) the limiter is a no-op stub, so
        # the wrap is backward-safe — no behaviour change on `basic`.
        from dazzle.http.runtime import rate_limit as _rl

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
        result = require_found(result)
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
        result = require_found(result)
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
        result = require_found(result)

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
