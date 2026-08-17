"""Phase 2 of the workspace region handler — source entity query.

Extracted from ``_workspace_region_handler`` in #1057 cut 12 (v0.67.111).
Runs after the auth/identity prelude and produces the row data the
rest of the pipeline shapes.

Pipeline (per region request):

1. Build filters from the IR ``ConditionExpr`` (`current_user`,
   `has_grant()`, etc.) via ``_extract_condition_filters``.
2. Build the sort list — user param > IR region sort > surface UX
   default (#362).
3. Layer query-param filters (``filter_<key>=value``) and date-range
   filters (#566) on top.
4. Apply entity-level scope predicates (#574). The returned
   ``scope_only_filters`` is captured separately so downstream
   aggregate paths can stay tenant-bounded without re-mixing in
   request filters (#887).
5. Pick the page-size for grouped displays (KANBAN/BAR_CHART/
   FUNNEL_CHART/BOX_PLOT — #889) so paginated defaults surface all
   buckets.
6. Default-deny: if scope rules didn't match, short-circuit to an
   empty result without firing the query.
7. Query the repo. Inject FK display names (#571). Use the item
   count as the total (#573 — repo COUNT may not be scoped).
8. Fail-closed on any exception: empty items + ERROR-level
   structured log (#546, #935).

Returns a ``RegionItemsResult`` dataclass.
"""

import logging
from dataclasses import dataclass, field
from datetime import date as _date
from typing import Any

from dazzle.http.runtime.page_routes import (
    _parse_list_as_of,
    _parse_list_include_closed,
)
from dazzle.http.runtime.workspace_context import WorkspaceRegionContext
from dazzle.http.runtime.workspace_region_computes import (
    compute_filter_columns_and_active,
)
from dazzle.http.runtime.workspace_region_prelude import RequestUserContext
from dazzle.http.runtime.workspace_scope import _apply_workspace_scope_filters
from dazzle.render.display_names import _inject_display_names
from dazzle.render.fragment.renderer._render_interactive import (
    leftover_honest_entity_id,
    leftover_honest_iso_date,
)

logger = logging.getLogger(__name__)


@dataclass
class RegionItemsResult:
    """Phase 2 output: the row data + scope state downstream phases read.

    ``items`` are already FK-display-injected and pydantic-dumped to
    plain dicts.

    ``scope_only_filters`` is the scope predicate slice **without**
    the request/IR filters mixed in — downstream aggregate paths
    (metrics / bucketed / overlay / pivot) need the pure scope slice
    so their GROUP BY queries stay tenant-bounded without re-applying
    the row-level filters.

    ``context_filters`` (#1305) is the ``current_context`` slice of the
    region ``filter:`` — the context-selector boundary, isolated from the
    row-level ``status``/literal predicates. It rides *alongside*
    ``scope_only_filters`` into the aggregate paths so a bar_chart /
    group_by / metric region re-scopes when the workspace
    ``context_selector`` changes, exactly as the list path does. Empty
    when no ``context_id`` is bound (selector cleared) or the filter has
    no ``current_context`` term.

    ``scope_denied`` is the default-deny flag (#887): aggregate
    paths suppress their queries when this is True so an unfiltered
    SQL aggregate can't leak cross-tenant counts.
    """

    items: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    scope_only_filters: dict[str, Any] | None = None
    context_filters: dict[str, Any] | None = None  # #1305
    # Default-deny: any failure path that skips scope evaluation
    # MUST surface as a denial — initialised True here to match the
    # original handler's #887 semantics.
    scope_denied: bool = True


