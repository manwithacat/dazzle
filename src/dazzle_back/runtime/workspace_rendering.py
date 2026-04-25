"""Workspace rendering helpers extracted from server.py.

Contains functions for building workspace region data, computing aggregate
metrics, and rendering workspace regions as HTML or JSON.
"""

import asyncio
import csv
import datetime as _dt
import io
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from starlette.responses import StreamingResponse

logger = logging.getLogger(__name__)

# Regex for aggregate expressions like count(Task) or count(Task where status = open)
# Tolerates whitespace around parens and entity name (DSL parser joins tokens with spaces).
_AGGREGATE_RE = re.compile(r"\s*(count|sum|avg|min|max)\s*\(\s*(\w+)\s*(?:where\s+(.+?))?\s*\)")


def _format_bucket_label(value: Any, unit: str) -> str:
    """Render a time-bucket SQL value as a human-readable string.

    ``date_trunc`` returns a datetime object (or tz-aware datetime on
    timestamptz columns). We emit a stable, locale-free label per unit
    so templates, snapshot tests, and charts all agree.

        day     → ``2026-04-23``
        week    → ``2026-W17``    (ISO week — Monday start)
        month   → ``Apr 2026``
        quarter → ``Q2 2026``
        year    → ``2026``

    Non-datetime / None values pass through as ``str(value)`` — the caller
    is responsible for deciding whether a null time bucket deserves a
    placeholder or should be filtered out.
    """
    if value is None:
        return ""
    if not isinstance(value, _dt.datetime | _dt.date):
        return str(value)
    # date (from date_trunc on a date column) vs datetime — both have
    # the strftime hooks we need.
    if unit == "day":
        return value.strftime("%Y-%m-%d")
    if unit == "week":
        # ISO week format — `%G` is ISO year, `%V` is ISO week number.
        return value.strftime("%G-W%V")
    if unit == "month":
        return value.strftime("%b %Y")
    if unit == "quarter":
        month = value.month
        quarter = (month - 1) // 3 + 1
        return f"Q{quarter} {value.year}"
    if unit == "year":
        return str(value.year)
    return str(value)


async def _resolve_workspace_user(
    request: Any,
    auth_middleware: Any,
    repositories: dict[str, Any] | None,
    user_entity_name: str = "User",
) -> tuple[str | None, dict[str, Any] | None]:
    """Resolve the current authenticated user to a DSL User entity UUID and attributes dict.

    Returns (entity_uuid, entity_dict) or (auth_user_id, None) as fallback.
    If no user can be resolved, returns (None, None).
    """
    if not auth_middleware:
        return None, None
    try:
        auth = auth_middleware.get_auth_context(request)
        if not (auth and auth.is_authenticated and auth.user):
            return None, None
    except Exception:
        logger.debug("Failed to resolve current user for filter context", exc_info=True)
        return None, None

    # Try to find the user entity record by email so filters use entity IDs.
    # Uses the DSL user entity name (may be "Student", "Member", etc.) (#588).
    email = getattr(auth.user, "email", None)
    if email and repositories:
        user_repo = repositories.get(user_entity_name)
        if user_repo:
            try:
                user_result = await user_repo.list(filters={"email": email}, page_size=1)
                user_items = (
                    user_result.get("items", [])
                    if isinstance(user_result, dict)
                    else getattr(user_result, "items", [])
                )
                if user_items:
                    entity_user = user_items[0]
                    uid = (
                        entity_user.get("id")
                        if isinstance(entity_user, dict)
                        else getattr(entity_user, "id", None)
                    )
                    if uid:
                        entity_dict = (
                            entity_user
                            if isinstance(entity_user, dict)
                            else entity_user.model_dump()
                            if hasattr(entity_user, "model_dump")
                            else {}
                        )
                        return str(uid), entity_dict
            except Exception:
                logger.debug("Could not resolve User entity by email", exc_info=True)

    # Fallback to auth user ID
    return str(auth.user.id), None


def _field_kind_to_col_type(field: Any, entity: Any = None) -> str:
    """Map an IR field to a column rendering type for workspace templates.

    Args:
        field: FieldSpec IR object.
        entity: Optional EntitySpec — when provided, checks if this field
                is the state-machine status field and returns ``"badge"``.
    """
    kind = field.type.kind
    kind_val: str = kind.value if hasattr(kind, "value") else str(kind) if kind else ""
    if kind_val == "enum":
        return "badge"
    if kind_val == "bool":
        return "bool"
    if kind_val in ("date", "datetime"):
        return "date"
    if kind_val == "money":
        return "currency"
    # State-machine status field renders as badge
    if entity is not None:
        sm = entity.state_machine
        if sm and sm.status_field == field.name:
            return "badge"
    return "text"


def _build_surface_columns(entity_spec: Any, surface_spec: Any) -> list[dict[str, Any]]:
    """Build column metadata from a list surface's field projection.

    Uses the surface's section elements to determine which entity fields to
    show and in what order, rather than dumping all entity fields.
    """
    from dazzle.core.strings import to_api_plural

    if not entity_spec or not hasattr(entity_spec, "fields"):
        return []

    # Collect field names from surface sections (preserving order). Carry the
    # element-level (or fallback section-level) visible: predicate so the
    # request handler can hide columns the persona shouldn't see (#872).
    surface_fields: list[str] = []
    field_visible_conditions: dict[str, dict[str, Any] | None] = {}
    for section in surface_spec.sections:
        _sec_vis = getattr(section, "visible", None)
        _section_vis_cond = _sec_vis.model_dump() if _sec_vis is not None else None
        for element in section.elements:
            fn = element.field_name
            if fn and fn != "id" and fn not in surface_fields:
                surface_fields.append(fn)
                _el_vis = getattr(element, "visible", None)
                field_visible_conditions[fn] = (
                    _el_vis.model_dump() if _el_vis else _section_vis_cond
                )

    if not surface_fields:
        return _build_entity_columns(entity_spec)

    # Build a lookup from entity fields
    field_map: dict[str, Any] = {f.name: f for f in entity_spec.fields}

    columns: list[dict[str, Any]] = []
    for fn in surface_fields:
        f = field_map.get(fn)
        if not f:
            continue
        _vis_cond = field_visible_conditions.get(fn)
        ft = f.type
        kind = ft.kind
        kind_val: str = kind.value if hasattr(kind, "value") else str(kind) if kind else ""
        # Ref and belongs_to fields
        if kind_val in ("ref", "belongs_to"):
            rel_name = f.name[:-3] if f.name.endswith("_id") else f.name
            ref_entity = getattr(ft, "ref_entity", None)
            ref_route = f"/{to_api_plural(str(ref_entity))}/{{id}}" if ref_entity else ""
            ref_col: dict[str, Any] = {
                "key": rel_name,
                "label": rel_name.replace("_", " ").title(),
                "type": "ref",
                "sortable": False,
                "ref_route": ref_route,
            }
            if _vis_cond:
                ref_col["visible_condition"] = _vis_cond
            columns.append(ref_col)
            continue
        # Skip non-displayable types
        if kind_val in ("uuid", "has_many", "has_one", "embeds"):
            continue
        col_type = _field_kind_to_col_type(f, entity_spec)
        col_key = f"{f.name}_minor" if kind_val == "money" else f.name
        col: dict[str, Any] = {
            "key": col_key,
            "label": f.name.replace("_", " ").title(),
            "type": col_type,
            "sortable": True,
        }
        if _vis_cond:
            col["visible_condition"] = _vis_cond
        if kind_val == "money":
            col["currency_code"] = getattr(ft, "currency_code", None) or "GBP"
        if col_type == "badge":
            if kind_val == "enum":
                ev = getattr(ft, "enum_values", None)
                if ev:
                    col["filterable"] = True
                    col["filter_options"] = list(ev)
            else:
                sm = entity_spec.state_machine
                if sm:
                    states = sm.states
                    if states:
                        col["filterable"] = True
                        col["filter_options"] = list(states)
        if col_type == "bool":
            col["filterable"] = True
            col["filter_options"] = ["true", "false"]
        columns.append(col)
    return columns


def _build_entity_columns(entity_spec: Any) -> list[dict[str, Any]]:
    """Pre-compute column metadata from an entity spec (constant-folded at startup).

    This replaces per-request column derivation with a one-time computation.
    All data comes from IR (field types, enum values, state machines) and
    never changes during the lifetime of the server.
    """
    from dazzle.core.strings import to_api_plural

    columns: list[dict[str, Any]] = []
    if not entity_spec or not hasattr(entity_spec, "fields"):
        return columns

    for f in entity_spec.fields:
        if f.name == "id":
            continue
        ft = f.type
        kind = ft.kind
        kind_val: str = kind.value if hasattr(kind, "value") else str(kind) if kind else ""
        # Show ref/belongs_to columns with resolved display name; hide other relation types
        if kind_val in ("ref", "belongs_to"):
            rel_name = f.name[:-3] if f.name.endswith("_id") else f.name
            ref_entity = getattr(ft, "ref_entity", None)
            # Ensure ref_entity is a plain string (not a pydantic/Cython object)
            ref_route = f"/{to_api_plural(str(ref_entity))}/{{id}}" if ref_entity else ""
            columns.append(
                {
                    "key": rel_name,
                    "label": rel_name.replace("_", " ").title(),
                    "type": "ref",
                    "sortable": False,
                    "ref_route": ref_route,
                }
            )
            continue
        if kind_val in ("uuid", "has_many", "has_one", "embeds"):
            continue
        if f.name.endswith("_id"):
            continue
        col_type = _field_kind_to_col_type(f, entity_spec)
        col_key = f.name
        if kind_val == "money":
            col_key = f"{f.name}_minor"
        col: dict[str, Any] = {
            "key": col_key,
            "label": f.name.replace("_", " ").title(),
            "type": col_type,
            "sortable": True,
        }
        if kind_val == "money":
            col["currency_code"] = getattr(ft, "currency_code", None) or "GBP"
        if col_type == "badge":
            if kind_val == "enum":
                ev = getattr(ft, "enum_values", None)
                if ev:
                    col["filterable"] = True
                    col["filter_options"] = list(ev)
            else:
                sm = entity_spec.state_machine
                if sm:
                    states = sm.states
                    if states:
                        col["filterable"] = True
                        col["filter_options"] = list(states)
        if col_type == "bool":
            col["filterable"] = True
            col["filter_options"] = ["true", "false"]
        columns.append(col)
        if len(columns) >= 8:
            break
    return columns


