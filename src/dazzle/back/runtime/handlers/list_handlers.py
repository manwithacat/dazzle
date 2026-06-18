"""List handler factory family for generated CRUD routes.

Extracted verbatim from ``route_generator.py`` (#1361 final slice). This is
the LIST family: ``create_list_handler`` (auth / noauth closure pair with
HTMX table metadata injection), the shared ``_list_handler_body`` (Cedar
LIST gate, scope-filter resolution, temporal ``?as_of=``, graph-format
serialization, HTMX fragment rendering, JSON projection), and
``_is_field_condition`` (used only by the LIST gate).

``_list_handler_body`` carries inline HTML (the HTMX error row + the
pagination OOB wrapper), so this module is listed in
``tests/unit/test_typed_runtime_no_jinja.py`` — the gate keeps covering
HTML that originated in ``route_generator.py``.

A leaf module by design: it must not import ``route_generator`` at module
level (``route_generator`` imports these names back at module level so the
``route_generator.<name>`` call sites, importers, and patch points keep
resolving there). The shared request/access utils that stay in
``route_generator`` (``_is_htmx_request`` / ``_wants_html`` /
``_normalize_role``) are imported lazily inside ``_list_handler_body``.

Deliberately NOT named ``*_routes.py`` — the runtime-urls api-surface walker
globs that pattern and this module defines no routes.
"""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from fastapi import Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from dazzle.back.runtime.audit_wrap import _build_access_context, _log_audit_decision
from dazzle.back.runtime.auth import AuthContext
from dazzle.back.runtime.htmx_render import (
    _render_table_empty,
    _render_table_pagination,
    _render_table_row,
    _render_table_sentinel,
)
from dazzle.back.runtime.scope_filters import _resolve_scope_filters
from dazzle.render.access_messages import _forbidden_detail

if TYPE_CHECKING:
    from dazzle.back.runtime.audit_log import AuditLogger
    from dazzle.back.runtime.route_generator import RouteSpec
    from dazzle.back.specs.auth import EntityAccessSpec
    from dazzle.core.ir.fk_graph import FKGraph

logger = logging.getLogger(__name__)


def create_list_handler(
    spec: "RouteSpec",
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

    # Request/role utils stay in route_generator (shared across handler
    # families + external importers); lazy import keeps this module
    # acyclic — route_generator imports this module at module level.
    from dazzle.back.runtime.route_generator import (
        _is_htmx_request,
        _normalize_role,
        _wants_html,
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
                # auth Plan 1b (#1406): report the *effective* roles the decision
                # actually used (active membership's roles, else legacy user.roles),
                # not the global user.roles — which is empty under the per-org model
                # and made the 403 diagnostic misleading.
                from dazzle.back.runtime.auth.models import effective_roles_of

                raise HTTPException(
                    status_code=403,
                    detail=_forbidden_detail(
                        entity_name=entity_name,
                        operation=AccessOperationKind.LIST,
                        cedar_access_spec=cedar_access_spec,
                        current_roles=list(effective_roles_of(auth_context)),
                    ),
                )

    # Build visibility filters
    sql_filters, post_filter = build_visibility_filter(access_spec, is_authenticated, user_id)

    # Apply scope filters (v0.44 — scope: blocks with predicate-compiled SQL).
    # When scopes list is non-empty, use _resolve_scope_filters which delegates
    # to the predicate compiler when predicates are available.
    if cedar_access_spec and is_authenticated and user_id:
        # Collect normalized user roles for scope matching. auth Plan 1b:
        # source from effective_roles (active membership's roles when present,
        # else legacy user.roles) so membership-scoped sessions match scope
        # rules — the global user.roles is empty under the per-org model.
        from dazzle.back.runtime.auth.models import effective_roles_of

        _scope_user_roles: set[str] = {
            _normalize_role(_r) for _r in effective_roles_of(auth_context)
        }

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
