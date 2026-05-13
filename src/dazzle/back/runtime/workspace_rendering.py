"""Workspace rendering helpers extracted from server.py.

Contains functions for building workspace region data, computing aggregate
metrics, and rendering workspace regions as HTML or JSON.

Post-#1057 (v0.67.100): column-metadata builders moved to
``workspace_columns.py``. Old import paths preserved as re-exports
below so external callers keep working.
"""

import logging
from typing import Any

# Aggregation machinery — #1057 cut 4 moved these to workspace_aggregation.
# Re-imported because `_workspace_region_handler` (below) dispatches to
# them and ~30 test sites import them from this module.
from dazzle.back.runtime.workspace_aggregation import (  # noqa: F401
    _AGGREGATE_RE,
    _aggregate_via_groupby,
    _bucket_key_label,
    _build_aggregate_filters,
    _compute_aggregate_metrics,
    _compute_box_plot_stats,
    _compute_bucketed_aggregates,
    _compute_histogram_bins,
    _compute_pivot_buckets,
    _enumerate_distinct_buckets,
    _fetch_count_metric,
    _fetch_scalar_metric,
    _format_bucket_label,
    _parse_simple_where,
    _resolve_fk_target_spec,
)

# Card-body renderers — #1057 cut 2 moved these to workspace_card_bodies.
# Imported here because `_build_entity_card_sections` (below) dispatches
# to them by display mode.
# Card-data shapers — #1057 cut 3 moved these to workspace_card_data.
# Imported here because `_build_entity_card_sections` (below) dispatches
# to them by display mode, and tests still import them from this module.
from dazzle.back.runtime.workspace_card_data import (  # noqa: F401
    _CARD_TEMPLATE_RE,
    _build_cohort_cells,
    _build_day_timeline_slots,
    _build_task_inbox_payload,
    _coerce_pipeline_progress,
    _coerce_urgency,
    _initials_from,
    _inject_display_names,
    _interpolate_card_template,
    _items_from_template,
    _resolve_display_name,
    _resolve_path,
    _resolve_task_inbox_multi_source,
)
from dazzle.back.runtime.workspace_card_fetchers import (  # noqa: F401
    _build_entity_card_sections,
    _empty_list_coro,
    _fetch_entity_card_section_rows,
    _fetch_task_inbox_items_per_source,
    _safe_fetch,
)

# Re-exports for back-compat — #1057 moved these to workspace_columns.
from dazzle.back.runtime.workspace_columns import (
    build_entity_columns as _build_entity_columns,  # noqa: F401
)
from dazzle.back.runtime.workspace_columns import (
    build_surface_columns as _build_surface_columns,  # noqa: F401
)
from dazzle.back.runtime.workspace_columns import (
    field_kind_to_col_type as _field_kind_to_col_type,  # noqa: F401
)
from dazzle.back.runtime.workspace_context import WorkspaceRegionContext  # noqa: F401
from dazzle.back.runtime.workspace_csv import _render_csv_response  # noqa: F401
from dazzle.back.runtime.workspace_region_computes import compute_columns_for_persona
from dazzle.back.runtime.workspace_region_fetch import fetch_region_items
from dazzle.back.runtime.workspace_region_orchestration import compute_region_render_inputs
from dazzle.back.runtime.workspace_region_prelude import resolve_request_user_context
from dazzle.back.runtime.workspace_region_render import render_region_html
from dazzle.back.runtime.workspace_scope import _apply_workspace_scope_filters  # noqa: F401
from dazzle.back.runtime.workspace_user import _resolve_workspace_user  # noqa: F401

logger = logging.getLogger(__name__)


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
    from fastapi.responses import HTMLResponse

    # Phase 1: auth gate + identity resolution + filter-context build.
    # Raises HTTPException(401/403) if the request is unauthorised.
    user_ctx = await resolve_request_user_context(request, ctx)

    # Phase 2: filters + sort + scope + repo.list. Returns the row
    # data plus the scope state downstream aggregate paths gate on.
    fetched = await fetch_region_items(request, ctx, user_ctx, sort, dir, page, page_size)

    # Phase 3: column metadata — pre-computed visible:-filtered columns
    # from startup, or auto-derived from the first item's keys (#872).
    if ctx.precomputed_columns:
        columns = compute_columns_for_persona(
            ctx.precomputed_columns,
            list(user_ctx.auth_ctx_for_filters.roles) if user_ctx.auth_ctx_for_filters else [],
        )
    elif fetched.items:
        columns = [
            {
                "key": k,
                "label": k.replace("_", " ").title(),
                "type": "text",
                "sortable": True,
            }
            for k in fetched.items[0].keys()
            if k != "id"
        ]
    else:
        columns = []

    # CSV export (#562) — short-circuits the typed-primitive render.
    if request.query_params.get("format") == "csv":
        return _render_csv_response(fetched.items, columns, ctx.ctx_region.name)

    # Phases 4-5: build every shape the render tail consumes.
    render_inputs = await compute_region_render_inputs(request, ctx, user_ctx, fetched, columns)

    # Phase 6: typed-primitive render + region-chrome wrap.
    html_body = await render_region_html(request, ctx, user_ctx, render_inputs, sort, dir)
    return HTMLResponse(content=html_body)