@dataclass
class WorkspaceRegionContext:
    """Bundles the non-request, non-pagination context for a workspace region handler."""

    ctx_region: Any
    ir_region: Any
    source: str
    entity_spec: Any
    attention_signals: list[Any]
    ws_access: Any
    repositories: dict[str, Any]
    require_auth: bool
    auth_middleware: Any
    # Pre-computed at startup (constant-folded from IR)
    precomputed_columns: list[dict[str, Any]] = field(default_factory=list)
    # Pre-computed ref relation names for eager-loading (from entity_auto_includes)
    auto_include: list[str] = field(default_factory=list)
    # Surface UX metadata (#362)
    surface_default_sort: list[Any] = field(default_factory=list)
    surface_empty_message: str = ""
    # Runtime parameter resolution (#572)
    param_resolver: Any = None  # ParamResolver | None
    tenant_id: str | None = None
    # Entity access spec for scope predicate enforcement (#574)
    cedar_access_spec: Any = None
    fk_graph: Any = None
    # DSL user entity name for current_user resolution (#588)
    user_entity_name: str = "User"


def _resolve_display_name(value: Any) -> str:
    """Resolve a field value to a display string.

    FK relations are dicts with an optional ``__display__`` key.
    Falls back to ``name``, ``title``, ``code``, ``label``, then ``id``.
    Scalar values are simply stringified.
    """
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("__display__", "name", "title", "code", "label", "id"):
            v = value.get(key)
            if v is not None:
                return str(v)
        # Last resort: first string value in the dict
        for v in value.values():
            if isinstance(v, str) and v:
                return v
        return str(value.get("id", ""))
    return str(value)


def _inject_display_names(item: dict[str, Any]) -> dict[str, Any]:
    """Inject ``{field}_display`` keys for FK dict fields (#571).

    For each field whose value is a dict (FK relation), adds a sibling key
    with the resolved display name. The original dict is preserved for
    templates that need the id for linking.
    """
    extras: dict[str, str] = {}
    for key, value in item.items():
        if isinstance(value, dict) and key != "_attention":
            extras[f"{key}_display"] = _resolve_display_name(value)
    if extras:
        item.update(extras)
    return item


def _render_csv_response(
    items: list[dict[str, Any]],
    columns: list[dict[str, Any]],
    region_name: str,
) -> StreamingResponse:
    """Return items as a CSV download."""
    output = io.StringIO()
    col_keys = [c["key"] for c in columns]
    col_labels = [c.get("label", c["key"]) for c in columns]

    writer = csv.writer(output)
    writer.writerow(col_labels)
    for item in items:
        row = [str(item.get(f"{k}_display", item.get(k, ""))) for k in col_keys]
        writer.writerow(row)

    output.seek(0)
    filename = f"{region_name}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _apply_workspace_scope_filters(
    ctx: WorkspaceRegionContext,
    auth_context: Any,
    user_id: str | None,
    filters: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, bool]:
    """Apply entity-level scope predicates to workspace region filters.

    Mirrors the scope enforcement in ``route_generator._make_list_handler``
    so that workspace regions cannot bypass row-level scope rules (#574).

    Returns:
        (merged_filters, denied) — *denied* is True when no scope rule
        matched the user's roles (default-deny: caller should return empty).
    """
    cedar_access_spec = ctx.cedar_access_spec
    if not cedar_access_spec or not user_id or not auth_context:
        return filters, False

    scopes = getattr(cedar_access_spec, "scopes", None)
    if not scopes:
        # No scope rules — pass through without row filtering (#607).
        # The permit gate already controls entity-level access.
        return filters, False

    from dazzle_back.runtime.route_generator import (
        _normalize_role,
        _resolve_scope_filters,
    )

    # Collect normalized user roles
    scope_user_roles: set[str] = set()
    user_obj = getattr(auth_context, "user", None)
    if user_obj:
        for r in getattr(user_obj, "roles", []):
            rname = r if isinstance(r, str) else getattr(r, "name", str(r))
            scope_user_roles.add(_normalize_role(rname))

    scope_result = _resolve_scope_filters(
        cedar_access_spec,
        "list",
        scope_user_roles,
        user_id,
        auth_context,
        entity_name=ctx.source,
        fk_graph=ctx.fk_graph,
    )

    if scope_result is None:
        # No scope rule matched — default-deny
        return filters, True

    if scope_result:
        filters = {**(filters or {}), **scope_result}

    return filters, False