def _apply_leftover_honest_temporal(
    request: Any, repo: Any, filters: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Fold leftover-honest ``include_closed`` / ``as_of`` into list filters.

    Workspace CSV (`?format=csv`) reuses this fetch. Dropping valid
    temporal params invented open-only / current (cycle 2174). Leftover
    junk (`zzz`, `2abc`, `maybe`, `not-a-date`) restores default.
    Non-temporal entities ignore the raw.
    """
    temporal = getattr(getattr(repo, "entity_spec", None), "temporal", None)
    if temporal is None:
        return filters
    qparams = getattr(request, "query_params", None)
    if qparams is None:
        return filters
    as_of_param = getattr(temporal, "as_of_param", None) or "as_of"
    as_of_raw = _parse_list_as_of(qparams.get(as_of_param))
    include_closed = _parse_list_include_closed(qparams.get("include_closed"))
    if not as_of_raw and not include_closed:
        return filters
    out = dict(filters) if filters else {}
    if as_of_raw:
        out["__as_of"] = _date.fromisoformat(as_of_raw)
    if include_closed:
        out[f"{temporal.end_field}__isnull"] = False
    return out


def _apply_leftover_honest_date_window(
    request: Any, date_field: str, filters: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Fold leftover-honest ``date_from`` / ``date_to`` into list filters.

    Leftover junk (``zzz``, ``2abc``, ``not-a-date``) used to ride
    ``{date_field}__gte`` / ``__lte`` and invent an empty collection
    (cycle 2186). Valid YYYY-MM-DD still windows. Rest is unbounded
    (omit). Distinct from leftover ``as_of`` (oral #49).
    """
    if not date_field:
        return filters
    qparams = getattr(request, "query_params", None)
    if qparams is None:
        return filters
    date_from = leftover_honest_iso_date(qparams.get("date_from"))
    date_to = leftover_honest_iso_date(qparams.get("date_to"))
    if not date_from and not date_to:
        return filters
    out = dict(filters) if filters else {}
    if date_from:
        out[f"{date_field}__gte"] = date_from
    if date_to:
        out[f"{date_field}__lte"] = date_to
    return out


def _apply_leftover_honest_filter_enums(
    request: Any,
    filters: dict[str, Any] | None,
    columns: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Fold leftover-honest ``filter_<enum>=`` into list filters.

    Picker restore All already exists (oral #69 /
    ``compute_filter_columns_and_active``). Fetch still applied raw
    ``filters[field]=param_val``, so leftover junk (``zzz``, ``ghost``)
    invented an empty collection while the picker showed All (cycle
    2190). Valid declared options ride. Rest is All (omit). Live
    FilterBar / support_tickets ``Ticket.status``.
    """
    qparams = getattr(request, "query_params", None)
    if qparams is None:
        return filters
    _, active = compute_filter_columns_and_active(list(columns or []), qparams)
    if not active:
        return filters
    out = dict(filters) if filters else {}
    out.update(active)
    return out


def _apply_leftover_honest_item_id(
    request: Any, filters: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Fold leftover-honest ``?id=`` into DETAIL filters.

    dual_pane master-detail hx-get ``?id=<pk>`` into the DETAIL pane.
    Leftover junk (``zzz``, ``ghost``, ``not-a-uuid``) used to invent
    an empty DETAIL via ``filters['id']`` (cycle 2189). Valid UUID
    still selects. Rest is unbound (omit). Oral #71 one-ship close.
    Live in contact_manager ``contacts`` ``contact_detail``.
    """
    qparams = getattr(request, "query_params", None)
    if qparams is None:
        return filters
    item_id = leftover_honest_entity_id(qparams.get("id"))
    if not item_id:
        return filters
    out = dict(filters) if filters else {}
    out["id"] = item_id
    return out


async def fetch_region_items(
    request: Any,
    ctx: WorkspaceRegionContext,
    user_ctx: RequestUserContext,
    sort: str | None,
    sort_dir: str,
    page: int,
    page_size: int,
) -> RegionItemsResult:
    """Phase 2: build filters/sort + apply scope + query repo.

    Fail-closed: any exception logs at ERROR with structured context
    (#935) and returns the default (empty items, scope_denied=True).
    Zero results from a successful query is a valid empty state — the
    region renders its ``empty:`` message rather than falling back
    to an unfiltered query (#546).
    """
    repo = ctx.repositories.get(ctx.source) if ctx.repositories else None
    if repo is None:
        return RegionItemsResult()

    try:
        # Step 1: filters from IR ConditionExpr (current_user, has_grant, etc.).
        # Multi-source regions store a per-source filter on `_source_filter`.
        filters: dict[str, Any] | None = None
        ir_filter = getattr(ctx, "_source_filter", None) or ctx.ir_region.filter
        if ir_filter is not None:
            try:
                from dazzle.http.runtime.scope_filters import _extract_condition_filters

                filters = {}
                _extract_condition_filters(
                    ir_filter,
                    user_ctx.user_id or "",
                    filters,
                    logger,
                    user_ctx.auth_ctx_for_filters,
                    # #1304: thread the source entity's FK→target map so a
                    # multi-hop dotted `current_context` filter (e.g.
                    # `assessment_event.teaching_group = current_context`)
                    # resolves to an FK-path subquery instead of a raw dotted
                    # key the repo can't map (which silently matched all rows).
                    ref_targets=ctx.entity_ref_targets.get(ctx.source) or {},
                    context_id=user_ctx.filter_context.get("current_context"),
                    # #1304: the global entity→FK-map so a 2-hop dotted path
                    # resolves the *target* entity's FK column correctly
                    # (`teaching_group` → `teaching_group_id`) rather than
                    # blindly suffixing `_id` (which broke bare-named FKs).
                    all_ref_targets=ctx.entity_ref_targets,
                )
                if not filters:
                    filters = None
            except Exception:
                logger.warning("Failed to evaluate condition filter", exc_info=True)

        # Step 2: sort list — user param > IR > surface default (#362).
        sort_list: list[str] | None = None
        if sort:
            sort_list = [f"-{sort}" if sort_dir == "desc" else sort]
        else:
            ir_sort = ctx.ir_region.sort
            if ir_sort:
                sort_list = [f"-{s.field}" if s.direction == "desc" else s.field for s in ir_sort]
            elif ctx.surface_default_sort:
                sort_list = [
                    f"-{s.field}" if s.direction == "desc" else s.field
                    for s in ctx.surface_default_sort
                ]

        # Step 3: leftover-honest query-param filters + date-range (#566).
        # Leftover ``filter_<enum>=junk`` must not invent empty (oral #72).
        filters = _apply_leftover_honest_filter_enums(request, filters, ctx.precomputed_columns)

        # dual_pane master-detail: DETAIL region fragment for one selected row.
        # List rows hx-get ``?id=<pk>`` into ``.dz-master-detail__detail``.
        # Leftover junk must not invent empty DETAIL (oral #71 close).
        filters = _apply_leftover_honest_item_id(request, filters)

        # Leftover-honest include_closed / as_of (cycle 2174). Bare CSV
        # downloads used to drop these so the file invented open-only /
        # current. Leftover junk restores default; valid true / YYYY-MM-DD
        # reach repo.list (__as_of / end_field__isnull=False).
        filters = _apply_leftover_honest_temporal(request, repo, filters)

        date_field = ctx.ctx_region.date_field if hasattr(ctx.ctx_region, "date_field") else ""
        filters = _apply_leftover_honest_date_window(request, date_field, filters)

        # Step 4: entity-level scope predicates (#574).
        scope_only_filters, scope_denied = _apply_workspace_scope_filters(
            ctx, user_ctx.auth_ctx_for_filters, user_ctx.user_id, None
        )
        if scope_only_filters:
            filters = {**(filters or {}), **scope_only_filters}

        # Step 4b (#1305): isolate the `current_context` slice of the region
        # filter so the aggregate paths can re-scope by the context selector
        # without re-mixing the row-level literals (#887). The list query above
        # already resolved current_context into `filters`; this second pass
        # extracts JUST the context terms (same FK-path resolution as #1304),
        # which `compute_region_render_inputs` merges into the aggregate
        # scope filters. Empty when no context_id is bound or no current_context
        # term exists.
        context_filters: dict[str, Any] = {}
        if ir_filter is not None and user_ctx.filter_context.get("current_context"):
            try:
                from dazzle.http.runtime.scope_filters import _extract_condition_filters

                _extract_condition_filters(
                    ir_filter,
                    user_ctx.user_id or "",
                    context_filters,
                    logger,
                    user_ctx.auth_ctx_for_filters,
                    ref_targets=ctx.entity_ref_targets.get(ctx.source) or {},
                    context_id=user_ctx.filter_context.get("current_context"),
                    all_ref_targets=ctx.entity_ref_targets,
                    context_only=True,
                )
            except Exception:
                logger.warning("Failed to isolate current_context filter", exc_info=True)
                context_filters = {}

        # Step 5: page-size for grouped displays (#889).
        include_rels = ctx.auto_include
        if (
            ctx.ctx_region.display in ("KANBAN", "BAR_CHART", "FUNNEL_CHART", "BOX_PLOT")
            and not ctx.ctx_region.limit
        ):
            limit = min(page_size, 200) if page_size > 20 else 50
        else:
            limit = ctx.ctx_region.limit or page_size

        # Step 6: default-deny — empty result without firing the query.
        if scope_denied:
            result: dict[str, Any] = {"items": [], "total": 0}
        else:
            # Free-text find-by-name (?q= / ?search=) when surface/FTS declares
            # search_fields — filters the list in place (ILIKE). Distinct from
            # display:search_box FTS results panel under the input.
            search_q = (
                request.query_params.get("q") or request.query_params.get("search") or ""
            ).strip()
            search_fields = list(getattr(ctx, "search_fields", None) or [])
            list_kwargs: dict[str, Any] = {
                "page": page,
                "page_size": limit,
                "filters": filters,
                "sort": sort_list,
                "include": include_rels or None,
                "fk_display_only": True,
            }
            if search_q and search_fields:
                list_kwargs["search"] = search_q
                list_kwargs["search_fields"] = search_fields
            result = await repo.list(**list_kwargs)

        # Step 7: inject display names; use item count as total (#573).
        items: list[dict[str, Any]] = []
        total = 0
        if isinstance(result, dict):
            raw_items = result.get("items", [])
            items = [i.model_dump() if hasattr(i, "model_dump") else dict(i) for i in raw_items]
            items = [_inject_display_names(item) for item in items]
            total = len(items)

        return RegionItemsResult(
            items=items,
            total=total,
            scope_only_filters=scope_only_filters,
            context_filters=context_filters or None,
            scope_denied=scope_denied,
        )

    except Exception as exc:
        # Step 8: fail-closed (#546). ERROR-level + structured log (#935)
        # so backend errors don't hide in WARN noise.
        logger.error(
            "workspace_region_query_failed entity=%s region=%s exc=%s",
            ctx.source,
            ctx.ctx_region.name,
            type(exc).__name__,
            exc_info=True,
        )
        return RegionItemsResult()
