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
resolving there). The shared request/access utils it needs (``RouteSpec`` /
``_is_htmx_request`` / ``_wants_html`` / ``_normalize_role``) come from the
``route_support`` leaf at top level — extracted there in the 2026-06-20 smells
round to break the import cycle that previously forced lazy in-function imports.

Deliberately NOT named ``*_routes.py`` — the runtime-urls api-surface walker
globs that pattern and this module defines no routes.
"""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from fastapi import Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from dazzle.core.access import AccessOperationKind
from dazzle.core.strings import entity_slug
from dazzle.http.runtime.audit_wrap import _log_audit_decision
from dazzle.http.runtime.auth import AuthContext
from dazzle.http.runtime.htmx_render import (
    _render_table_empty,
    _render_table_pagination,
    _render_table_row,
    _render_table_sentinel,
)

# Shared CRUD route-dispatch surface — from the route_support LEAF (smells round
# 2026-06-20). Was lazily imported from route_generator to dodge an import cycle;
# route_support is a leaf, so these are now plain top-level imports.
from dazzle.http.runtime.route_support import (
    RouteSpec,
    _is_htmx_request,
    _wants_html,
)
from dazzle.render.access_messages import _forbidden_detail

if TYPE_CHECKING:
    from dazzle.core.ir.fk_graph import FKGraph
    from dazzle.http.runtime.audit_log import AuditLogger
    from dazzle.http.specs.auth import EntityAccessSpec

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


# `_is_field_condition` was relocated to the clean `condition_evaluator` leaf
# (#1422) so the transport-agnostic `access.gated.gated_list` can use it without
# importing back into this FastAPI adapter. Re-imported here so the existing
# `route_generator` / `handlers` re-export chain (`list_handlers._is_field_condition`)
# keeps resolving.
from dazzle.http.runtime.condition_evaluator import (  # noqa: E402
    _is_field_condition as _is_field_condition,
)


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
    # Parse user-supplied filters from the request (HTTP concern). The enforcement
    # — Cedar LIST permit gate, legacy visibility filter, Cedar scope merge, and
    # the OR-condition post-filter — plus the data call were relocated VERBATIM to
    # access.gated.gated_list (#1422); this route now parses params, delegates,
    # and shapes the result. Permit-deny raises AccessForbidden → mapped to 403
    # here (with the same _forbidden_detail); scope-default-deny returns an empty
    # page (handled inside gated_list).
    # `filters` is the field-only user filter set (filter[field] / bare ?field=) —
    # kept distinct because the HTMX table renders it as `filter_values` (it must
    # NOT include the temporal repository keys below). `_gated_filters` is what
    # gated_list merges over scope: the field filters PLUS any temporal keys.
    filters: dict[str, Any] = {}
    _reserved_params = {"page", "page_size", "sort", "dir", "search", "q", "format"}
    for key, value in request.query_params.items():
        if key.startswith("filter[") and key.endswith("]") and value:
            filters[key[7:-1]] = value
        elif filter_fields and key in filter_fields and key not in _reserved_params and value:
            # Accept bare ?field=value when field is in the DSL-declared filter list (#596)
            filters[key] = value

    # #1223 Phase 3a.iv — read the temporal `?as_of=` / `?include_closed=` RAW
    # values here (HTTP concern), but parse + validate them INSIDE gated_list,
    # AFTER the permit gate, so a denied caller is rejected (403) before any input
    # validation runs (#1406 order). Mock-safe: a non-str value just passes through
    # and is rejected post-gate.
    _entity_spec = getattr(service, "entity_spec", None)
    _entity_temporal = _entity_spec.temporal if _entity_spec is not None else None
    _as_of_raw = (
        request.query_params.get(_entity_temporal.as_of_param)
        if _entity_temporal is not None
        else None
    )
    _include_closed = (
        request.query_params.get("include_closed", "").lower() in ("true", "1", "yes")
        if _entity_temporal is not None
        else False
    )

    # Build sort list for repository
    sort_list = [f"-{sort}" if dir == "desc" else sort] if sort else None

    # Delegate enforcement + data to the transport-agnostic core (#1422).
    from dazzle.http.runtime.access.gated import (
        AccessForbidden,
        InvalidTemporalParam,
        access_context_from,
        gated_list,
    )

    _access = access_context_from(
        auth_context=auth_context,
        entity_name=entity_name,
        cedar_access_spec=cedar_access_spec,
        fk_graph=fk_graph,
        admin_personas=admin_personas,
    )
    try:
        result = await gated_list(
            service,
            _access,
            page=page,
            page_size=page_size,
            sort_list=sort_list,
            search=search,
            user_filters=filters or None,
            select_fields=select_fields,
            auto_include=auto_include,
            search_fields=search_fields,
            access_spec=access_spec,
            ref_targets=ref_targets,
            temporal_as_of_raw=_as_of_raw,
            temporal_include_closed=_include_closed,
        )
    except AccessForbidden:
        from dazzle.http.runtime.auth.models import effective_roles_of

        raise HTTPException(
            status_code=403,
            detail=_forbidden_detail(
                entity_name=entity_name,
                operation=AccessOperationKind.LIST,
                cedar_access_spec=cedar_access_spec,
                current_roles=list(effective_roles_of(auth_context)) if auth_context else [],
            ),
        )
    except InvalidTemporalParam as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Audit log the list access (success — the deny path raised above).
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

        from dazzle.http.runtime.graph_serializer import GraphSerializer

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

        _slug = entity_slug(entity_name)
        redirect_url = f"/app/{_slug}"
        if request.query_params:
            redirect_url += f"?{request.url.query}"
        return RedirectResponse(url=redirect_url, status_code=302)

    # HTMX content negotiation: return HTML fragment for HX-Request
    if _is_htmx_request(request):
        try:
            from dazzle.http.runtime.htmx_response import HtmxDetails

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

            _logging.getLogger(__name__).exception(
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