async def _workspace_region_handler(
    request: Any,
    page: int,
    page_size: int,
    sort: str | None,
    dir: str,
    *,
    ctx: WorkspaceRegionContext,
) -> Any:
    """Return rendered HTML for a workspace region.

    Extracted from DazzleBackendApp._init_workspace_routes to reduce closure
    complexity.  All context is bundled in a ``WorkspaceRegionContext``.
    """
    from fastapi import HTTPException
    from fastapi.responses import HTMLResponse

    from dazzle_ui.runtime.template_renderer import render_fragment

    # Enforce authentication (#145)
    if ctx.require_auth:
        auth_ctx = None
        if ctx.auth_middleware:
            try:
                auth_ctx = ctx.auth_middleware.get_auth_context(request)
            except Exception:
                logger.debug("Failed to get auth context for region", exc_info=True)
        if not (auth_ctx and auth_ctx.is_authenticated):
            raise HTTPException(status_code=401, detail="Authentication required")

        # RBAC: enforce workspace persona restrictions on region data.
        # Roles use "role_" prefix; persona IDs don't.
        if ctx.ws_access and ctx.ws_access.allow_personas and auth_ctx:
            is_super = auth_ctx.user and auth_ctx.user.is_superuser
            normalized_roles = [r.removeprefix("role_") for r in auth_ctx.roles]
            if not is_super and not any(
                r in ctx.ws_access.allow_personas for r in normalized_roles
            ):
                raise HTTPException(status_code=403, detail="Workspace access denied")

    # Resolve current user ID for filter expressions (e.g. reviewer == current_user)
    # Auth user IDs and User entity IDs are separate; resolve via email match (#480).
    # Always attempt resolution when middleware is available, even in test mode
    # where require_auth is False — the user may still be authenticated (#483).
    _current_user_id, _current_user_entity = await _resolve_workspace_user(
        request, ctx.auth_middleware, ctx.repositories, ctx.user_entity_name
    )

    # Build auth_context for _extract_condition_filters (shared with entity scope path)
    _auth_ctx_for_filters: Any = None
    if ctx.auth_middleware:
        try:
            _auth_ctx_for_filters = ctx.auth_middleware.get_auth_context(request)
            # Ensure preferences contain entity attributes so current_user.<attr> resolves
            if _auth_ctx_for_filters and _current_user_entity:
                prefs = getattr(_auth_ctx_for_filters, "preferences", None)
                if prefs is None:
                    _auth_ctx_for_filters.preferences = {}
                    prefs = _auth_ctx_for_filters.preferences
                from uuid import UUID as _UUID

                for k, v in _current_user_entity.items():
                    if k not in prefs and v is not None:
                        prefs[k] = str(v) if isinstance(v, _UUID) else v
                if _current_user_id and "entity_id" not in prefs:
                    prefs["entity_id"] = _current_user_id
        except Exception:
            logger.debug("Failed to get auth context for filter resolution", exc_info=True)

    # Build legacy filter context for attention signals and grant evaluation
    _filter_context: dict[str, Any] = {}
    if _current_user_id:
        _filter_context["current_user_id"] = _current_user_id
    if _current_user_entity:
        _filter_context["current_user_entity"] = _current_user_entity
    # Context selector value (v0.38.0): from query param or user preferences
    _context_id = request.query_params.get("context_id")
    if _context_id:
        _filter_context["current_context"] = _context_id

    # Pre-fetch active grants for has_grant() condition evaluation (v0.42.0)
    if _current_user_id:
        try:
            from .grant_store import GrantStore

            # Get DB connection from any available repository
            _db_mgr = None
            if ctx.repositories:
                for _r in ctx.repositories.values():
                    _db_mgr = getattr(_r, "db", None)
                    if _db_mgr:
                        break
            if _db_mgr:
                _grant_conn = _db_mgr.get_persistent_connection()
                _grant_store = GrantStore(_grant_conn)
                from uuid import UUID as _UUID

                _active_grants = _grant_store.list_grants(
                    principal_id=_UUID(_current_user_id), status="active"
                )
                _filter_context["active_grants"] = _active_grants
            else:
                _filter_context["active_grants"] = []
        except Exception:
            # Grant tables may not exist if no grant_schemas defined
            logger.debug("Could not pre-fetch grants", exc_info=True)
            _filter_context["active_grants"] = []

    # Query the source entity
    items: list[dict[str, Any]] = []
    total = 0
    columns: list[dict[str, Any]] = []

    repo = ctx.repositories.get(ctx.source) if ctx.repositories else None
    if repo:
        try:
            # Build filters from IR ConditionExpr
            # Multi-source regions store per-source filter on _source_filter
            filters: dict[str, Any] | None = None
            ir_filter = getattr(ctx, "_source_filter", None) or ctx.ir_region.filter
            if ir_filter is not None:
                try:
                    from dazzle_back.runtime.route_generator import (
                        _extract_condition_filters,
                    )

                    filters = {}
                    _extract_condition_filters(
                        ir_filter,
                        _current_user_id or "",
                        filters,
                        logger,
                        _auth_ctx_for_filters,
                        context_id=_context_id,
                    )
                    if not filters:
                        filters = None
                except Exception:
                    logger.warning("Failed to evaluate condition filter", exc_info=True)

            # Build sort — user sort param > IR region sort > surface UX sort (#362)
            sort_list: list[str] | None = None
            if sort:
                sort_list = [f"-{sort}" if dir == "desc" else sort]
            else:
                ir_sort = ctx.ir_region.sort
                if ir_sort:
                    sort_list = [
                        f"-{s.field}" if s.direction == "desc" else s.field for s in ir_sort
                    ]
                elif ctx.surface_default_sort:
                    sort_list = [
                        f"-{s.field}" if s.direction == "desc" else s.field
                        for s in ctx.surface_default_sort
                    ]

            # Collect interactive filters from query params
            for param_key, param_val in request.query_params.items():
                if param_key.startswith("filter_") and param_val:
                    field_name = param_key[7:]  # strip "filter_"
                    if filters is None:
                        filters = {}
                    filters[field_name] = param_val

            # Date range filtering (#566)
            date_field = ctx.ctx_region.date_field if hasattr(ctx.ctx_region, "date_field") else ""
            if date_field:
                date_from = request.query_params.get("date_from")
                date_to = request.query_params.get("date_to")
                if date_from:
                    if filters is None:
                        filters = {}
                    filters[f"{date_field}__gte"] = date_from
                if date_to:
                    if filters is None:
                        filters = {}
                    filters[f"{date_field}__lte"] = date_to

            # SECURITY: apply entity-level scope predicates (#574)
            _scope_only_filters, _scope_denied = _apply_workspace_scope_filters(
                ctx, _auth_ctx_for_filters, _current_user_id, None
            )
            if _scope_only_filters:
                filters = {**(filters or {}), **_scope_only_filters}

            # Use pre-computed auto_include from entity_auto_includes (#272, #423)
            include_rels = ctx.auto_include

            # Grouped views need enough items to distribute across columns
            if (
                ctx.ctx_region.display in ("KANBAN", "BAR_CHART", "FUNNEL_CHART")
                and not ctx.ctx_region.limit
            ):
                limit = min(page_size, 200) if page_size > 20 else 50
            else:
                limit = ctx.ctx_region.limit or page_size
            if _scope_denied:
                # No scope rule matched — default-deny: empty result set
                result = {"items": [], "total": 0}
            else:
                result = await repo.list(
                    page=page,
                    page_size=limit,
                    filters=filters,
                    sort=sort_list,
                    include=include_rels or None,
                    fk_display_only=True,
                )
            if isinstance(result, dict):
                _result: dict[str, Any] = result
                raw_items = _result.get("items", [])
                items = [i.model_dump() if hasattr(i, "model_dump") else dict(i) for i in raw_items]
                # Resolve FK dicts to display strings (#571)
                items = [_inject_display_names(item) for item in items]
                # SECURITY: use item count as total for workspace regions.
                # The repo COUNT query may not have scope rules applied,
                # which would leak unscoped record counts in pagination
                # metadata (e.g., "Showing 10 of 52,380") (#573).
                total = len(items)

            # Zero results is valid — the region shows its empty: message.
            # Do NOT fall back to unfiltered queries: scope/filter conditions
            # are access-control gates, not advisory hints (#546).
        except Exception:
            logger.warning("Failed to list items for workspace region", exc_info=True)

    # Use pre-computed columns from startup (constant-folded from IR).
    # Filter out columns whose visible: predicate fails for the current
    # persona (#872). Build a fresh list — never mutate the shared one.
    if ctx.precomputed_columns:
        if any(c.get("visible_condition") for c in ctx.precomputed_columns):
            from dazzle_ui.utils.condition_eval import evaluate_condition as _eval_vis

            _request_roles = list(_auth_ctx_for_filters.roles) if _auth_ctx_for_filters else []
            _role_ctx = {
                "user_roles": [r.removeprefix("role_") for r in _request_roles],
            }
            columns = [
                c
                for c in ctx.precomputed_columns
                if not c.get("visible_condition")
                or _eval_vis(c["visible_condition"], {}, _role_ctx)
            ]
        else:
            columns = ctx.precomputed_columns
    elif items:
        columns = [
            {
                "key": k,
                "label": k.replace("_", " ").title(),
                "type": "text",
                "sortable": True,
            }
            for k in items[0].keys()
            if k != "id"
        ]

    # CSV export (#562)
    format_param = request.query_params.get("format")
    if format_param == "csv":
        return _render_csv_response(items, columns, ctx.ctx_region.name)

    # Build aggregate metrics if configured
    metrics: list[dict[str, Any]] = []
    if ctx.ctx_region.aggregates:
        metrics = await _compute_aggregate_metrics(
            ctx.ctx_region.aggregates,
            ctx.repositories,
            total,
            items,
            scope_filters=_scope_only_filters,
            delta=ctx.ctx_region.delta,  # #884
        )

    # Bucketed aggregates for bar_chart distributions (#847). When a
    # bar_chart region declares both `group_by` and `aggregates`, evaluate
    # the first aggregate once per bucket so authors can express true
    # distributions instead of getting raw row counts. The bucket list
    # comes from `kanban_columns` when available (enum / state-machine
    # values), else falls back to distinct items[group_by].
    bucketed_metrics: list[dict[str, Any]] = []

    # Build filter column metadata for template
    filter_columns: list[dict[str, Any]] = [
        {
            "key": c["key"],
            "label": c["label"],
            "options": c.get("filter_options", []),
        }
        for c in columns
        if c.get("filterable")
    ]
    active_filters: dict[str, str] = {
        k[7:]: v for k, v in request.query_params.items() if k.startswith("filter_") and v
    }

    # Evaluate attention signals for row highlighting
    if ctx.attention_signals and items:
        from dazzle_back.runtime.condition_evaluator import (
            evaluate_condition as _eval_cond,
        )

        _severity_order = {
            "critical": 0,
            "warning": 1,
            "notice": 2,
            "info": 3,
        }
        for item in items:
            best: dict[str, str] | None = None
            best_sev = 999
            for sig in ctx.attention_signals:
                try:
                    cond_dict = sig.condition.model_dump(exclude_none=True)
                    if _eval_cond(cond_dict, item, _filter_context):
                        lvl = sig.level.value if hasattr(sig.level, "value") else str(sig.level)
                        sev = _severity_order.get(lvl, 99)
                        if sev < best_sev:
                            best_sev = sev
                            best = {
                                "level": lvl,
                                "message": sig.message,
                            }
                except Exception:
                    logger.debug("Failed to evaluate attention signal", exc_info=True)
            if best:
                item["_attention"] = best

    # Grouped displays: extract column values from group_by field's enum/state-machine
    kanban_columns: list[str] = []
    # Read group_by from ir_region — the IR preserves the typed form
    # (str | BucketRef | None). ctx_region (pydantic, template-facing)
    # flattens it to a string for Jinja.
    group_by = (
        getattr(ctx.ir_region, "group_by", None) if ctx.ir_region else ctx.ctx_region.group_by
    )
    _grouped_modes = {"KANBAN", "BAR_CHART", "FUNNEL_CHART"}
    # Time-bucketed group_by is a BucketRef — it has no enum values and is
    # never kanban. Skip the enum/state-machine resolution for it.
    from dazzle.core.ir import BucketRef as _BucketRef

    _gb_is_bucket = isinstance(group_by, _BucketRef)
    if (
        group_by
        and not _gb_is_bucket
        and ctx.ctx_region.display in _grouped_modes
        and ctx.entity_spec
    ):
        # Try enum values first, then state machine states
        for f in ctx.entity_spec.fields:
            if f.name == group_by:
                ev = getattr(f.type, "enum_values", None)
                if ev:
                    kanban_columns = list(ev)
                break
        if not kanban_columns:
            sm = ctx.entity_spec.state_machine
            if sm and sm.status_field == group_by:
                kanban_columns = [s if isinstance(s, str) else str(s) for s in sm.states]

    # Compute bucketed aggregates for bar_chart / line_chart / sparkline —
    # single-dim distributions or time-series. Multi-dim (area_chart /
    # pivot_table) runs through _compute_pivot_buckets below.
    _single_dim_chart_modes = {"BAR_CHART", "LINE_CHART", "SPARKLINE"}
    if ctx.ctx_region.display in _single_dim_chart_modes and group_by and ctx.ctx_region.aggregates:
        bucketed_metrics = await _compute_bucketed_aggregates(
            ctx.ctx_region.aggregates,
            ctx.repositories,
            group_by,
            items,
            bucket_values=kanban_columns or None,
            scope_filters=_scope_only_filters,
            source_entity=ctx.source,
        )

    # Histogram (#882, v0.61.27): bin a continuous numeric column from the
    # already-fetched ``items`` and pass per-bin counts to the template.
    # No extra DB query — uses the rows already loaded for the region. The
    # value column is read from ``heatmap_value`` (legacy-named generic
    # "the value column" IR field). ``bin_count`` is the explicit bin count
    # or None for Sturges' rule (⌈log2(N) + 1⌉).
    histogram_bins: list[dict[str, Any]] = []
    if ctx.ctx_region.display == "HISTOGRAM":
        _value_field = (getattr(ctx.ctx_region, "heatmap_value", "") or "").strip()
        _bin_count = getattr(ctx.ir_region, "bin_count", None)
        if _value_field:
            histogram_bins = _compute_histogram_bins(items, _value_field, _bin_count)

    # Multi-dimension aggregate for pivot_table (cycle 25) and area_chart
    # (cycle 28 — stacked time-series). Reads `group_by_dims` from the IR
    # and runs ONE multi-dim GROUP BY via Repository.aggregate. Each entry
    # is a column on the source entity or a BucketRef for time-bucketed
    # dims; FK columns auto-LEFT JOIN their target so the bucket carries
    # the resolved display field.
    pivot_buckets: list[dict[str, Any]] = []
    pivot_dim_specs: list[dict[str, Any]] = []
    _multi_dim_modes = {"PIVOT_TABLE", "AREA_CHART"}
    _ir_group_by_dims = getattr(ctx.ir_region, "group_by_dims", None) if ctx.ir_region else None
    if (
        ctx.ctx_region.display in _multi_dim_modes
        and _ir_group_by_dims
        and ctx.ctx_region.aggregates
    ):
        pivot_buckets, pivot_dim_specs = await _compute_pivot_buckets(
            ctx.ctx_region.aggregates,
            ctx.repositories,
            _ir_group_by_dims,
            source_entity=ctx.source,
            source_entity_spec=ctx.entity_spec,
            scope_filters=_scope_only_filters,
        )

    # Queue display: extract state machine transitions for inline action buttons
    queue_transitions: list[dict[str, str]] = []
    queue_status_field = ""
    queue_api_endpoint = ""
    if ctx.ctx_region.display == "QUEUE" and ctx.entity_spec:
        sm = ctx.entity_spec.state_machine
        if sm:
            queue_status_field = sm.status_field
            seen: set[str] = set()
            for t in sm.transitions:
                to_state = t.to_state if isinstance(t.to_state, str) else str(t.to_state)
                if to_state not in seen:
                    seen.add(to_state)
                    queue_transitions.append(
                        {
                            "to_state": to_state,
                            "label": to_state.replace("_", " ").title(),
                        }
                    )
        # API endpoint for PUT transitions
        from dazzle.core.strings import to_api_plural

        queue_api_endpoint = f"/{to_api_plural(ctx.source)}"

    # Multi-source tabbed regions pass source_tabs to the template
    source_tabs = ctx.ctx_region.source_tabs or []

    # Tree display (#565) — build nested tree from flat items using group_by as parent ref
    tree_items: list[dict[str, Any]] = []

    # Heatmap: pivot flat items into a matrix structure (v0.44.0)
    heatmap_matrix: list[dict[str, Any]] = []
    heatmap_col_values: list[str] = []
    # Resolve heatmap_thresholds — check IR for ParamRef (#572, #575)
    _ir_thresholds = getattr(ctx.ir_region, "heatmap_thresholds", None)
    if hasattr(_ir_thresholds, "key"):  # ParamRef in IR
        from dazzle_back.runtime.param_store import resolve_value

        _resolved = resolve_value(
            _ir_thresholds,
            getattr(ctx, "param_resolver", None),
            tenant_id=getattr(ctx, "tenant_id", None),
        )
        # Fall back to ctx_region defaults when runtime has no override (#586)
        heatmap_thresholds: list[float] = list(
            _resolved or getattr(ctx.ctx_region, "heatmap_thresholds", None) or []
        )
    else:
        heatmap_thresholds = list(getattr(ctx.ctx_region, "heatmap_thresholds", None) or [])
    if ctx.ctx_region.display == "HEATMAP" and items:
        hm_rows_field = getattr(ctx.ctx_region, "heatmap_rows", "") or ""
        hm_cols_field = getattr(ctx.ctx_region, "heatmap_columns", "") or ""
        hm_value_field = getattr(ctx.ctx_region, "heatmap_value", "") or ""
        # Collect unique column values and build pivot
        # Use _display sibling keys injected by _inject_display_names() (#586)
        col_set: set[str] = set()
        for item in items:
            cv = str(item.get(f"{hm_cols_field}_display", "")) or _resolve_display_name(
                item.get(hm_cols_field, "")
            )
            if cv:
                col_set.add(cv)
        heatmap_col_values = sorted(col_set)
        # Group by row → column → value; track raw row IDs for action URLs
        row_map: dict[str, dict[str, float]] = {}
        row_ids: dict[str, str] = {}
        for item in items:
            rv = str(item.get(f"{hm_rows_field}_display", "")) or _resolve_display_name(
                item.get(hm_rows_field, "")
            )
            cv = str(item.get(f"{hm_cols_field}_display", "")) or _resolve_display_name(
                item.get(hm_cols_field, "")
            )
            val = float(item.get(hm_value_field, 0) or 0)
            if rv not in row_map:
                row_map[rv] = {}
            row_map[rv][cv] = val
            # Store raw row ID for action URL interpolation.
            # When the FK is expanded (dict), use its "id"; when it's a plain
            # UUID string, that IS the target entity ID — don't fall back to
            # the source item's own id (#633).
            raw_row = item.get(hm_rows_field)
            if isinstance(raw_row, dict):
                row_id = str(raw_row.get("id", ""))
            elif raw_row:
                row_id = str(raw_row)
            else:
                row_id = str(item.get("id", ""))
            row_ids[rv] = row_id
        for row_label in sorted(row_map.keys()):
            cells: list[dict[str, Any]] = []
            for col_label in heatmap_col_values:
                cell_val = row_map[row_label].get(col_label, 0.0)
                cells.append({"value": cell_val, "column": col_label})
            heatmap_matrix.append(
                {"row": row_label, "row_id": row_ids.get(row_label, ""), "cells": cells}
            )

    # Progress: count items per stage and compute percentage (v0.44.0)
    progress_stage_counts: list[dict[str, Any]] = []
    progress_total = 0
    progress_complete_count = 0
    progress_complete_pct = 0.0
    progress_stages_list: list[str] = list(getattr(ctx.ctx_region, "progress_stages", None) or [])
    progress_complete_at: str = getattr(ctx.ctx_region, "progress_complete_at", "") or ""
    if ctx.ctx_region.display == "PROGRESS" and items and progress_stages_list:
        stage_counter: dict[str, int] = dict.fromkeys(progress_stages_list, 0)
        status_field = group_by or "status"
        for item in items:
            item_stage = str(item.get(status_field, ""))
            if item_stage in stage_counter:
                stage_counter[item_stage] += 1
        progress_total = sum(stage_counter.values())
        # Find the index of complete_at stage; everything at or past it is "complete"
        complete_idx = -1
        if progress_complete_at in progress_stages_list:
            complete_idx = progress_stages_list.index(progress_complete_at)
        for i, stage_name in enumerate(progress_stages_list):
            cnt = stage_counter.get(stage_name, 0)
            is_complete = complete_idx >= 0 and i >= complete_idx
            progress_stage_counts.append(
                {"name": stage_name, "count": cnt, "complete": is_complete}
            )
            if is_complete:
                progress_complete_count += cnt
        if progress_total > 0:
            progress_complete_pct = round(progress_complete_count / progress_total * 100, 1)

    # Tree display (#565) — build nested hierarchy from flat items
    display_upper = ctx.ctx_region.display
    if display_upper == "TREE" and group_by and items:
        items_by_id = {str(item.get("id", "")): item for item in items}
        children_map: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            parent_id = str(item.get(group_by, "") or "")
            children_map.setdefault(parent_id, []).append(item)

        # Root items have no parent or parent not in the set
        roots = [item for item in items if str(item.get(group_by, "") or "") not in items_by_id]

        def _build_subtree(node: dict[str, Any]) -> dict[str, Any]:
            node_id = str(node.get("id", ""))
            node["_children"] = children_map.get(node_id, [])
            for child in node["_children"]:
                _build_subtree(child)
            return node

        tree_items = [_build_subtree(r) for r in roots]

    html = render_fragment(
        ctx.ctx_region.template,
        title=ctx.ctx_region.title,
        items=items,
        total=total,
        columns=columns,
        metrics=metrics,
        bucketed_metrics=bucketed_metrics,
        pivot_buckets=pivot_buckets,
        pivot_dim_specs=pivot_dim_specs,
        empty_message=ctx.surface_empty_message or ctx.ctx_region.empty_message,
        display_key=next(
            (c["key"] for c in columns if c.get("type") not in ("badge", "ref")),
            columns[0]["key"] if columns else "name",
        ),
        item=items[0] if items else None,
        action_url=ctx.ctx_region.action_url,
        # v0.61.7 (#861): forward the FK field the action URL should key on.
        # Templates use `item[action_id_field] | resolve_fk_id` to handle
        # both scalar ids and FK dicts expanded by _inject_display_names.
        action_id_field=ctx.ctx_region.action_id_field,
        sort_field=sort or "",
        sort_dir=dir,
        endpoint=ctx.ctx_region.endpoint,
        region_name=ctx.ctx_region.name,
        filter_columns=filter_columns,
        active_filters=active_filters,
        # Templates expect a string or None; reduce BucketRef to its field
        # name (the unit already drove bucketed_metrics labels server-side).
        group_by=(group_by.field if isinstance(group_by, _BucketRef) else group_by),
        kanban_columns=kanban_columns,
        queue_transitions=queue_transitions,
        queue_status_field=queue_status_field,
        queue_api_endpoint=queue_api_endpoint,
        source_tabs=source_tabs,
        source_entity=ctx.source,
        # Heatmap context (v0.44.0)
        heatmap_matrix=heatmap_matrix,
        heatmap_col_values=heatmap_col_values,
        heatmap_thresholds=heatmap_thresholds,
        # Progress context (v0.44.0)
        stage_counts=progress_stage_counts,
        progress_total=progress_total,
        complete_count=progress_complete_count,
        complete_pct=progress_complete_pct,
        # Date range (v0.44.0)
        date_range=getattr(ctx.ctx_region, "date_range", False),
        date_field=getattr(ctx.ctx_region, "date_field", ""),
        date_from=request.query_params.get("date_from", ""),
        date_to=request.query_params.get("date_to", ""),
        # Tree context (#565)
        tree_items=tree_items,
        # Line/area chart overlays (#883, v0.61.26)
        reference_lines=getattr(ctx.ctx_region, "reference_lines", []),
        reference_bands=getattr(ctx.ctx_region, "reference_bands", []),
        # Histogram (#882, v0.61.27) — pre-computed bins from `items`
        histogram_bins=histogram_bins,
    )
    return HTMLResponse(content=html)


