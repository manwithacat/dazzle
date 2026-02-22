"""Workspace rendering helpers extracted from server.py.

Contains functions for building workspace region data, computing aggregate
metrics, and rendering workspace regions as HTML or JSON.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Regex for aggregate expressions like count(Task) or count(Task where status = open)
# Tolerates whitespace around parens and entity name (DSL parser joins tokens with spaces).
_AGGREGATE_RE = re.compile(r"\s*(count|sum|avg|min|max)\s*\(\s*(\w+)\s*(?:where\s+(.+?))?\s*\)")


def _field_kind_to_col_type(field: Any, entity: Any = None) -> str:
    """Map an IR field to a column rendering type for workspace templates.

    Args:
        field: FieldSpec IR object.
        entity: Optional EntitySpec — when provided, checks if this field
                is the state-machine status field and returns ``"badge"``.
    """
    ft = getattr(field, "type", None)
    kind = getattr(ft, "kind", None)
    kind_val: str = kind.value if hasattr(kind, "value") else str(kind) if kind else ""  # type: ignore[union-attr]
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
        sm = getattr(entity, "state_machine", None)
        if sm and getattr(sm, "status_field", None) == getattr(field, "name", None):
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

    # Collect field names from surface sections (preserving order)
    surface_fields: list[str] = []
    for section in getattr(surface_spec, "sections", []):
        for element in getattr(section, "elements", []):
            fn = getattr(element, "field_name", None)
            if fn and fn != "id" and fn not in surface_fields:
                surface_fields.append(fn)

    if not surface_fields:
        return _build_entity_columns(entity_spec)

    # Build a lookup from entity fields
    field_map: dict[str, Any] = {f.name: f for f in entity_spec.fields}

    columns: list[dict[str, Any]] = []
    for fn in surface_fields:
        f = field_map.get(fn)
        if not f:
            continue
        ft = getattr(f, "type", None)
        kind = getattr(ft, "kind", None)
        kind_val: str = (
            kind.value if hasattr(kind, "value") else str(kind) if kind else ""  # type: ignore[union-attr]
        )
        # Ref fields
        if kind_val == "ref":
            rel_name = f.name[:-3] if f.name.endswith("_id") else f.name
            ref_entity = getattr(ft, "ref_entity", None)
            ref_route = f"/{to_api_plural(str(ref_entity))}/{{id}}" if ref_entity else ""
            columns.append(
                {
                    "key": rel_name,
                    "label": getattr(f, "label", None) or rel_name.replace("_", " ").title(),
                    "type": "ref",
                    "sortable": False,
                    "ref_route": ref_route,
                }
            )
            continue
        # Skip non-displayable types
        if kind_val in ("uuid", "has_many", "has_one", "embeds", "belongs_to"):
            continue
        col_type = _field_kind_to_col_type(f, entity_spec)
        col_key = f"{f.name}_minor" if kind_val == "money" else f.name
        col: dict[str, Any] = {
            "key": col_key,
            "label": getattr(f, "label", None) or f.name.replace("_", " ").title(),
            "type": col_type,
            "sortable": True,
        }
        if kind_val == "money":
            col["currency_code"] = getattr(getattr(f, "type", None), "currency_code", None) or "GBP"
        if col_type == "badge":
            if kind_val == "enum":
                ev = getattr(ft, "enum_values", None)
                if ev:
                    col["filterable"] = True
                    col["filter_options"] = list(ev)
            else:
                sm = getattr(entity_spec, "state_machine", None)
                if sm:
                    states = getattr(sm, "states", [])
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
        ft = getattr(f, "type", None)
        kind = getattr(ft, "kind", None)
        kind_val: str = (
            kind.value if hasattr(kind, "value") else str(kind) if kind else ""  # type: ignore[union-attr]
        )
        # Show ref columns with resolved display name; hide other relation types
        if kind_val == "ref":
            rel_name = f.name[:-3] if f.name.endswith("_id") else f.name
            ref_entity = getattr(ft, "ref_entity", None)
            # Ensure ref_entity is a plain string (not a pydantic/Cython object)
            ref_route = f"/{to_api_plural(str(ref_entity))}/{{id}}" if ref_entity else ""
            columns.append(
                {
                    "key": rel_name,
                    "label": getattr(f, "label", None) or rel_name.replace("_", " ").title(),
                    "type": "ref",
                    "sortable": False,
                    "ref_route": ref_route,
                }
            )
            continue
        if kind_val in ("uuid", "has_many", "has_one", "embeds", "belongs_to"):
            continue
        if f.name.endswith("_id"):
            continue
        col_type = _field_kind_to_col_type(f, entity_spec)
        col_key = f.name
        if kind_val == "money":
            col_key = f"{f.name}_minor"
        col: dict[str, Any] = {
            "key": col_key,
            "label": getattr(f, "label", None) or f.name.replace("_", " ").title(),
            "type": col_type,
            "sortable": True,
        }
        if kind_val == "money":
            ft_obj = getattr(f, "type", None)
            col["currency_code"] = getattr(ft_obj, "currency_code", None) or "GBP"
        if col_type == "badge":
            if kind_val == "enum":
                ev = getattr(ft, "enum_values", None)
                if ev:
                    col["filterable"] = True
                    col["filter_options"] = list(ev)
            else:
                sm = getattr(entity_spec, "state_machine", None)
                if sm:
                    states = getattr(sm, "states", [])
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
    # Surface UX metadata (#362)
    surface_default_sort: list[Any] = field(default_factory=list)
    surface_empty_message: str = ""


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

        # RBAC: enforce workspace persona restrictions on region data
        if ctx.ws_access and ctx.ws_access.allow_personas and auth_ctx:
            is_super = auth_ctx.user and auth_ctx.user.is_superuser
            if not is_super and not any(r in ctx.ws_access.allow_personas for r in auth_ctx.roles):
                raise HTTPException(status_code=403, detail="Workspace access denied")

    # Resolve current user ID for filter expressions (e.g. reviewer == current_user)
    _current_user_id: str | None = None
    if ctx.require_auth and ctx.auth_middleware:
        try:
            _auth = ctx.auth_middleware.get_auth_context(request)
            if _auth and _auth.is_authenticated and _auth.user:
                _current_user_id = str(_auth.user.id)
        except Exception:
            logger.debug("Failed to resolve current user for filter context", exc_info=True)
    _filter_context: dict[str, Any] = {}
    if _current_user_id:
        _filter_context["current_user_id"] = _current_user_id

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
            ir_filter = getattr(ctx, "_source_filter", None) or getattr(
                ctx.ir_region, "filter", None
            )
            if ir_filter is not None:
                try:
                    from dazzle_back.runtime.condition_evaluator import (
                        condition_to_sql_filter,
                    )

                    filters = condition_to_sql_filter(
                        ir_filter.model_dump(exclude_none=True),
                        context=_filter_context,
                    )
                except Exception:
                    logger.warning("Failed to evaluate condition filter", exc_info=True)

            # Build sort — user sort param > IR region sort > surface UX sort (#362)
            sort_list: list[str] | None = None
            if sort:
                sort_list = [f"-{sort}" if dir == "desc" else sort]
            else:
                ir_sort = getattr(ctx.ir_region, "sort", [])
                if ir_sort:
                    sort_list = [
                        f"-{s.field}" if getattr(s, "direction", "asc") == "desc" else s.field
                        for s in ir_sort
                    ]
                elif ctx.surface_default_sort:
                    sort_list = [
                        f"-{s.field}" if getattr(s, "direction", "asc") == "desc" else s.field
                        for s in ctx.surface_default_sort
                    ]

            # Collect interactive filters from query params
            for param_key, param_val in request.query_params.items():
                if param_key.startswith("filter_") and param_val:
                    field_name = param_key[7:]  # strip "filter_"
                    if filters is None:
                        filters = {}
                    filters[field_name] = param_val

            # Build include list for eager-loading ref fields (#272)
            include_rels: list[str] = []
            if ctx.entity_spec and hasattr(ctx.entity_spec, "fields"):
                for f in ctx.entity_spec.fields:
                    ft = getattr(f, "type", None)
                    kind = getattr(ft, "kind", None)
                    kind_val_str: str = getattr(kind, "value", str(kind)) if kind else ""
                    if kind_val_str == "ref":
                        # Relation name is the field name without _id suffix
                        rel_name = f.name[:-3] if f.name.endswith("_id") else f.name
                        include_rels.append(rel_name)

            # Grouped views need enough items to distribute across columns
            if (
                ctx.ctx_region.display in ("KANBAN", "BAR_CHART", "FUNNEL_CHART")
                and not ctx.ctx_region.limit
            ):
                limit = min(page_size, 200) if page_size > 20 else 50
            else:
                limit = ctx.ctx_region.limit or page_size
            result = await repo.list(
                page=page,
                page_size=limit,
                filters=filters,
                sort=sort_list,
                include=include_rels or None,
            )
            if isinstance(result, dict):
                raw_items = result.get("items", [])
                total = result.get("total", 0)
                items = [i.model_dump() if hasattr(i, "model_dump") else dict(i) for i in raw_items]
        except Exception:
            logger.warning("Failed to list items for workspace region", exc_info=True)

    # Use pre-computed columns from startup (constant-folded from IR)
    if ctx.precomputed_columns:
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

    # Build aggregate metrics if configured
    metrics: list[dict[str, Any]] = []
    if ctx.ctx_region.aggregates:
        metrics = await _compute_aggregate_metrics(
            ctx.ctx_region.aggregates, ctx.repositories, total, items
        )

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
                    if _eval_cond(cond_dict, item, {}):
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
    group_by = ctx.ctx_region.group_by
    _grouped_modes = {"KANBAN", "BAR_CHART", "FUNNEL_CHART"}
    if group_by and ctx.ctx_region.display in _grouped_modes and ctx.entity_spec:
        # Try enum values first, then state machine states
        for f in getattr(ctx.entity_spec, "fields", []):
            if f.name == group_by:
                ft = getattr(f, "type", None)
                ev = getattr(ft, "enum_values", None)
                if ev:
                    kanban_columns = list(ev)
                break
        if not kanban_columns:
            sm = getattr(ctx.entity_spec, "state_machine", None)
            if sm and getattr(sm, "status_field", "") == group_by:
                states = getattr(sm, "states", [])
                kanban_columns = [
                    s if isinstance(s, str) else getattr(s, "name", str(s)) for s in states
                ]

    # Queue display: extract state machine transitions for inline action buttons
    queue_transitions: list[dict[str, str]] = []
    queue_status_field = ""
    queue_api_endpoint = ""
    if ctx.ctx_region.display == "QUEUE" and ctx.entity_spec:
        sm = getattr(ctx.entity_spec, "state_machine", None)
        if sm:
            queue_status_field = getattr(sm, "status_field", "status")
            seen: set[str] = set()
            for t in getattr(sm, "transitions", []):
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
    source_tabs = getattr(ctx.ctx_region, "source_tabs", []) or []

    html = render_fragment(
        ctx.ctx_region.template,
        title=ctx.ctx_region.title,
        items=items,
        total=total,
        columns=columns,
        metrics=metrics,
        empty_message=ctx.surface_empty_message or ctx.ctx_region.empty_message,
        display_key=columns[0]["key"] if columns else "name",
        item=items[0] if items else None,
        action_url=ctx.ctx_region.action_url,
        sort_field=sort or "",
        sort_dir=dir,
        endpoint=ctx.ctx_region.endpoint,
        region_name=ctx.ctx_region.name,
        filter_columns=filter_columns,
        active_filters=active_filters,
        group_by=group_by,
        kanban_columns=kanban_columns,
        queue_transitions=queue_transitions,
        queue_status_field=queue_status_field,
        queue_api_endpoint=queue_api_endpoint,
        source_tabs=source_tabs,
        source_entity=ctx.source,
    )
    return HTMLResponse(content=html)


async def _fetch_region_json(
    request: Any,
    page: int,
    page_size: int,
    ctx: WorkspaceRegionContext,
) -> dict[str, Any]:
    """Fetch a single region's data as JSON for batch responses."""
    repo = ctx.repositories.get(ctx.source) if ctx.repositories else None
    items: list[dict[str, Any]] = []
    total = 0

    if repo:
        try:
            filters: dict[str, Any] | None = None
            ir_filter = getattr(ctx.ir_region, "filter", None)
            if ir_filter is not None:
                try:
                    from dazzle_back.runtime.condition_evaluator import condition_to_sql_filter

                    filters = condition_to_sql_filter(
                        ir_filter.model_dump(exclude_none=True), context={}
                    )
                except Exception:
                    logger.warning("Failed to evaluate condition filter for region", exc_info=True)

            sort_list: list[str] | None = None
            ir_sort = getattr(ctx.ir_region, "sort", [])
            if ir_sort:
                sort_list = [
                    f"-{s.field}" if getattr(s, "direction", "asc") == "desc" else s.field
                    for s in ir_sort
                ]

            limit = ctx.ctx_region.limit or page_size
            result = await repo.list(page=page, page_size=limit, filters=filters, sort=sort_list)
            if isinstance(result, dict):
                raw_items = result.get("items", [])
                total = result.get("total", 0)
                items = [i.model_dump() if hasattr(i, "model_dump") else dict(i) for i in raw_items]
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
                if not is_super and not any(
                    r in ctx.ws_access.allow_personas for r in auth_ctx.roles
                ):
                    raise HTTPException(status_code=403, detail="Workspace access denied")
            break  # All regions share the same workspace access

    results = await asyncio.gather(
        *(_fetch_region_json(request, page, page_size, ctx) for ctx in region_ctxs),
        return_exceptions=True,
    )

    regions: list[dict[str, Any]] = []
    for result in results:
        if isinstance(result, dict):
            regions.append(result)
        elif isinstance(result, BaseException):
            logger.warning("Batch region query failed: %s", result)

    return {"regions": regions}


async def _fetch_count_metric(
    metric_name: str,
    agg_repo: Any,
    where_clause: str | None,
) -> tuple[str, Any]:
    """Fetch a single count aggregate metric from a repository."""
    try:
        agg_filters: dict[str, Any] | None = None
        if where_clause:
            agg_filters = _parse_simple_where(where_clause)
        agg_result = await agg_repo.list(page=1, page_size=1, filters=agg_filters)
        if isinstance(agg_result, dict):
            return metric_name, agg_result.get("total", 0)
    except Exception:
        logger.warning("Failed to compute aggregate metric %s", metric_name, exc_info=True)
    return metric_name, 0


async def _compute_aggregate_metrics(
    aggregates: dict[str, str],
    repositories: dict[str, Any] | None,
    total: int,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compute aggregate metrics, batching independent DB queries concurrently."""
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
                    (metric_name, _fetch_count_metric(metric_name, agg_repo, where_clause))
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
    return [
        {
            "label": name.replace("_", " ").title(),
            "value": sync_results.get(name, 0),
        }
        for name in metric_order
    ]


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
