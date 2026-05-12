"""Workspace rendering helpers extracted from server.py.

Contains functions for building workspace region data, computing aggregate
metrics, and rendering workspace regions as HTML or JSON.

Post-#1057 (v0.67.100): column-metadata builders moved to
``workspace_columns.py``. Old import paths preserved as re-exports
below so external callers keep working.
"""

import datetime as _dt
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
from dazzle.back.runtime.workspace_region_computes import (
    apply_attention_signals,
    compute_action_grid,
    compute_bar_track,
    compute_bullet,
    compute_columns_for_persona,
    compute_confirm_action_state,
    compute_filter_columns_and_active,
    compute_heatmap,
    compute_kanban_columns,
    compute_pipeline_steps,
    compute_profile_card,
    compute_progress,
    compute_queue,
    compute_tree,
)
from dazzle.back.runtime.workspace_region_fetch import fetch_region_items
from dazzle.back.runtime.workspace_region_prelude import resolve_request_user_context
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
    _current_user_id = user_ctx.user_id
    _auth_ctx_for_filters = user_ctx.auth_ctx_for_filters
    _filter_context = user_ctx.filter_context

    # Phase 2: filters + sort + scope + repo.list. Returns the row
    # data plus the scope state downstream aggregate paths gate on.
    fetched = await fetch_region_items(request, ctx, user_ctx, sort, dir, page, page_size)
    items = fetched.items
    total = fetched.total
    _scope_only_filters = fetched.scope_only_filters
    _scope_denied = fetched.scope_denied
    columns: list[dict[str, Any]] = []

    # Use pre-computed columns from startup (constant-folded from IR),
    # filtered by per-persona visible: predicates (#872).
    if ctx.precomputed_columns:
        columns = compute_columns_for_persona(
            ctx.precomputed_columns,
            list(_auth_ctx_for_filters.roles) if _auth_ctx_for_filters else [],
        )
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

    # Build aggregate metrics if configured. SECURITY (#887): suppress
    # when scope is denied — unfiltered aggregates would leak counts /
    # sums / averages across tenants.
    metrics: list[dict[str, Any]] = []
    if ctx.ctx_region.aggregates and not _scope_denied:
        metrics = await _compute_aggregate_metrics(
            ctx.ctx_region.aggregates,
            ctx.repositories,
            total,
            items,
            scope_filters=_scope_only_filters,
            delta=ctx.ctx_region.delta,  # #884
            source_entity=ctx.source,  # #888 Phase 1
            tones=getattr(ctx.ctx_region, "tones", None),  # v0.61.65
        )

    # Bucketed aggregates for bar_chart distributions (#847). When a
    # bar_chart region declares both `group_by` and `aggregates`, evaluate
    # the first aggregate once per bucket so authors can express true
    # distributions instead of getting raw row counts. The bucket list
    # comes from `kanban_columns` when available (enum / state-machine
    # values), else falls back to distinct items[group_by].
    bucketed_metrics: list[dict[str, Any]] = []

    # Filter column metadata + active filters from the request.
    filter_columns, active_filters = compute_filter_columns_and_active(
        columns, request.query_params
    )

    # Annotate items with the highest-severity matching attention signal.
    apply_attention_signals(items, ctx.attention_signals, _filter_context)

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
        kanban_columns = compute_kanban_columns(ctx.entity_spec, group_by)

    # Compute bucketed aggregates for bar_chart / line_chart / sparkline —
    # single-dim distributions or time-series. Multi-dim (area_chart /
    # pivot_table) runs through _compute_pivot_buckets below.
    # SECURITY (#887): same gating as `metrics` above — bucketed
    # aggregates run their own SQL GROUP BY query and would leak
    # cross-tenant rows when scope is denied.
    _single_dim_chart_modes = {"BAR_CHART", "LINE_CHART", "SPARKLINE", "RADAR", "BAR_TRACK"}
    if (
        ctx.ctx_region.display in _single_dim_chart_modes
        and group_by
        and ctx.ctx_region.aggregates
        and not _scope_denied
    ):
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

    # Box plot (#881, v0.61.29): per-group quartile/whisker stats from the
    # already-fetched ``items``. Same in-process pattern as histogram.
    box_plot_stats: list[dict[str, Any]] = []
    if ctx.ctx_region.display == "BOX_PLOT":
        _value_field = (getattr(ctx.ctx_region, "heatmap_value", "") or "").strip()
        _bp_group_by = group_by if isinstance(group_by, str) else None
        _show_outliers = bool(getattr(ctx.ir_region, "show_outliers", True))
        if _value_field:
            box_plot_stats = _compute_box_plot_stats(
                items, _value_field, _bp_group_by, _show_outliers
            )

    # Overlay series (#883, v0.61.33): for line/area chart regions,
    # fire one extra `_compute_bucketed_aggregates` per overlay using
    # the parent's group_by but the overlay's own source/filter/aggregate.
    # Each overlay collapses to a list of {label, value} buckets that the
    # template renders as an additional polyline (line_chart) or stacked
    # layer (area_chart).
    overlay_series_data: list[dict[str, Any]] = []
    _ir_overlays = (getattr(ctx.ir_region, "overlay_series", None) if ctx.ir_region else None) or []
    # SECURITY (#887): overlays each fire a fresh `_compute_bucketed_aggregates`
    # against `_ovl_source` — same scope gate as the primary buckets above.
    if (
        _ir_overlays
        and ctx.ctx_region.display in {"LINE_CHART", "AREA_CHART"}
        and group_by
        and not _scope_denied
    ):
        for _overlay in _ir_overlays:
            _ovl_source = _overlay.source or ctx.source
            # Convert the overlay's filter ConditionExpr → flat dict for
            # the runtime via the same path scope_filters use. For the v1
            # we inline-merge the overlay's filter as the where_clause
            # of a synthetic `<aggregate_expr>` evaluated against
            # _ovl_source. Scope still applies (overlay sees the same
            # scope_filters as the primary aggregate).
            try:
                _overlay_aggregates = {_overlay.label: _overlay.aggregate_expr}
                _overlay_buckets = await _compute_bucketed_aggregates(
                    _overlay_aggregates,
                    ctx.repositories,
                    group_by,
                    items=[],  # overlay computes its own buckets via fast path
                    bucket_values=kanban_columns or None,
                    scope_filters=_scope_only_filters,
                    source_entity=_ovl_source,
                )
                overlay_series_data.append(
                    {
                        "label": _overlay.label,
                        "buckets": _overlay_buckets,
                    }
                )
            except Exception:
                logger.warning(
                    "Overlay series %r failed — skipping",
                    _overlay.label,
                    exc_info=True,
                )

    # Bullet chart (#880, v0.61.30): one row per item, reading three named
    # columns (label, actual, target) directly off the item. Pre-computed
    # MVP — per-group_by aggregation deferred (would need multi-measure
    # support in `_compute_bucketed_aggregates`). Reference_bands (#883)
    # render as comparative qualitative zones behind each bar.
    if ctx.ctx_region.display == "BULLET":
        bullet_rows, bullet_max_value = compute_bullet(
            items,
            label_field=getattr(ctx.ir_region, "bullet_label", None),
            actual_field=getattr(ctx.ir_region, "bullet_actual", None),
            target_field=getattr(ctx.ir_region, "bullet_target", None),
            reference_bands=getattr(ctx.ir_region, "reference_bands", None),
        )
    else:
        bullet_rows = []
        bullet_max_value = 0.0

    # Bar track (#893, v0.61.53): per-row label + filled track + value.
    # Reuses the single-dim chart pipeline — `bucketed_metrics` is
    # already populated above. Post-process into row dicts with a
    # computed `fill_pct` (value / track_max) and `formatted_value`
    # (Python format spec applied). The format spec runs in Python via
    # `format()` rather than Jinja so the template stays simple and we
    # don't risk template injection from an author-supplied format
    # string.
    if ctx.ctx_region.display == "BAR_TRACK" and bucketed_metrics:
        bar_track_rows, bar_track_max = compute_bar_track(
            bucketed_metrics,
            explicit_max=ctx.ctx_region.track_max,
            format_spec=ctx.ctx_region.track_format or "",
            region_name=ctx.ctx_region.name,
        )
    else:
        bar_track_rows = []
        bar_track_max = 0.0

    # Action grid (#891, v0.61.54): CTA cards on dashboards. Each card
    # carries a label/icon/url/tone (already resolved at context build
    # time) plus an optional `count_aggregate` expression that the
    # runtime fires per-card via the existing `_fetch_count_metric`
    # machinery. Single batched query is a future optimisation; MVP
    # fires concurrently via asyncio.gather.
    # SECURITY (#887): same scope gate as other aggregate paths — when
    # scope is denied the per-card counts are suppressed (cards still
    # render but with no count badge).
    if ctx.ctx_region.display == "ACTION_GRID":
        action_card_data: list[dict[str, Any]] = await compute_action_grid(
            ctx.ctx_region.action_cards or [],
            ctx.repositories,
            ctx.source,
            _scope_only_filters,
            _scope_denied,
        )
    else:
        action_card_data = []

    # Pipeline steps (#890, v0.61.56): sequential-stage workflow.
    # Each stage's `value` is either an aggregate expression (matches
    # `_AGGREGATE_RE` — fires a count query) OR a literal string
    # (renders verbatim — v0.61.66 AegisMark UX patterns #4). RBAC
    # scope rules apply per stage for the aggregate path. Stages with
    # empty value render `—`. Median and other not-yet-supported
    # aggregates also render `—` (only count is wired today).
    # Mirrors the action_grid pattern (#891).
    if ctx.ctx_region.display == "PIPELINE_STEPS":
        pipeline_stage_data: list[dict[str, Any]] = await compute_pipeline_steps(
            ctx.ctx_region.pipeline_stages or [],
            ctx.repositories,
            ctx.source,
            _scope_only_filters,
            _scope_denied,
        )
    else:
        pipeline_stage_data = []

    # Profile card (#892, v0.61.55): single-record identity panel.
    # Resolves the avatar, primary, secondary, stats, and facts from
    # the first item already fetched (the region's `filter:` should
    # narrow to one record — typically `id = current_context`).
    # Secondary + facts strings support tiny `{{ field }}` /
    # `{{ field.path }}` interpolation against the item dict — handled
    # server-side by `_interpolate_card_template` so the template is
    # logic-less. No Jinja eval, no expressions.
    if ctx.ctx_region.display == "PROFILE_CARD":
        profile_card_data: dict[str, Any] = compute_profile_card(items, ctx.ctx_region)
    else:
        profile_card_data = {}

    # v0.61.72 (#6): confirm_action_panel reads state_value from the
    # entity field named by `state_field` so the template can branch
    # between off / live / revoked render modes. Reads from the first
    # fetched item (callers typically narrow with `filter:`). Empty
    # string when no field configured or no item — template falls
    # through to the safe default ("off").
    if ctx.ctx_region.display == "CONFIRM_ACTION_PANEL":
        confirm_state_value: str = compute_confirm_action_state(
            items, getattr(ctx.ctx_region, "state_field", None)
        )
    else:
        confirm_state_value = ""

    # Multi-dimension aggregate for pivot_table (cycle 25) and area_chart
    # (cycle 28 — stacked time-series). Reads `group_by_dims` from the IR
    # and runs ONE multi-dim GROUP BY via Repository.aggregate. Each entry
    # is a column on the source entity or a BucketRef for time-bucketed
    # dims; FK columns auto-LEFT JOIN their target so the bucket carries
    # the resolved display field.
    # SECURITY (#887): same gating — `_compute_pivot_buckets` runs a
    # multi-dim GROUP BY query and would expose unscoped tenant rows.
    pivot_buckets: list[dict[str, Any]] = []
    pivot_dim_specs: list[dict[str, Any]] = []
    _multi_dim_modes = {"PIVOT_TABLE", "AREA_CHART"}
    _ir_group_by_dims = getattr(ctx.ir_region, "group_by_dims", None) if ctx.ir_region else None
    if (
        ctx.ctx_region.display in _multi_dim_modes
        and _ir_group_by_dims
        and ctx.ctx_region.aggregates
        and not _scope_denied
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
    if ctx.ctx_region.display == "QUEUE" and ctx.entity_spec:
        queue_transitions, queue_status_field, queue_api_endpoint = compute_queue(
            ctx.entity_spec, ctx.source
        )
    else:
        queue_transitions = []
        queue_status_field = ""
        queue_api_endpoint = ""

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
        from dazzle.back.runtime.param_store import resolve_value

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
        heatmap_matrix, heatmap_col_values = compute_heatmap(
            items,
            rows_field=getattr(ctx.ctx_region, "heatmap_rows", "") or "",
            cols_field=getattr(ctx.ctx_region, "heatmap_columns", "") or "",
            value_field=getattr(ctx.ctx_region, "heatmap_value", "") or "",
        )

    # Progress: count items per stage and compute percentage (v0.44.0)
    progress_stages_list: list[str] = list(getattr(ctx.ctx_region, "progress_stages", None) or [])
    progress_complete_at: str = getattr(ctx.ctx_region, "progress_complete_at", "") or ""
    if ctx.ctx_region.display == "PROGRESS" and items and progress_stages_list:
        _prog = compute_progress(
            items, progress_stages_list, progress_complete_at, group_by or "status"
        )
        progress_stage_counts: list[dict[str, Any]] = _prog["stage_counts"]
        progress_total: int = _prog["total"]
        progress_complete_count: int = _prog["complete_count"]
        progress_complete_pct: float = _prog["complete_pct"]
    else:
        progress_stage_counts = []
        progress_total = 0
        progress_complete_count = 0
        progress_complete_pct = 0.0

    # Tree display (#565) — build nested hierarchy from flat items
    display_upper = ctx.ctx_region.display
    if display_upper == "TREE" and group_by and items:
        tree_items = compute_tree(items, group_by)

    # Phase 4 region migration (v0.67.46): the typed-primitive path
    # extends beyond the original #1015–#1018 special cases. Region
    # kinds whose adapter builder is mature + whose data shape matches
    # the legacy Jinja partial's expectations are listed here; they
    # bypass the Jinja body in favour of FragmentRenderer output.
    # Adding a new display value is one entry in this whitelist plus
    # a matching `adapter_ctx[...]` population below.
    typed_primitive_html: str = ""
    _TYPED_REGION_DISPLAYS = (
        "COHORT_STRIP",
        "DAY_TIMELINE",
        "TASK_INBOX",
        "ENTITY_CARD",
        "PROGRESS",  # Phase 4 region migration (v0.67.46)
        # Phase 4 region migration batch (v0.67.47):
        "DETAIL",
        "TREE",
        "DIAGRAM",
        "SEARCH_BOX",
        "TABBED_LIST",
        # Phase 4 region migration batch (v0.67.48):
        "GRID",
        "HEATMAP",
        "SPARKLINE",
        "STATUS_LIST",
        "PROFILE_CARD",
        # Phase 4 region migration batch (v0.67.49):
        "METRICS",
        "FUNNEL_CHART",
        "HISTOGRAM",
        "PIVOT_TABLE",
        "TIMELINE",
        "KANBAN",
        "PIPELINE_STEPS",
        "QUEUE",
        "ACTION_GRID",
        "CONFIRM_ACTION_PANEL",
        # Phase 4 region migration batch (v0.67.50): chart + specialty:
        "BAR_CHART",
        "LINE_CHART",
        "AREA_CHART",
        "BAR_TRACK",
        "BULLET",
        "BOX_PLOT",
        "ACTIVITY_FEED",
        # Phase 4 region migration (v0.67.51): foundational list-view
        # — the richest ctx contract (sort/filter state, FilterBar,
        # CSV export, date-range picker, RBAC propagation, bulk
        # actions plumbing).
        "LIST",
        # Phase 4 region migration (v0.67.70): radar polar chart —
        # `_build_radar` consumes (label, value) axis pairs from the
        # legacy `bucketed_metrics` shape; the typed Radar primitive
        # does its own polygon/polar math.
        "RADAR",
    )
    if display_upper in _TYPED_REGION_DISPLAYS:
        from dazzle.back.runtime.renderers.region_adapter import WorkspaceRegionAdapter
        from dazzle.render.fragment import FragmentRenderer

        # Adapter wants the lowercase display value (its _BUILDERS
        # keys) on `region.display`, plus the IR config slots. Use
        # the IR region directly — it carries the typed configs.
        ir_region = ctx.ir_region or ctx.ctx_region
        # Force a lowercase display value if the IR carries the
        # uppercase enum (defensive — most callers already lowercase).
        _display_obj = getattr(ir_region, "display", None)
        _display_val = getattr(_display_obj, "value", None) or str(_display_obj or "")
        if _display_val and _display_val.upper() == display_upper:
            adapter_ctx: dict[str, Any] = {
                "region_url": getattr(ctx.ctx_region, "endpoint", "") or "",
            }
            # Per-display data resolution. Each branch reads its own
            # typed config off the IR region and shapes `items` (or
            # other already-scoped data) into the dict shape the
            # adapter consumes. Empty config = empty/unconfigured state
            # in the primitive (handled by the adapter).
            if display_upper == "COHORT_STRIP":
                _cohort_cfg = getattr(ir_region, "cohort_strip_config", None)
                if _cohort_cfg is not None:
                    _active_lens_id = (
                        request.query_params.get("lens")
                        or getattr(_cohort_cfg, "default_lens", "")
                        or (getattr(_cohort_cfg.lenses[0], "id", "") if _cohort_cfg.lenses else "")
                    )
                    adapter_ctx["cohort_active_lens"] = _active_lens_id
                    adapter_ctx["cohort_cells"] = _build_cohort_cells(
                        items=items,
                        config=_cohort_cfg,
                        active_lens_id=_active_lens_id,
                    )
            elif display_upper == "DAY_TIMELINE":
                _day_cfg = getattr(ir_region, "day_timeline_config", None)
                if _day_cfg is not None:
                    adapter_ctx["day_timeline_slots"] = _build_day_timeline_slots(
                        items=items,
                        config=_day_cfg,
                        now=_dt.datetime.now(_dt.UTC),
                    )
            elif display_upper == "TASK_INBOX":
                _inbox_cfg = getattr(ir_region, "task_inbox_config", None)
                if _inbox_cfg is not None:
                    # #1015 (v0.67.16) — fan out per-source queries in
                    # parallel, scope each against its own entity's
                    # access spec, pass the items_per_source dict to
                    # the helper. Falls through to single-source MVP
                    # when the fan-out produces an empty dict (e.g.
                    # repositories not yet wired in test contexts).
                    _items_per_source = await _fetch_task_inbox_items_per_source(
                        config=_inbox_cfg,
                        ctx=ctx,
                        request=request,
                        auth_context=_auth_ctx_for_filters,
                        user_id=_current_user_id,
                    )
                    inbox_items, inbox_chips = _build_task_inbox_payload(
                        items=items,
                        config=_inbox_cfg,
                        items_per_source=_items_per_source,
                    )
                    adapter_ctx["task_inbox_items"] = inbox_items
                    adapter_ctx["task_inbox_chips"] = inbox_chips
            elif display_upper == "PROGRESS":
                # Phase 4 region migration (v0.67.46): progress's
                # adapter builder consumes pre-computed stage rollups
                # from `progress_stage_counts` etc. already populated
                # upstream in this function.
                adapter_ctx["stage_counts"] = progress_stage_counts
                adapter_ctx["progress_total"] = progress_total
                adapter_ctx["complete_count"] = progress_complete_count
                adapter_ctx["complete_pct"] = progress_complete_pct
                # Legacy `items` fallback the adapter's _build_progress
                # accepts when stage_counts is empty — pass through so
                # the synthetic-stage path keeps working.
                adapter_ctx["items"] = items
            elif display_upper == "DETAIL":
                # Phase 4 region migration batch (v0.67.47): detail's
                # adapter consumes a single record + the region's
                # declared field shape.
                adapter_ctx["item"] = items[0] if items else None
                adapter_ctx["fields"] = columns
            elif display_upper == "TREE":
                # _build_tree wants the pre-computed nested tree shape
                # already produced upstream by `_build_subtree`.
                adapter_ctx["tree_items"] = tree_items
                adapter_ctx["items"] = items
                adapter_ctx["display_key"] = next(
                    (c["key"] for c in columns if c.get("type") not in ("badge", "ref")),
                    columns[0]["key"] if columns else "name",
                )
            elif display_upper == "DIAGRAM":
                # _build_diagram prefers `diagram_data` (Mermaid source)
                # but falls back to nodes/edges from the IR region
                # when not pre-computed.
                adapter_ctx["nodes"] = getattr(ctx.ctx_region, "nodes", []) or []
                adapter_ctx["edges"] = getattr(ctx.ctx_region, "edges", []) or []
            elif display_upper == "SEARCH_BOX":
                # _build_search_box wants source_entity + region name +
                # optional placeholder/coaching message.
                adapter_ctx["source_entity"] = getattr(ctx, "source", "") or ""
                adapter_ctx["name"] = getattr(ctx.ctx_region, "name", "")
                adapter_ctx["placeholder"] = getattr(ctx.ctx_region, "search_placeholder", "") or ""
                adapter_ctx["coaching_message"] = (
                    getattr(ctx.ctx_region, "coaching_message", "") or ""
                )
            elif display_upper == "TABBED_LIST":
                # _build_tabbed_list prefers `source_tabs` (HTMX-driven
                # lazy panels) which the runtime already computed
                # upstream from the IR region's source declarations.
                adapter_ctx["region_name"] = getattr(ctx.ctx_region, "name", "")
                adapter_ctx["source_tabs"] = source_tabs
            elif display_upper == "GRID":
                # Phase 4 region migration batch (v0.67.48): grid renders
                # card cells from the scoped item rows + the region's
                # column declarations.
                adapter_ctx["items"] = items
                adapter_ctx["columns"] = columns
                adapter_ctx["display_key"] = next(
                    (c["key"] for c in columns if c.get("type") not in ("badge", "ref")),
                    columns[0]["key"] if columns else "name",
                )
                adapter_ctx["entity_name"] = ctx.source
            elif display_upper == "HEATMAP":
                # Threshold-tinted matrix from pre-computed aggregates.
                adapter_ctx["heatmap_matrix"] = heatmap_matrix
                adapter_ctx["heatmap_col_values"] = heatmap_col_values
                adapter_ctx["heatmap_thresholds"] = heatmap_thresholds
                adapter_ctx["total"] = total
                adapter_ctx["items"] = items
            elif display_upper == "SPARKLINE":
                # Sparkline is a TimeSeries view variant; its adapter
                # builder reads `points` as a list of label/value
                # tuples or dicts. `bucketed_metrics` is already that
                # shape.
                adapter_ctx["points"] = bucketed_metrics
                adapter_ctx["chart_label"] = ctx.ctx_region.title
            elif display_upper == "STATUS_LIST":
                # Authored entries forwarded directly from the IR region
                # — no per-request resolution needed (#3, v0.61.69).
                adapter_ctx["status_entries"] = getattr(ctx.ctx_region, "status_entries", [])
            elif display_upper == "PROFILE_CARD":
                # Pre-assembled identity-panel dict — built upstream in
                # this function around line 2424.
                adapter_ctx["profile_card_data"] = profile_card_data
            elif display_upper == "METRICS":
                # Phase 4 region migration batch (v0.67.49): metrics
                # tiles read pre-computed aggregate values + columns.
                adapter_ctx["metrics"] = metrics
                adapter_ctx["columns"] = columns
            elif display_upper == "FUNNEL_CHART":
                # Funnel uses kanban_columns for stage order +
                # bucketed_metrics for per-stage counts.
                adapter_ctx["kanban_columns"] = kanban_columns
                adapter_ctx["bucketed_metrics"] = bucketed_metrics
            elif display_upper == "HISTOGRAM":
                # Pre-computed bins from `_compute_histogram_bins`.
                adapter_ctx["histogram_bins"] = histogram_bins
                adapter_ctx["reference_lines"] = getattr(ctx.ctx_region, "reference_lines", [])
            elif display_upper == "PIVOT_TABLE":
                # Multi-dim pivot: workspace-shape primitive consumes
                # pivot_buckets + pivot_dim_specs directly.
                adapter_ctx["pivot_buckets"] = pivot_buckets
                adapter_ctx["pivot_dim_specs"] = pivot_dim_specs
                adapter_ctx["bucketed_metrics"] = bucketed_metrics
                adapter_ctx["columns"] = columns
            elif display_upper == "TIMELINE":
                # Timeline events from scoped items + column declarations.
                adapter_ctx["items"] = items
                adapter_ctx["columns"] = columns
                adapter_ctx["display_key"] = next(
                    (c["key"] for c in columns if c.get("type") not in ("badge", "ref")),
                    columns[0]["key"] if columns else "name",
                )
            elif display_upper == "KANBAN":
                # KanbanRegion workspace-shape: items + status order
                # + columns + display_key.
                adapter_ctx["items"] = items
                adapter_ctx["columns"] = columns
                adapter_ctx["kanban_columns"] = kanban_columns
                adapter_ctx["display_key"] = next(
                    (c["key"] for c in columns if c.get("type") not in ("badge", "ref")),
                    columns[0]["key"] if columns else "name",
                )
                adapter_ctx["group_by"] = (
                    group_by.field if isinstance(group_by, _BucketRef) else group_by
                )
            elif display_upper == "PIPELINE_STEPS":
                # Pre-computed per-stage rollups from upstream.
                adapter_ctx["pipeline_stage_data"] = pipeline_stage_data
            elif display_upper == "QUEUE":
                # Review queue: items + state-transition wiring + the
                # filter-chrome contract _build_list shares.
                adapter_ctx["items"] = items
                adapter_ctx["columns"] = columns
                adapter_ctx["total"] = total
                adapter_ctx["metrics"] = metrics
                adapter_ctx["queue_transitions"] = queue_transitions
                adapter_ctx["queue_status_field"] = queue_status_field
                adapter_ctx["queue_api_endpoint"] = queue_api_endpoint
            elif display_upper == "ACTION_GRID":
                # Pre-assembled CTA card list (legacy alias
                # `action_card_data` is the actual upstream name).
                adapter_ctx["action_cards"] = action_card_data
            elif display_upper == "BAR_CHART":
                # Phase 4 region migration batch (v0.67.50): bar_chart's
                # adapter consumes `buckets` (list of label/count
                # tuples or dicts). bucketed_metrics is already the
                # right dict shape.
                adapter_ctx["buckets"] = bucketed_metrics
                adapter_ctx["chart_label"] = ctx.ctx_region.title
            elif display_upper == "RADAR":
                # Phase 4 region migration (v0.67.70): radar consumes
                # `axes` (label, value) pairs. The legacy template iterated
                # `bucketed_metrics` and read each entry's `label` + `value`
                # — same source, simpler shape here.
                radar_axes: list[tuple[str, float]] = []
                for entry in bucketed_metrics or []:
                    if not isinstance(entry, dict):
                        continue
                    label = str(entry.get("label", "") or "")
                    raw_val = entry.get("value", 0) or 0
                    try:
                        val = float(raw_val)
                    except (TypeError, ValueError):
                        val = 0.0
                    if label:
                        radar_axes.append((label, val))
                adapter_ctx["axes"] = radar_axes
                adapter_ctx["chart_label"] = ctx.ctx_region.title
            elif display_upper in ("LINE_CHART", "AREA_CHART"):
                # TimeSeries variants: both read `points` from the
                # same upstream `bucketed_metrics`. Reference lines /
                # bands / overlay series flow through too.
                adapter_ctx["points"] = bucketed_metrics
                adapter_ctx["chart_label"] = ctx.ctx_region.title
                adapter_ctx["reference_lines"] = getattr(ctx.ctx_region, "reference_lines", [])
                adapter_ctx["reference_bands"] = getattr(ctx.ctx_region, "reference_bands", [])
                adapter_ctx["overlay_series_data"] = overlay_series_data
            elif display_upper == "BAR_TRACK":
                # Pre-computed per-row {label, value, fill_pct,
                # formatted_value} from `_compute_bar_track_rows`.
                adapter_ctx["bar_track_rows"] = bar_track_rows
                adapter_ctx["bar_track_max"] = bar_track_max
            elif display_upper == "BULLET":
                # Pre-computed per-row {label, actual, target} from
                # `_compute_bullet_rows`.
                adapter_ctx["bullet_rows"] = bullet_rows
                adapter_ctx["bullet_max_value"] = bullet_max_value
            elif display_upper == "BOX_PLOT":
                # Per-group quartile stats from `_compute_box_plot_stats`.
                adapter_ctx["box_plot_stats"] = box_plot_stats
            elif display_upper == "ACTIVITY_FEED":
                # Items carry actor/description/created_at — the adapter
                # reads them directly off the row dicts.
                adapter_ctx["items"] = items
            elif display_upper == "LIST":
                # Phase 4 region migration (v0.67.51): foundational
                # list-view. Read all the chrome contract (filter bar,
                # date range, CSV, sort headers) plus row data.
                adapter_ctx["items"] = items
                adapter_ctx["columns"] = columns
                adapter_ctx["total"] = total
                adapter_ctx["endpoint"] = ctx.ctx_region.endpoint
                adapter_ctx["region_name"] = getattr(ctx.ctx_region, "name", "")
                adapter_ctx["filter_columns"] = filter_columns
                adapter_ctx["active_filters"] = active_filters
                adapter_ctx["date_range"] = getattr(ctx.ctx_region, "date_range", False)
                adapter_ctx["date_field"] = getattr(ctx.ctx_region, "date_field", "")
                adapter_ctx["date_from"] = request.query_params.get("date_from", "")
                adapter_ctx["date_to"] = request.query_params.get("date_to", "")
                adapter_ctx["csv_export"] = getattr(ctx.ctx_region, "csv_export", False)
                adapter_ctx["sort_field"] = sort or ""
                adapter_ctx["sort_dir"] = dir
                adapter_ctx["empty_message"] = (
                    ctx.surface_empty_message or ctx.ctx_region.empty_message
                )
            elif display_upper == "CONFIRM_ACTION_PANEL":
                # ConfirmGate full state machine — IR-level fields plus
                # the request-time state value.
                adapter_ctx["state_value"] = confirm_state_value
                adapter_ctx["confirmations"] = getattr(ctx.ctx_region, "confirmations", [])
                adapter_ctx["primary_action_url"] = getattr(
                    ctx.ctx_region, "primary_action_url", ""
                )
                adapter_ctx["secondary_action_url"] = getattr(
                    ctx.ctx_region, "secondary_action_url", ""
                )
                adapter_ctx["revoke_url"] = getattr(ctx.ctx_region, "revoke_url", "")
                adapter_ctx["audit_enabled"] = getattr(ctx.ctx_region, "audit_enabled", False)
            elif display_upper == "ENTITY_CARD":
                _card_cfg = getattr(ir_region, "entity_card_config", None)
                if _card_cfg is not None:
                    # #1017 (v0.67.18) — per-section fan-out for modes
                    # that pull from related entities (mini_bars, stamps,
                    # thread_summary). Sections without their own
                    # `source:` (halo / flags / quick_actions) skip the
                    # fan-out and read from the scoped record directly.
                    _rows_per_section = await _fetch_entity_card_section_rows(
                        config=_card_cfg,
                        ctx=ctx,
                        request=request,
                        auth_context=_auth_ctx_for_filters,
                        user_id=_current_user_id,
                    )
                    adapter_ctx["entity_card_sections"] = _build_entity_card_sections(
                        items=items,
                        config=_card_cfg,
                        rows_per_section=_rows_per_section,
                    )
                    if items:
                        # Heading from the resolved single record's
                        # `name` / `title` / `message` field — first
                        # row scoped via the `scope_param` URL parameter
                        # which the upstream filter machinery already
                        # applied. Empty when no record matched.
                        record = items[0]
                        adapter_ctx["entity_card_record_label"] = str(
                            record.get("name") or record.get("title") or record.get("message") or ""
                        )
            try:
                surface = WorkspaceRegionAdapter().build(ir_region, adapter_ctx)
                inner = getattr(getattr(surface, "body", None), "body", None)
                fragment_to_render = inner if inner is not None else surface
                typed_primitive_html = FragmentRenderer().render(fragment_to_render)
            except Exception as exc:  # noqa: BLE001 — surface to operator log
                logger.error(
                    "typed-primitive render failed for %s region %s: %s",
                    display_upper,
                    getattr(ctx.ctx_region, "name", "?"),
                    exc,
                )
                typed_primitive_html = (
                    '<p class="dz-empty-dense" role="status">'
                    "Typed primitive render failed; check server logs."
                    "</p>"
                )

    # Phase 4 (v0.67.70): every region display now resolves to
    # `_typed_primitive.html`. The Jinja fallback path is gone — the
    # typed substrate is the only render path.
    import html as _html_mod

    region_name_attr = _html_mod.escape(ctx.ctx_region.name, quote=True)
    html = (
        f'<div data-dz-region data-dz-region-name="{region_name_attr}" '
        f'id="region-{region_name_attr}">'
        f"{typed_primitive_html or ''}"
        f"</div>"
    )
    return HTMLResponse(content=html)