async def _fetch_region_json(
    request: Any,
    page: int,
    page_size: int,
    ctx: WorkspaceRegionContext,
    filter_context: dict[str, Any] | None = None,
    *,
    auth_context: Any = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Fetch a single region's data as JSON for batch responses."""
    repo = ctx.repositories.get(ctx.source) if ctx.repositories else None
    items: list[dict[str, Any]] = []
    total = 0

    if repo:
        try:
            filters: dict[str, Any] | None = None
            ir_filter = ctx.ir_region.filter
            if ir_filter is not None:
                try:
                    from dazzle_back.runtime.route_generator import (
                        _extract_condition_filters,
                    )

                    filters = {}
                    _extract_condition_filters(
                        ir_filter,
                        user_id or (filter_context or {}).get("current_user_id", ""),
                        filters,
                        logger,
                        auth_context,
                        context_id=(filter_context or {}).get("current_context"),
                    )
                    if not filters:
                        filters = None
                except Exception:
                    logger.warning("Failed to evaluate condition filter for region", exc_info=True)

            sort_list: list[str] | None = None
            ir_sort = ctx.ir_region.sort
            if ir_sort:
                sort_list = [f"-{s.field}" if s.direction == "desc" else s.field for s in ir_sort]

            # SECURITY: apply entity-level scope predicates (#574)
            filters, _scope_denied = _apply_workspace_scope_filters(
                ctx, auth_context, user_id, filters
            )

            limit = ctx.ctx_region.limit or page_size
            include_rels = ctx.auto_include or None
            if _scope_denied:
                result = {"items": [], "total": 0}
            else:
                result = await repo.list(
                    page=page,
                    page_size=limit,
                    filters=filters,
                    sort=sort_list,
                    include=include_rels,
                    fk_display_only=True,
                )
            if isinstance(result, dict):
                _result: dict[str, Any] = result
                raw_items = _result.get("items", [])
                total = _result.get("total", 0)
                items = [i.model_dump() if hasattr(i, "model_dump") else dict(i) for i in raw_items]
                items = [_inject_display_names(item) for item in items]

            # Zero results is valid — the region shows its empty: message.
            # Do NOT fall back to unfiltered queries (#546).
        except Exception:
            logger.warning(
                "Batch: failed to list items for region %s", ctx.ctx_region.name, exc_info=True
            )

    metrics: list[dict[str, Any]] = []
    if ctx.ctx_region.aggregates:
        metrics = await _compute_aggregate_metrics(
            ctx.ctx_region.aggregates, ctx.repositories, total, items
        )

    return {
        "region": ctx.ctx_region.name,
        "items": items,
        "total": total,
        "metrics": metrics,
    }


async def _workspace_batch_handler(
    request: Any,
    page: int,
    page_size: int,
    region_ctxs: list[WorkspaceRegionContext],
) -> dict[str, Any]:
    """Fetch all workspace regions concurrently and return combined JSON."""
    from fastapi import HTTPException

    # Enforce auth on any region that requires it
    for ctx in region_ctxs:
        if ctx.require_auth:
            auth_ctx = None
            if ctx.auth_middleware:
                try:
                    auth_ctx = ctx.auth_middleware.get_auth_context(request)
                except Exception:
                    logger.warning(
                        "Failed to get auth context for batch workspace request", exc_info=True
                    )
            if not (auth_ctx and auth_ctx.is_authenticated):
                raise HTTPException(status_code=401, detail="Authentication required")
            if ctx.ws_access and ctx.ws_access.allow_personas and auth_ctx:
                is_super = auth_ctx.user and auth_ctx.user.is_superuser
                normalized_roles = [r.removeprefix("role_") for r in auth_ctx.roles]
                if not is_super and not any(
                    r in ctx.ws_access.allow_personas for r in normalized_roles
                ):
                    raise HTTPException(status_code=403, detail="Workspace access denied")
            break  # All regions share the same workspace access

    # Resolve current user entity ID for filter context (same logic as
    # _workspace_region_handler) so batch region filters using current_user
    # compare against the DSL User entity UUID, not the auth UUID (#546).
    _first_ctx = region_ctxs[0] if region_ctxs else None
    _batch_user_id, _batch_user_entity = await _resolve_workspace_user(
        request,
        _first_ctx.auth_middleware if _first_ctx else None,
        _first_ctx.repositories if _first_ctx else None,
        _first_ctx.user_entity_name if _first_ctx else "User",
    )

    # Build auth_context for _extract_condition_filters
    _batch_auth_ctx: Any = None
    if _first_ctx and _first_ctx.auth_middleware:
        try:
            _batch_auth_ctx = _first_ctx.auth_middleware.get_auth_context(request)
            if _batch_auth_ctx and _batch_user_entity:
                prefs = getattr(_batch_auth_ctx, "preferences", None)
                if prefs is None:
                    _batch_auth_ctx.preferences = {}
                    prefs = _batch_auth_ctx.preferences
                from uuid import UUID as _UUID

                for k, v in _batch_user_entity.items():
                    if k not in prefs and v is not None:
                        prefs[k] = str(v) if isinstance(v, _UUID) else v
                if _batch_user_id and "entity_id" not in prefs:
                    prefs["entity_id"] = _batch_user_id
        except Exception:
            logger.debug("Batch: failed to get auth context", exc_info=True)

    # Legacy filter context for backward compat
    _batch_filter_ctx: dict[str, Any] = {}
    if _batch_user_id:
        _batch_filter_ctx["current_user_id"] = _batch_user_id
    if _batch_user_entity:
        _batch_filter_ctx["current_user_entity"] = _batch_user_entity

    results = await asyncio.gather(
        *(
            _fetch_region_json(
                request,
                page,
                page_size,
                ctx,
                filter_context=_batch_filter_ctx,
                auth_context=_batch_auth_ctx,
                user_id=_batch_user_id,
            )
            for ctx in region_ctxs
        ),
        return_exceptions=True,
    )

    regions: list[dict[str, Any]] = []
    for result in results:
        if isinstance(result, dict):
            regions.append(result)
        elif isinstance(result, BaseException):
            logger.warning("Batch region query failed: %s", result)

    return {"regions": regions}


async def _workspace_stats_handler(
    request: Any,
    region_ctxs: list[WorkspaceRegionContext],
) -> dict[str, Any]:
    """Compute workspace aggregate metrics as standalone JSON (closes #783).

    Returns ``{"workspace": name, "stats": {region_name: {metric: value}}}``.
    Only regions with a non-empty ``aggregates`` mapping contribute.
    Items-based aggregates (``count`` alone or ``sum:field``) resolve to 0 —
    callers needing those values should invoke the region endpoint directly.
    """
    from fastapi import HTTPException

    # Enforce auth (same shape as batch handler: any region that requires it).
    for ctx in region_ctxs:
        if ctx.require_auth:
            auth_ctx = None
            if ctx.auth_middleware:
                try:
                    auth_ctx = ctx.auth_middleware.get_auth_context(request)
                except Exception:
                    logger.warning("Failed to get auth context for stats request", exc_info=True)
            if not (auth_ctx and auth_ctx.is_authenticated):
                raise HTTPException(status_code=401, detail="Authentication required")
            if ctx.ws_access and ctx.ws_access.allow_personas and auth_ctx:
                is_super = auth_ctx.user and auth_ctx.user.is_superuser
                normalized_roles = [r.removeprefix("role_") for r in auth_ctx.roles]
                if not is_super and not any(
                    r in ctx.ws_access.allow_personas for r in normalized_roles
                ):
                    raise HTTPException(status_code=403, detail="Workspace access denied")
            break

    workspace_name = ""
    if region_ctxs:
        endpoint = region_ctxs[0].ctx_region.endpoint or ""
        if "/api/workspaces/" in endpoint:
            workspace_name = endpoint.split("/api/workspaces/")[1].split("/")[0]

    stats: dict[str, dict[str, Any]] = {}
    seen_regions: set[str] = set()
    for ctx in region_ctxs:
        aggregates = ctx.ctx_region.aggregates
        if not aggregates:
            continue
        region_name = ctx.ctx_region.name
        if region_name in seen_regions:
            continue
        seen_regions.add(region_name)

        metrics = await _compute_aggregate_metrics(
            aggregates,
            ctx.repositories,
            total=0,
            items=[],
        )
        stats[region_name] = {m["label"]: m["value"] for m in metrics}

    return {"workspace": workspace_name, "stats": stats}


async def _fetch_count_metric(
    metric_name: str,
    agg_repo: Any,
    where_clause: str | None,
    scope_filters: dict[str, Any] | None = None,
) -> tuple[str, Any]:
    """Fetch a single count aggregate metric from a repository."""
    try:
        agg_filters: dict[str, Any] | None = None
        if where_clause:
            agg_filters = _parse_simple_where(where_clause)
        # SECURITY: merge scope predicates into aggregate filters (#574)
        if scope_filters:
            agg_filters = {**(agg_filters or {}), **scope_filters}
        agg_result = await agg_repo.list(page=1, page_size=1, filters=agg_filters)
        if isinstance(agg_result, dict):
            return metric_name, agg_result.get("total", 0)
    except Exception:
        logger.warning("Failed to compute aggregate metric %s", metric_name, exc_info=True)
    return metric_name, 0


def _resolve_fk_target_spec(
    source_repo: Any,
    group_by: str,
    repositories: dict[str, Any] | None,
) -> Any | None:
    """Walk source_entity → field(group_by) → ref_entity → other repo's spec.

    Returns the target entity's EntitySpec when ``group_by`` is an FK,
    or None when it's a scalar / enum / state field. Used to drive
    ``aggregate.resolve_fk_display_field`` so the bar label resolves
    to the human-readable column on the related entity.
    """
    spec = getattr(source_repo, "entity_spec", None)
    if spec is None or repositories is None:
        return None
    field = next((f for f in getattr(spec, "fields", []) if f.name == group_by), None)
    if field is None:
        return None
    ftype = getattr(field, "type", None)
    if ftype is None or getattr(ftype, "kind", None) != "ref":
        return None
    target_entity = getattr(ftype, "ref_entity", None)
    if not target_entity:
        return None
    target_repo = repositories.get(target_entity)
    return getattr(target_repo, "entity_spec", None) if target_repo else None


async def _compute_pivot_buckets(
    aggregates: dict[str, str],
    repositories: dict[str, Any] | None,
    group_by_dims: list[Any],
    *,
    source_entity: str | None,
    source_entity_spec: Any,
    scope_filters: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Multi-dimension aggregate for pivot_table regions (cycle 25).

    Returns ``(buckets, dim_specs)`` where:
      * ``buckets`` is a list of ``{dim_<name>: <id>, dim_<name>_label:
        <display>, <metric>: <value>, ...}`` dicts ready for the
        template to render rows from;
      * ``dim_specs`` is a list of ``{name, label, is_fk}`` describing
        each dimension column header.

    For each dim that's a FK on the source entity, the runtime resolves
    the target's display field and routes the LEFT JOIN through
    ``Repository.aggregate``. Scalar dims pass through verbatim.
    """
    if not aggregates or not repositories or not source_entity:
        return [], []

    from dazzle_back.runtime.aggregate import Dimension, resolve_fk_display_field

    # Only the simple case (count(<source_entity>) with no current_bucket)
    # routes through the pivot fast path. Other shapes fall through.
    metric_name, expr = next(iter(aggregates.items()))
    agg_match = _AGGREGATE_RE.match(expr)
    if not agg_match or agg_match.group(1) != "count":
        return [], []
    _, entity_name, where_clause = agg_match.groups()
    if entity_name != source_entity or (where_clause and "current_bucket" in where_clause):
        return [], []

    source_repo = repositories.get(source_entity)
    if source_repo is None:
        return [], []

    # Resolve each dim — FK target spec (if any), display field via probe,
    # or time-bucket via BucketRef (cycle 28).
    from dazzle.core.ir import BucketRef

    dimensions: list[Dimension] = []
    dim_specs: list[dict[str, Any]] = []
    for dim_entry in group_by_dims:
        if isinstance(dim_entry, BucketRef):
            # Time-bucketed dim — no FK, no enum, just date_trunc on the
            # timestamp column. The label generator in _format_bucket_label
            # handles the display format.
            dimensions.append(Dimension(name=dim_entry.field, truncate=dim_entry.unit))  # type: ignore[arg-type]
            dim_specs.append(
                {
                    "name": dim_entry.field,
                    "label": dim_entry.field.replace("_", " ").title(),
                    "is_fk": False,
                    "is_time_bucket": True,
                    "unit": dim_entry.unit,
                }
            )
            continue

        dim_name = dim_entry
        fld = next(
            (f for f in getattr(source_entity_spec, "fields", []) if f.name == dim_name),
            None,
        )
        ftype = getattr(fld, "type", None) if fld else None
        is_fk = ftype is not None and getattr(ftype, "kind", None) == "ref"
        fk_table = None
        fk_display_field = None
        if is_fk:
            target_name = getattr(ftype, "ref_entity", None)
            target_repo = repositories.get(target_name) if target_name else None
            target_spec = getattr(target_repo, "entity_spec", None) if target_repo else None
            fk_table = target_name
            fk_display_field = resolve_fk_display_field(target_spec)
        dimensions.append(
            Dimension(name=dim_name, fk_table=fk_table, fk_display_field=fk_display_field)
        )
        dim_specs.append(
            {
                "name": dim_name,
                "label": dim_name.replace("_", " ").title(),
                "is_fk": bool(fk_table and fk_display_field),
                "is_time_bucket": False,
                "unit": None,
            }
        )

    # Merge any author-supplied where clause + scope filters.
    merged_filters: dict[str, Any] = {}
    if where_clause:
        merged_filters.update(_parse_simple_where(where_clause))
    if scope_filters:
        merged_filters = {**scope_filters, **merged_filters}

    try:
        buckets = await source_repo.aggregate(
            dimensions=dimensions,
            measures={metric_name: "count"},
            filters=merged_filters or None,
        )
    except Exception:
        # Promoted to ERROR for #854 — a silent WARNING on a pivot region's
        # only failure path made the root cause invisible in production logs.
        # The dimensions + merged filter dict are logged so operators can
        # reproduce the exact SQL via `dazzle db explain-aggregate` without
        # needing repository internals.
        logger.error(
            "Pivot aggregate FAILED for %s by %r — returning empty buckets. "
            "dimensions=%r filters=%r",
            source_entity,
            group_by_dims,
            [(d.name, d.fk_table, d.fk_display_field, d.truncate) for d in dimensions],
            merged_filters or None,
            exc_info=True,
        )
        return [], dim_specs

    out: list[dict[str, Any]] = []
    for b in buckets:
        row: dict[str, Any] = {}
        for spec in dim_specs:
            raw = b.dimensions.get(spec["name"])
            row[spec["name"]] = raw
            if spec["is_fk"]:
                lbl_key = f"{spec['name']}_label"
                row[lbl_key] = b.dimensions.get(lbl_key) or raw
            elif spec.get("is_time_bucket"):
                # Formatted label + ISO string for chart axes / JSON.
                row[f"{spec['name']}_label"] = _format_bucket_label(raw, spec["unit"])
                if isinstance(raw, _dt.datetime | _dt.date):
                    row[spec["name"]] = raw.isoformat()
        for k, v in b.measures.items():
            row[k] = v
        out.append(row)
    return out, dim_specs


async def _aggregate_via_groupby(
    agg_repo: Any,
    *,
    metric_name: str,
    group_by: Any,  # str | BucketRef
    where_clause: str | None,
    scope_filters: dict[str, Any] | None,
    source_entity_spec: Any,
    fk_target_spec: Any | None,
) -> list[dict[str, Any]]:
    """Run the bar-chart distribution as a single GROUP BY query.

    Strategy C — replaces the N+1 enumerate-then-per-bucket-count
    pipeline (#847–#851) with one ``Repository.aggregate`` call. The
    aggregate method composes ``SELECT <dim>, COUNT(*) FROM src LEFT
    JOIN <fk>... WHERE <scope> GROUP BY <dim>`` and returns the buckets
    + counts in a single round-trip. No enumeration phase, no per-bucket
    queries, no possibility of the two paths producing different scoped
    row sets.
    """
    from dazzle.core.ir import BucketRef
    from dazzle_back.runtime.aggregate import Dimension, resolve_fk_display_field

    # Merge any author-supplied where clause into the filter dict via
    # _parse_simple_where — same semantics the slow path used to apply
    # before its per-bucket extension.
    merged_filters: dict[str, Any] = {}
    if where_clause:
        merged_filters.update(_parse_simple_where(where_clause))
    if scope_filters:
        merged_filters = {**scope_filters, **merged_filters}

    # Time-bucketed single-dim path — no FK join, date_trunc in SQL.
    if isinstance(group_by, BucketRef):
        bucket_dim = Dimension(name=group_by.field, truncate=group_by.unit)  # type: ignore[arg-type]
        buckets = await agg_repo.aggregate(
            dimensions=[bucket_dim],
            measures={metric_name: "count"},
            filters=merged_filters or None,
        )
        out: list[dict[str, Any]] = []
        for b in buckets:
            raw = b.dimensions.get(group_by.field)
            if raw is None:
                continue
            label = _format_bucket_label(raw, group_by.unit)
            iso = raw.isoformat() if isinstance(raw, _dt.datetime | _dt.date) else str(raw)
            out.append(
                {
                    "label": label,
                    "value": b.measures.get(metric_name, 0),
                    "bucket": iso,
                }
            )
        return out

    fk_table = getattr(fk_target_spec, "name", None) if fk_target_spec is not None else None
    fk_display_field = (
        resolve_fk_display_field(fk_target_spec) if fk_target_spec is not None else None
    )

    dim = Dimension(name=group_by, fk_table=fk_table, fk_display_field=fk_display_field)
    buckets = await agg_repo.aggregate(
        dimensions=[dim],
        measures={metric_name: "count"},
        filters=merged_filters or None,
    )

    out = []
    for b in buckets:
        bucket_id = b.dimensions.get(group_by)
        if bucket_id is None:
            continue
        label_key = f"{group_by}_label"
        label = b.dimensions.get(label_key) or str(bucket_id)
        out.append({"label": str(label), "value": b.measures.get(metric_name, 0)})
    return out


async def _enumerate_distinct_buckets(
    source_repo: Any,
    group_by: str,
    scope_filters: dict[str, Any] | None,
    fetch_cap: int = 1000,
) -> tuple[list[tuple[str, str]], bool]:
    """Pull distinct group_by values from the SOURCE entity (#849, #850).

    Pre-fix the bucket list was derived from the region's first items page
    — so any group_by value that didn't happen to appear on page 1 was
    silently absent from the chart. For FK / high-cardinality columns
    that's most of them.

    Pages through the source repo (cap at ``fetch_cap`` rows) and dedupes
    on the bucket key. Reuses ``_bucket_key_label`` so FK-dict cells
    bucket on id and render on display field, matching the per-bucket
    filter semantics in ``_compute_bucketed_aggregates``.

    The source query passes ``include=[group_by]`` so FK columns come back
    as ``{id, <display_field>, ...}`` dicts (#850) — without it the repo
    serialiser drops the relation and ``_bucket_key_label`` only sees the
    raw FK UUID, producing UUID-as-label bars.

    Returns ``(buckets, succeeded)``:
      * ``succeeded=True`` — the source query ran without raising, even
        if zero rows came back. Caller must not fall back to items-page
        derivation in this case (a true empty state should render as
        no bars, not as page-1 fallback).
      * ``succeeded=False`` — the source query raised and the caller
        should fall back to items-page derivation as a last resort.
    """
    seen_keys: set[str] = set()
    out: list[tuple[str, str]] = []
    page_size = 200
    page = 1
    fetched = 0
    while fetched < fetch_cap:
        try:
            result = await source_repo.list(
                page=page,
                page_size=page_size,
                filters=scope_filters,
                include=[group_by],
            )
        except Exception:
            logger.warning(
                "Failed to enumerate distinct buckets for %s — falling back to "
                "items-page derivation",
                group_by,
                exc_info=True,
            )
            return out, False
        items = result.get("items", []) if isinstance(result, dict) else []
        if not items:
            break
        for item in items:
            it = item.model_dump() if hasattr(item, "model_dump") else dict(item)
            v = it.get(group_by)
            if v is None:
                continue
            key, label = _bucket_key_label(v)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            out.append((key, label))
        fetched += len(items)
        if len(items) < page_size:
            break
        page += 1
    return out, True


def _compute_histogram_bins(
    items: list[dict[str, Any]],
    value_field: str,
    bin_count: int | None,
) -> list[dict[str, Any]]:
    """Bin numeric values from ``items`` into equal-width buckets (#882).

    Returns one dict per bin in ascending order, each with:
      ``label``    – ``"<lo>–<hi>"`` (rounded for display),
      ``count``    – number of items whose ``value_field`` falls in [lo, hi),
      ``low``      – numeric lower edge (inclusive),
      ``high``     – numeric upper edge (exclusive, except final bin which
                     is closed so the global max isn't dropped).

    ``bin_count`` semantics:
      ``None``  → Sturges' rule: ⌈log2(N) + 1⌉, clamped to [1, 50].
      ``int``   → exact bin count (caller validates ≥ 1).

    Returns ``[]`` for empty input or when no item has a numeric value at
    ``value_field`` — the template falls back to its empty-state message.
    """
    import math

    raw_values: list[float] = []
    for item in items:
        v = item.get(value_field)
        if v is None:
            continue
        try:
            raw_values.append(float(v))
        except (TypeError, ValueError):
            continue

    if not raw_values:
        return []

    lo, hi = min(raw_values), max(raw_values)
    if lo == hi:
        # Single distinct value — one degenerate bin so the chart still
        # renders something meaningful instead of a divide-by-zero.
        return [
            {"label": f"{lo:g}", "count": len(raw_values), "low": lo, "high": hi},
        ]

    if bin_count is None:
        sturges = math.ceil(math.log2(len(raw_values)) + 1) if len(raw_values) > 1 else 1
        bin_count = max(1, min(sturges, 50))

    width = (hi - lo) / bin_count
    buckets: list[dict[str, Any]] = [
        {"low": lo + i * width, "high": lo + (i + 1) * width, "count": 0} for i in range(bin_count)
    ]

    for v in raw_values:
        # Final bin is closed on the right so v == hi lands in the last
        # bucket instead of falling through.
        idx = min(int((v - lo) / width), bin_count - 1)
        buckets[idx]["count"] += 1

    for b in buckets:
        b["label"] = f"{b['low']:g}–{b['high']:g}"

    return buckets


async def _compute_bucketed_aggregates(
    aggregates: dict[str, str],
    repositories: dict[str, Any] | None,
    group_by: Any,  # str | BucketRef
    items: list[dict[str, Any]],
    bucket_values: list[str] | None = None,
    scope_filters: dict[str, Any] | None = None,
    source_entity: str | None = None,
) -> list[dict[str, Any]]:
    """Evaluate aggregate expressions once per bucket — for bar_chart distributions.

    Used by bar_chart regions when both ``group_by`` and ``aggregates`` are
    declared. The ``current_bucket`` sentinel inside the where clause is
    substituted with each distinct group_by value before the count is
    fetched, so authors can express true distributions:

        aggregate:
          students: count(Manuscript where computed_grade = current_bucket)

    Closes #847 — previously bar_chart counted source rows per bucket and
    silently dropped the aggregate clause.

    Args:
        aggregates: Mapping of metric_name → expression. The first
            metric is the one rendered as the bar value.
        repositories: Repository registry keyed by entity name.
        group_by: Field name to bucket by.
        items: The source rows (used as a fallback bucket source when
            ``bucket_values`` is empty AND ``source_entity`` cannot be
            queried for distinct values).
        bucket_values: Pre-computed bucket list (e.g. enum values or
            state-machine states from ``kanban_columns``). When empty,
            distinct values are pulled from the source entity instead
            (#849).
        scope_filters: Scope predicates to merge into every per-bucket
            query (security gate per #574). Also applied to the
            distinct-bucket enumeration so users can't see buckets they
            wouldn't be allowed to see rows for.
        source_entity: The source entity name — used to resolve the
            source repo for distinct-bucket enumeration (#849 Bug B).
    """
    if not aggregates:
        return []

    metric_name, expr = next(iter(aggregates.items()))
    agg_match = _AGGREGATE_RE.match(expr)
    if not agg_match or agg_match.group(1) != "count":
        return []
    func, entity_name, where_clause = agg_match.groups()
    agg_repo = repositories.get(entity_name) if repositories else None
    if not agg_repo:
        return []

    # ---- Fast path: count(<source_entity>) with no current_bucket ----
    # This is the bar-chart distribution case (#847–#851) — replace the
    # enumerate-then-N+1-count pipeline with a single GROUP BY query
    # via Repository.aggregate. One SQL statement, one scope evaluation,
    # no possibility of enumeration/per-bucket divergence. The slow
    # sentinel path below stays for `count(OtherEntity where ... =
    # current_bucket)` expressions that need true per-bucket queries.
    from dazzle.core.ir import BucketRef as _BucketRef

    is_bucket_ref = isinstance(group_by, _BucketRef)
    is_simple_distribution = (
        not bucket_values  # caller didn't pre-supply enum/state buckets
        and source_entity is not None
        and entity_name == source_entity
        and (not where_clause or "current_bucket" not in (where_clause or ""))
    )
    # Time-bucketed distributions always take the GROUP BY path — there's no
    # per-bucket substitution to fall back to (current_bucket only makes sense
    # for enum / categorical group_by).
    if is_simple_distribution or is_bucket_ref:
        try:
            fk_target = None
            if not is_bucket_ref:
                fk_target = _resolve_fk_target_spec(agg_repo, group_by, repositories)
            return await _aggregate_via_groupby(
                agg_repo,
                metric_name=metric_name,
                group_by=group_by,
                where_clause=where_clause,
                scope_filters=scope_filters,
                source_entity_spec=getattr(agg_repo, "entity_spec", None),
                fk_target_spec=fk_target,
            )
        except Exception:
            logger.warning(
                "GROUP BY aggregate failed for %s.%r — falling back to N+1",
                entity_name,
                group_by,
                exc_info=True,
            )
            # fall through to the old loop on exception. Time buckets have
            # no N+1 fallback — they'll just return [] below.
            if is_bucket_ref:
                return []

    # ---- Slow path: per-bucket loop (enumeration + per-bucket count) ----
    # Used when the aggregate expression has a current_bucket sentinel
    # against a different entity, or when callers pre-supply bucket_values.
    # buckets is a list of (key, label). key goes into the per-bucket
    # filter; label renders on the bar. For FK group_by fields the list
    # endpoint serialises rows as `{id, <display_field>, ...}` dicts —
    # the old `str(dict)` produced a Python-repr string for both, so
    # filters never matched and labels rendered as junk (#848).
    if bucket_values:
        buckets: list[tuple[str, str]] = [(str(b), str(b)) for b in bucket_values]
    else:
        # Prefer enumerating distinct values from the source entity (#849
        # Bug B) so buckets that don't appear on the region's first items
        # page still render. Items-page derivation is a last-resort
        # fallback and only fires when the source query itself raises
        # — a successful-but-empty enumeration is a true empty state and
        # must not be papered over with a page-1 derivation that would
        # show stale or wrong-scope buckets (#850).
        source_repo = repositories.get(source_entity) if (repositories and source_entity) else None
        enum_succeeded = False
        if source_repo is not None:
            buckets, enum_succeeded = await _enumerate_distinct_buckets(
                source_repo, group_by, scope_filters
            )
        else:
            buckets = []
        if not buckets and not enum_succeeded:
            seen_keys: set[str] = set()
            derived: list[tuple[str, str]] = []
            for item in items:
                v = item.get(group_by)
                if v is None:
                    continue
                key, label = _bucket_key_label(v)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                derived.append((key, label))
            buckets = derived

    if not buckets:
        return []

    async def _per_bucket(bucket_key: str, bucket_label: str) -> tuple[str, int]:
        # When the expression has no current_bucket sentinel, build the
        # filter dict directly — bypassing _parse_simple_where avoids any
        # parser quirks around UUIDs / dashes / whitespace (#849 Bug A).
        if not where_clause or "current_bucket" not in where_clause:
            try:
                base_filters: dict[str, Any] = {}
                if where_clause:
                    base_filters = _parse_simple_where(where_clause)
                base_filters[group_by] = bucket_key
                if scope_filters:
                    base_filters = {**scope_filters, **base_filters}
                # Mirror the items list call exactly (#851): pass
                # include=[group_by] so the FK column is loaded the same
                # way the items endpoint does. Some repo backends only
                # apply column-type coercion (UUID etc.) on relations
                # they're aware of via include — without it the WHERE
                # filter against an FK UUID column can silently match
                # zero rows.
                agg_result = await agg_repo.list(
                    page=1,
                    page_size=1,
                    filters=base_filters,
                    include=[group_by],
                )
                value = agg_result.get("total", 0) if isinstance(agg_result, dict) else 0
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "bucketed-aggregate %s[%s=%s] → total=%s (filters=%r)",
                        metric_name,
                        group_by,
                        bucket_key,
                        value,
                        base_filters,
                    )
                return bucket_label, value
            except Exception:
                logger.warning(
                    "Per-bucket query failed for %s = %s",
                    group_by,
                    bucket_key,
                    exc_info=True,
                )
                return bucket_label, 0

        # Sentinel path: substitute and round-trip through _parse_simple_where.
        sub_clause = where_clause.replace("current_bucket", str(bucket_key))
        _, value = await _fetch_count_metric(metric_name, agg_repo, sub_clause, scope_filters)
        return bucket_label, value

    results = await asyncio.gather(
        *(_per_bucket(key, label) for key, label in buckets),
        return_exceptions=True,
    )

    out: list[dict[str, Any]] = []
    for r in results:
        if isinstance(r, BaseException):
            logger.warning("Bucketed aggregate query failed: %s", r)
            continue
        bucket_label, value = r
        out.append({"label": bucket_label, "value": value})
    return out


# Display-field probe order for FK dicts. `name` and `title` are common
# defaults; `code` / `label` cover enum-like reference data (e.g.
# AssessmentObjective.code, GradeBoundary.label). `display_name` is the
# convention used by user-management and FK display injection (#571).
_FK_DISPLAY_FIELDS: tuple[str, ...] = (
    "display_name",
    "name",
    "title",
    "label",
    "code",
)


def _bucket_key_label(value: Any) -> tuple[str, str]:
    """Derive (filter_key, render_label) from a group_by cell value (#848).

    For FK fields the list endpoint serialises the related row as a dict
    (``{id, <display_field>, ...}``). The id is what the per-bucket
    filter needs; the display field is what should render on the bar.
    Scalars pass through with key == label.
    """
    if isinstance(value, dict):
        # Prefer 'id' as the filter key; fall back to first key with a
        # primitive value so non-id-keyed dicts still bucket sensibly.
        key = value.get("id")
        if key is None:
            for _k, v in value.items():
                if isinstance(v, str | int | float | bool):
                    key = v
                    break
        key_str = str(key) if key is not None else str(value)
        for field in _FK_DISPLAY_FIELDS:
            if field in value and value[field]:
                return key_str, str(value[field])
        return key_str, key_str
    return str(value), str(value)


async def _compute_aggregate_metrics(
    aggregates: dict[str, str],
    repositories: dict[str, Any] | None,
    total: int,
    items: list[dict[str, Any]],
    scope_filters: dict[str, Any] | None = None,
    delta: Any | None = None,  # ir.DeltaSpec | None — see #884
) -> list[dict[str, Any]]:
    """Compute aggregate metrics, batching independent DB queries concurrently.

    When ``delta`` is set (#884), each metric also gets a prior-period value
    computed via a second aggregate query with date-range filters on
    ``delta.date_field`` (defaults to ``created_at``). The metric dict gains
    ``delta`` (current - prior), ``delta_pct``, ``delta_direction``
    (up|down|flat), ``delta_sentiment`` (positive_up|positive_down|neutral),
    and ``delta_period_label`` keys. Renderer uses these to emit the trend
    arrow + comparison line on summary/metrics tiles.
    """
    # Separate metrics into async (need DB query) and sync (computed from existing data)
    async_tasks: list[tuple[str, Any]] = []  # (metric_name, coroutine)
    sync_results: dict[str, Any] = {}  # metric_name -> value
    metric_order: list[str] = []

    for metric_name, expr in aggregates.items():
        metric_order.append(metric_name)
        agg_match = _AGGREGATE_RE.match(expr)
        if agg_match:
            func, entity_name, where_clause = agg_match.groups()
            agg_repo = repositories.get(entity_name) if repositories else None
            if func == "count" and agg_repo:
                async_tasks.append(
                    (
                        metric_name,
                        _fetch_count_metric(metric_name, agg_repo, where_clause, scope_filters),
                    )
                )
            else:
                sync_results[metric_name] = 0
        elif expr == "count":
            sync_results[metric_name] = total
        elif expr.startswith("sum:") and items:
            field_name = expr.split(":", 1)[1]
            sync_results[metric_name] = sum(float(i.get(field_name, 0) or 0) for i in items)
        else:
            sync_results[metric_name] = 0

    # Fire all async queries concurrently
    if async_tasks:
        results = await asyncio.gather(*(coro for _, coro in async_tasks), return_exceptions=True)
        for result in results:
            if isinstance(result, tuple):
                sync_results[result[0]] = result[1]
            elif isinstance(result, BaseException):
                logger.warning("Aggregate metric query failed: %s", result)

    # Build output in original order
    built_metrics = [
        {
            "label": name.replace("_", " ").title(),
            "value": sync_results.get(name, 0),
        }
        for name in metric_order
    ]

    # v0.61.25 (#884): period-over-period delta. For each count() metric,
    # fire a second aggregate over the prior window so the template can
    # render the trend arrow + comparison line.
    if delta is not None and aggregates and repositories:
        from datetime import datetime, timedelta

        period = timedelta(seconds=delta.period_seconds)
        now = datetime.now(_dt.UTC)
        prior_start = now - 2 * period
        prior_end = now - period
        date_field = delta.date_field or "created_at"

        prior_tasks: list[Any] = []
        prior_metric_names: list[str] = []
        for metric_name, expr in aggregates.items():
            agg_match = _AGGREGATE_RE.match(expr)
            if not agg_match:
                continue
            func, entity_name, where_clause = agg_match.groups()
            agg_repo = repositories.get(entity_name)
            if func != "count" or not agg_repo:
                continue
            prior_filters: dict[str, Any] = {}
            if where_clause:
                prior_filters.update(_parse_simple_where(where_clause))
            if scope_filters:
                prior_filters.update(scope_filters)
            prior_filters[f"{date_field}__gte"] = prior_start.isoformat()
            prior_filters[f"{date_field}__lt"] = prior_end.isoformat()
            prior_tasks.append(_fetch_count_metric(metric_name, agg_repo, None, prior_filters))
            prior_metric_names.append(metric_name)

        prior_map: dict[str, Any] = {}
        if prior_tasks:
            prior_results = await asyncio.gather(*prior_tasks, return_exceptions=True)
            for result in prior_results:
                if isinstance(result, tuple):
                    prior_map[result[0]] = result[1]

        for metric_name, m in zip(metric_order, built_metrics, strict=False):
            if metric_name not in prior_map:
                continue
            try:
                current_val = float(m["value"])
                prior_val = float(prior_map[metric_name])
            except (TypeError, ValueError):
                continue
            delta_val = current_val - prior_val
            pct = (delta_val / prior_val * 100.0) if prior_val else 0.0
            direction = "up" if delta_val > 0 else ("down" if delta_val < 0 else "flat")
            m["delta"] = int(delta_val) if delta_val == int(delta_val) else round(delta_val, 2)
            m["delta_pct"] = round(pct, 1)
            m["delta_direction"] = direction
            m["delta_sentiment"] = delta.sentiment
            m["delta_period_label"] = delta.period_label

    return built_metrics


def _parse_simple_where(where_clause: str) -> dict[str, Any]:
    """Parse simple WHERE clause to repository filter dict.

    Supports: ``field = value``, ``field != value``, ``field > value``, etc.
    Multiple conditions joined with ``and``.
    """
    filters: dict[str, Any] = {}
    parts = [p.strip() for p in where_clause.split(" and ")]
    for part in parts:
        for op, suffix in [
            ("!=", "__ne"),
            (">=", "__gte"),
            ("<=", "__lte"),
            (">", "__gt"),
            ("<", "__lt"),
            ("=", ""),
        ]:
            if op in part:
                field, value = [x.strip() for x in part.split(op, 1)]
                key = f"{field}{suffix}" if suffix else field
                filters[key] = value
                break
    return filters
