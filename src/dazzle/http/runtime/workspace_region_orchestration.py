"""Phase 4-5 of the workspace region handler — compute orchestration.

Extracted from ``_workspace_region_handler`` in #1057 cut 15 (v0.67.114).
Runs after Phase 2 (item fetch) and before Phase 6 (render). Threads
the fetched rows through every per-display compute and returns a
fully-populated ``RegionRenderInputs`` dataclass ready for
``render_region_html``.

Pipeline:

- **Phase 4** (aggregate setup, cross-display): scope-gated aggregate
  metrics, bucketed aggregates (single-dim charts), kanban columns,
  filter columns, attention signals.
- **Phase 5** (per-display computes): histograms, box plots, overlay
  series, bullet rows, bar tracks, action grids, pipeline stages,
  profile cards, confirm action state, pivot buckets, queue
  transitions, heatmap matrices, progress stages, tree items.

Each step is a call to an already-extracted helper — this module
is the orchestrator that wires them in the right order.
"""

import logging
from typing import Any

from dazzle.core.ir import BucketRef as _BucketRef
from dazzle.core.ir.workspaces import ComparisonOutlierSpec
from dazzle.http.runtime.workspace_aggregation import (
    _compute_aggregate_metrics,
    _compute_box_plot_stats,
    _compute_bucketed_aggregates,
    _compute_histogram_bins,
    _compute_pivot_buckets,
)
from dazzle.http.runtime.workspace_context import WorkspaceRegionContext
from dazzle.http.runtime.workspace_region_computes import (
    apply_attention_signals,
    build_comparison_inputs,
    compute_action_grid,
    compute_bar_track,
    compute_bullet,
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
from dazzle.http.runtime.workspace_region_fetch import RegionItemsResult
from dazzle.http.runtime.workspace_region_prelude import RequestUserContext
from dazzle.http.runtime.workspace_region_render import RegionRenderInputs

logger = logging.getLogger(__name__)

# Display-mode groupings used by phase-4 gates.
_GROUPED_MODES: frozenset[str] = frozenset({"KANBAN", "BAR_CHART", "FUNNEL_CHART"})
_SINGLE_DIM_CHART_MODES: frozenset[str] = frozenset(
    {"BAR_CHART", "LINE_CHART", "SPARKLINE", "RADAR", "BAR_TRACK", "COMPARISON"}
)
_MULTI_DIM_MODES: frozenset[str] = frozenset({"PIVOT_TABLE", "AREA_CHART"})


async def compute_region_render_inputs(
    request: Any,
    ctx: WorkspaceRegionContext,
    user_ctx: RequestUserContext,
    fetched: RegionItemsResult,
    columns: list[dict[str, Any]],
) -> RegionRenderInputs:
    """Run phases 4 and 5: build every shape Phase 6 reads.

    Returns a fully-populated ``RegionRenderInputs``. Defaults
    (empty lists, ``0`` totals, etc.) carry through for displays
    that don't need a given shape — phase 6's adapter dispatch
    handles the conditional reads.
    """

    items = fetched.items
    total = fetched.total
    scope_only_filters = fetched.scope_only_filters
    scope_denied = fetched.scope_denied
    ctx_region = ctx.ctx_region
    display = ctx_region.display

    # #1305: aggregate / GROUP BY paths re-scope by the workspace
    # context_selector. `scope_only_filters` deliberately excludes the region
    # `filter:` (the #887 tenant-bounding contract), but the `current_context`
    # slice of that filter IS a context boundary — it must reach the aggregate
    # query so charts/metrics narrow on selector change, just like the list
    # path does. `context_filters` is keyed on the source entity's FK columns,
    # so it composes with `scope_only_filters` for every `ctx.source`-based
    # aggregate below. (Overlay series may target a different source and is
    # handled separately.)
    agg_scope_filters: dict[str, Any] = {
        **(scope_only_filters or {}),
        **(fetched.context_filters or {}),
    }

    # ─── Phase 4: cross-display aggregates ─────────────────────────────

    # Scope-gated aggregate metrics (#887): when scope is denied,
    # unfiltered aggregates would leak counts/sums/averages across
    # tenants — suppress.
    metrics: list[dict[str, Any]] = []
    if ctx_region.aggregates and not scope_denied:
        metrics = await _compute_aggregate_metrics(
            ctx_region.aggregates,
            ctx.repositories,
            total,
            items,
            scope_filters=agg_scope_filters,  # #1305: scope + context selector
            delta=ctx_region.delta,  # #884
            source_entity=ctx.source,  # #888 Phase 1
            tones=getattr(ctx_region, "tones", None),  # v0.61.65
        )

    # Filter column metadata + active filters from the request.
    filter_columns, active_filters = compute_filter_columns_and_active(
        columns, request.query_params
    )

    # Annotate items with the highest-severity matching attention signal.
    apply_attention_signals(items, ctx.attention_signals, user_ctx.filter_context)

    # group_by: read from ir_region — IR preserves the typed form
    # (str | BucketRef | None). ctx_region (pydantic, template-facing)
    # flattens it to a string for Jinja.
    group_by = getattr(ctx.ir_region, "group_by", None) if ctx.ir_region else ctx_region.group_by
    gb_is_bucket = isinstance(group_by, _BucketRef)

    # Kanban / grouped bucket list (enum / state-machine values).
    kanban_columns: list[str] = []
    if group_by and not gb_is_bucket and display in _GROUPED_MODES and ctx.entity_spec:
        kanban_columns = compute_kanban_columns(ctx.entity_spec, group_by)

    # Single-dim bucketed aggregates (bar_chart / line_chart / sparkline /
    # radar / bar_track). #887: scope-gated.
    bucketed_metrics: list[dict[str, Any]] = []
    if (
        display in _SINGLE_DIM_CHART_MODES
        and group_by
        and ctx_region.aggregates
        and not scope_denied
    ):
        bucketed_metrics = await _compute_bucketed_aggregates(
            ctx_region.aggregates,
            ctx.repositories,
            group_by,
            items,
            bucket_values=kanban_columns or None,
            scope_filters=agg_scope_filters,  # #1305: scope + context selector
            source_entity=ctx.source,
        )

    # ─── Phase 5: per-display computes ─────────────────────────────────

    # Histogram (#882): bin a continuous numeric column from items.
    histogram_bins: list[dict[str, Any]] = []
    if display == "HISTOGRAM":
        value_field = (getattr(ctx_region, "heatmap_value", "") or "").strip()
        bin_count = getattr(ctx.ir_region, "bin_count", None)
        if value_field:
            histogram_bins = _compute_histogram_bins(items, value_field, bin_count)

    # Box plot (#881): per-group quartile/whisker stats from items.
    box_plot_stats: list[dict[str, Any]] = []
    if display == "BOX_PLOT":
        value_field = (getattr(ctx_region, "heatmap_value", "") or "").strip()
        bp_group_by = group_by if isinstance(group_by, str) else None
        show_outliers = bool(getattr(ctx.ir_region, "show_outliers", True))
        if value_field:
            box_plot_stats = _compute_box_plot_stats(items, value_field, bp_group_by, show_outliers)

    # Overlay series (#883): for line/area chart regions, fire one extra
    # bucketed-aggregate query per overlay. #887: same scope gate.
    overlay_series_data: list[dict[str, Any]] = []
    ir_overlays = (getattr(ctx.ir_region, "overlay_series", None) if ctx.ir_region else None) or []
    if ir_overlays and display in {"LINE_CHART", "AREA_CHART"} and group_by and not scope_denied:
        for overlay in ir_overlays:
            ovl_source = overlay.source or ctx.source
            # #1305: the context slice is keyed on `ctx.source`'s FK columns,
            # so it only composes with an overlay that shares that source.
            # A different-source overlay keeps the pure scope slice.
            ovl_scope_filters = (
                agg_scope_filters if ovl_source == ctx.source else scope_only_filters
            )
            try:
                # Per ADR-0024 _compute_bucketed_aggregates consumes typed
                # AggregateRef directly — no stringification.
                overlay_aggregates = {overlay.label: overlay.aggregate}
                overlay_buckets = await _compute_bucketed_aggregates(
                    overlay_aggregates,
                    ctx.repositories,
                    group_by,
                    items=[],  # overlay computes its own buckets via fast path
                    bucket_values=kanban_columns or None,
                    scope_filters=ovl_scope_filters,
                    source_entity=ovl_source,
                )
                overlay_series_data.append({"label": overlay.label, "buckets": overlay_buckets})
            except Exception:
                logger.warning(
                    "Overlay series %r failed — skipping",
                    overlay.label,
                    exc_info=True,
                )

    # Bullet chart (#880): per-row {label, actual, target}.
    if display == "BULLET":
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

    # Bar track (#893): rows + auto-max from bucketed_metrics.
    if display == "BAR_TRACK" and bucketed_metrics:
        bar_track_rows, bar_track_max = compute_bar_track(
            bucketed_metrics,
            explicit_max=ctx_region.track_max,
            format_spec=ctx_region.track_format or "",
            region_name=ctx_region.name,
        )
    else:
        bar_track_rows = []
        bar_track_max = 0.0

    # Comparison (#1470): ranked league from group buckets or scoped entity rows.
    if display == "COMPARISON":
        comparison_rows, comparison_max = build_comparison_inputs(
            group_by=group_by,
            bucketed_metrics=bucketed_metrics,
            items=items,
            columns=columns,
            rank_by=getattr(ctx.ir_region, "rank_by", None) or "",
            order=getattr(ctx.ir_region, "order", "desc"),
            outlier_spec=getattr(ctx.ir_region, "outlier", None) or ComparisonOutlierSpec(),
        )
    else:
        comparison_rows = []
        comparison_max = 0.0

    # Action grid (#891): async per-card count fan-out.
    action_card_data: list[dict[str, Any]] = []
    if display == "ACTION_GRID":
        action_card_data = await compute_action_grid(
            ctx_region.action_cards or [],
            ctx.repositories,
            ctx.source,
            agg_scope_filters,  # #1305: scope + context selector
            scope_denied,
        )

    # Pipeline steps (#890): async per-stage aggregate.
    pipeline_stage_data: list[dict[str, Any]] = []
    if display == "PIPELINE_STEPS":
        pipeline_stage_data = await compute_pipeline_steps(
            ctx_region.pipeline_stages or [],
            ctx.repositories,
            ctx.source,
            agg_scope_filters,  # #1305: scope + context selector
            scope_denied,
        )

    # Profile card (#892): single-record identity panel.
    profile_card_data: dict[str, Any] = {}
    if display == "PROFILE_CARD":
        profile_card_data = compute_profile_card(items, ctx_region)

    # Confirm action panel (v0.61.72): state_field read.
    confirm_state_value: str = ""
    if display == "CONFIRM_ACTION_PANEL":
        confirm_state_value = compute_confirm_action_state(
            items, getattr(ctx_region, "state_field", None)
        )

    # Multi-dim pivot (cycle 25, cycle 28). #887: scope-gated.
    pivot_buckets: list[dict[str, Any]] = []
    pivot_dim_specs: list[dict[str, Any]] = []
    ir_group_by_dims = getattr(ctx.ir_region, "group_by_dims", None) if ctx.ir_region else None
    if (
        display in _MULTI_DIM_MODES
        and ir_group_by_dims
        and ctx_region.aggregates
        and not scope_denied
    ):
        pivot_buckets, pivot_dim_specs = await _compute_pivot_buckets(
            ctx_region.aggregates,
            ctx.repositories,
            ir_group_by_dims,
            source_entity=ctx.source,
            source_entity_spec=ctx.entity_spec,
            scope_filters=agg_scope_filters,  # #1305: scope + context selector
        )

    # Queue: state-machine transitions + API endpoint.
    if display == "QUEUE" and ctx.entity_spec:
        queue_transitions, queue_status_field, queue_api_endpoint = compute_queue(
            ctx.entity_spec, ctx.source
        )
    else:
        queue_transitions = []
        queue_status_field = ""
        queue_api_endpoint = ""

    # Multi-source tabbed regions.
    source_tabs = ctx_region.source_tabs or []

    # Heatmap (v0.44.0): pivot items into matrix. Thresholds may come
    # from a ParamRef in IR (#572, #575); fall back to ctx_region defaults.
    heatmap_matrix: list[dict[str, Any]] = []
    heatmap_col_values: list[str] = []
    ir_thresholds = getattr(ctx.ir_region, "heatmap_thresholds", None)
    if hasattr(ir_thresholds, "key"):  # ParamRef
        from dazzle.http.runtime.param_store import resolve_value

        resolved = resolve_value(
            ir_thresholds,
            getattr(ctx, "param_resolver", None),
            tenant_id=getattr(ctx, "tenant_id", None),
        )
        heatmap_thresholds: list[float] = list(
            resolved or getattr(ctx_region, "heatmap_thresholds", None) or []
        )
    else:
        heatmap_thresholds = list(getattr(ctx_region, "heatmap_thresholds", None) or [])
    if display == "HEATMAP" and items:
        heatmap_matrix, heatmap_col_values = compute_heatmap(
            items,
            rows_field=getattr(ctx_region, "heatmap_rows", "") or "",
            cols_field=getattr(ctx_region, "heatmap_columns", "") or "",
            value_field=getattr(ctx_region, "heatmap_value", "") or "",
        )

    # Progress (v0.44.0): stage counts + completion pct.
    progress_stages_list: list[str] = list(getattr(ctx_region, "progress_stages", None) or [])
    progress_complete_at: str = getattr(ctx_region, "progress_complete_at", "") or ""
    if display == "PROGRESS" and items and progress_stages_list:
        prog = compute_progress(
            items, progress_stages_list, progress_complete_at, group_by or "status"
        )
        progress_stage_counts: list[dict[str, Any]] = prog["stage_counts"]
        progress_total: int = prog["total"]
        progress_complete_count: int = prog["complete_count"]
        progress_complete_pct: float = prog["complete_pct"]
    else:
        progress_stage_counts = []
        progress_total = 0
        progress_complete_count = 0
        progress_complete_pct = 0.0

    # Tree (#565): nested hierarchy via group_by as parent ref.
    tree_items: list[dict[str, Any]] = []
    if display == "TREE" and group_by and items:
        tree_items = compute_tree(items, group_by)

    # #1144 Gap 1 phase 2: cohort_strip primary_aggregate lens runtime.
    # When the active lens carries `primary_aggregate:`, fire per-member
    # aggregate queries (N+1 fan-out; phase 3 will batch via GROUP BY).
    # No-via case only — `via:` is phase 3.
    cohort_aggregate_values: dict[str, Any] = {}
    if display == "COHORT_STRIP" and items and not scope_denied:
        cohort_cfg = getattr(ctx.ir_region, "cohort_strip_config", None)
        if cohort_cfg is not None:
            from dazzle.http.runtime.workspace_region_computes import (
                compute_cohort_aggregate_primary,
            )

            active_lens_id = (
                request.query_params.get("lens")
                or getattr(cohort_cfg, "default_lens", "")
                or (getattr(cohort_cfg.lenses[0], "id", "") if cohort_cfg.lenses else "")
            )
            active_lens = next(
                (
                    lens
                    for lens in (cohort_cfg.lenses or [])
                    if str(getattr(lens, "id", "")) == active_lens_id
                ),
                cohort_cfg.lenses[0] if cohort_cfg.lenses else None,
            )
            if active_lens is not None and getattr(active_lens, "primary_aggregate", None):
                cohort_aggregate_values = await compute_cohort_aggregate_primary(
                    items=items,
                    lens=active_lens,
                    source_entity=ctx.source,
                    repositories=ctx.repositories,
                    scope_only_filters=agg_scope_filters,  # #1305: scope + context selector
                )

    return RegionRenderInputs(
        items=items,
        columns=columns,
        total=total,
        metrics=metrics,
        bucketed_metrics=bucketed_metrics,
        kanban_columns=kanban_columns,
        heatmap_matrix=heatmap_matrix,
        heatmap_col_values=heatmap_col_values,
        heatmap_thresholds=heatmap_thresholds,
        histogram_bins=histogram_bins,
        box_plot_stats=box_plot_stats,
        pivot_buckets=pivot_buckets,
        pivot_dim_specs=pivot_dim_specs,
        tree_items=tree_items,
        source_tabs=source_tabs,
        bar_track_rows=bar_track_rows,
        bar_track_max=bar_track_max,
        comparison_rows=comparison_rows,
        comparison_max=comparison_max,
        bullet_rows=bullet_rows,
        bullet_max_value=bullet_max_value,
        progress_stage_counts=progress_stage_counts,
        progress_total=progress_total,
        progress_complete_count=progress_complete_count,
        progress_complete_pct=progress_complete_pct,
        action_card_data=action_card_data,
        pipeline_stage_data=pipeline_stage_data,
        profile_card_data=profile_card_data,
        confirm_state_value=confirm_state_value,
        queue_transitions=queue_transitions,
        queue_status_field=queue_status_field,
        queue_api_endpoint=queue_api_endpoint,
        overlay_series_data=overlay_series_data,
        group_by=group_by,
        filter_columns=filter_columns,
        active_filters=active_filters,
        cohort_aggregate_values=cohort_aggregate_values,
    )
