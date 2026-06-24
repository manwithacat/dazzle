"""Workspace sibling request handlers: region-JSON, batch, stats.

Extracted from workspace_rendering.py in #1057 cut 6 (v0.67.105).
The three handlers here all reuse `_workspace_region_handler`
(the main region renderer) underneath but wrap it for different
response shapes:

- `_fetch_region_json`: single-region JSON (used by the SPA-style
  re-fetch path after a mutation).
- `_workspace_batch_handler`: fetch N regions in one round-trip,
  sharing one scope-filter computation.
- `_workspace_stats_handler`: workspace-level KPI rollup
  (metrics-only response, no row data).
"""

import asyncio
import logging
from typing import Any

from dazzle.http.runtime.auth.dependencies import _bind_rls_tenant_id
from dazzle.http.runtime.workspace_aggregation import _compute_aggregate_metrics
from dazzle.http.runtime.workspace_context import WorkspaceRegionContext
from dazzle.http.runtime.workspace_scope import _apply_workspace_scope_filters
from dazzle.http.runtime.workspace_user import _resolve_workspace_user
from dazzle.render.display_names import _inject_display_names

logger = logging.getLogger(__name__)


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

    # SECURITY (#887): mirror `_workspace_region_handler` — default-deny
    # scope state so a missing repo or early exception doesn't bypass
    # the gate on `_compute_aggregate_metrics` below.
    _scope_only_filters_batch: dict[str, Any] | None = None
    _scope_denied: bool = True

    if repo:
        try:
            filters: dict[str, Any] | None = None
            ir_filter = ctx.ir_region.filter
            if ir_filter is not None:
                try:
                    from dazzle.http.runtime.scope_filters import (
                        _extract_condition_filters,
                    )

                    filters = {}
                    _extract_condition_filters(
                        ir_filter,
                        user_id or (filter_context or {}).get("current_user_id", ""),
                        filters,
                        logger,
                        auth_context,
                        # #1304: thread FK→target map for multi-hop dotted
                        # `current_context` resolution (batch JSON path).
                        ref_targets=ctx.entity_ref_targets.get(ctx.source) or {},
                        context_id=(filter_context or {}).get("current_context"),
                        all_ref_targets=ctx.entity_ref_targets,  # #1304
                    )
                    if not filters:
                        filters = None
                except Exception:
                    logger.warning("Failed to evaluate condition filter for region", exc_info=True)

            sort_list: list[str] | None = None
            ir_sort = ctx.ir_region.sort
            if ir_sort:
                sort_list = [f"-{s.field}" if s.direction == "desc" else s.field for s in ir_sort]

            # SECURITY: apply entity-level scope predicates (#574).
            # Capture scope-only filters (without other request filters
            # mixed in) so `_compute_aggregate_metrics` below can run a
            # scope-aware aggregate query — unfiltered aggregates leak
            # cross-tenant counts (#887).
            _scope_only_filters_batch, _scope_denied = _apply_workspace_scope_filters(
                ctx, auth_context, user_id, None
            )
            if _scope_only_filters_batch:
                filters = {**(filters or {}), **_scope_only_filters_batch}

            # #1305: isolate the `current_context` slice so the aggregate
            # metrics below re-scope by the context selector (batch JSON path),
            # mirroring the single-region path in compute_region_render_inputs.
            _ctx_id_batch = (filter_context or {}).get("current_context")
            if ir_filter is not None and _ctx_id_batch:
                try:
                    from dazzle.http.runtime.scope_filters import (
                        _extract_condition_filters,
                    )

                    _ctx_filters_batch: dict[str, Any] = {}
                    _extract_condition_filters(
                        ir_filter,
                        user_id or (filter_context or {}).get("current_user_id", ""),
                        _ctx_filters_batch,
                        logger,
                        auth_context,
                        ref_targets=ctx.entity_ref_targets.get(ctx.source) or {},
                        context_id=_ctx_id_batch,
                        all_ref_targets=ctx.entity_ref_targets,
                        context_only=True,
                    )
                    if _ctx_filters_batch:
                        _scope_only_filters_batch = {
                            **(_scope_only_filters_batch or {}),
                            **_ctx_filters_batch,
                        }
                except Exception:
                    logger.warning(
                        "Failed to isolate current_context filter (batch)", exc_info=True
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
        except Exception as exc:
            # #935: ERROR-level + structured (see _workspace_region_handler
            # above for rationale). Same fail-closed semantics.
            logger.error(
                "workspace_region_query_failed entity=%s region=%s exc=%s context=batch",
                ctx.source,
                ctx.ctx_region.name,
                type(exc).__name__,
                exc_info=True,
            )

    # SECURITY (#887): suppress aggregates when scope is denied AND
    # propagate the scope-only filters so the aggregate query stays
    # tenant-bounded for the legitimate case.
    metrics: list[dict[str, Any]] = []
    if ctx.ctx_region.aggregates and not _scope_denied:
        metrics = await _compute_aggregate_metrics(
            ctx.ctx_region.aggregates,
            ctx.repositories,
            total,
            items,
            scope_filters=_scope_only_filters_batch,
            source_entity=ctx.source,  # #888 Phase 1
            tones=getattr(ctx.ctx_region, "tones", None),  # v0.61.65
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
            logger.warning("Batch: failed to get auth context", exc_info=True)

    # #1466: bind the per-request RLS GUCs so the batched region reads below run
    # with dazzle.tenant_id resolved (this handler self-authenticates, so the
    # auth dependency's _bind_rls_tenant_id never runs). Without it a shared_schema
    # /RLS app denies every row → empty regions. Same fix as the region path; the
    # prefs splice above means current_user.<attr> scope GUCs also bind.
    if _batch_auth_ctx is not None:
        _bind_rls_tenant_id(_batch_auth_ctx)

    # Legacy filter context for backward compat
    _batch_filter_ctx: dict[str, Any] = {}
    if _batch_user_id:
        _batch_filter_ctx["current_user_id"] = _batch_user_id
    if _batch_user_entity:
        _batch_filter_ctx["current_user_entity"] = _batch_user_entity
    # #1394: host-resolved tenant for `current_tenant[.attr]` display gates.
    from dazzle.http.runtime.tenant_render_context import inject_current_tenant

    inject_current_tenant(_batch_filter_ctx, request)

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
    _stats_auth_ctx: Any = None
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
            _stats_auth_ctx = auth_ctx
            break

    # #1466: bind dazzle.tenant_id before the scope-aware aggregate queries below.
    # This handler self-authenticates, so the auth dependency's _bind_rls_tenant_id
    # never runs — without it the aggregate's leased connection reads an unset
    # tenant GUC and a shared_schema/RLS app fences every row → all stats are 0.
    if _stats_auth_ctx is not None:
        _bind_rls_tenant_id(_stats_auth_ctx)

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
            source_entity=ctx.source,  # #888 Phase 1
        )
        stats[region_name] = {m["label"]: m["value"] for m in metrics}

    return {"workspace": workspace_name, "stats": stats}
