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
- **Phase 5** (per-display computes): overlay series, comparison
  rows, insight narrative, pipeline stages, confirm action state,
  pivot buckets, queue transitions, kanban rearrange, tabbed slices,
  cohort aggregates.

Each step is a call to an already-extracted helper — this module
is the orchestrator that wires them in the right order.
"""

import logging
from typing import Any

from dazzle.core.access import AccessOperationKind
from dazzle.core.ir import BucketRef as _BucketRef
from dazzle.core.ir.workspaces import ComparisonOutlierSpec
from dazzle.http.runtime.handlers.list_handlers import (
    _principal_can_op,
)
from dazzle.http.runtime.insight_store import get_stored_insight
from dazzle.http.runtime.workspace_aggregation import (
    _compute_aggregate_metrics,
    _compute_bucketed_aggregates,
    _compute_pivot_buckets,
)
from dazzle.http.runtime.workspace_context import WorkspaceRegionContext
from dazzle.http.runtime.workspace_region_computes import (
    apply_attention_signals,
    build_comparison_inputs,
    build_insight_inputs,
    build_outlier_flags,
    build_rag_tones,
    comparison_top_n,
    compute_confirm_action_state,
    compute_filter_columns_and_active,
    compute_kanban_columns,
    compute_kanban_rearrange,
    compute_pipeline_steps,
    compute_queue,
    compute_tabbed_slices,
)
from dazzle.http.runtime.workspace_region_fetch import RegionItemsResult
from dazzle.http.runtime.workspace_region_prelude import RequestUserContext
from dazzle.http.runtime.workspace_region_render import RegionRenderInputs
from dazzle.page.runtime.action_urls import fill_row_id_in_url
from dazzle.render.fragment.insight import clerk_insight_group_noun
from dazzle.render.fragment.renderer._render_interactive import leftover_honest_catalog_id

logger = logging.getLogger(__name__)


def gate_queue_transitions_for_principal(
    transitions: list[dict[str, str]],
    cedar_access_spec: Any,
    auth_ctx: Any,
    *,
    entity_name: str = "",
) -> list[dict[str, str]]:
    """Clear workspace QUEUE transition chrome when UPDATE is denied.

    Queue rows paint SM action buttons (Approve / Reject / …) from
    ``compute_queue``. List rows and detail toolbars already omit
    transition chips when permit denies UPDATE (cycles 1390–1392); workspace
    queues still painted the full primary pair for read-only personas until
    the PUT 403'd. Reuses the list-handler principal gate so pure role rules
    suppress chrome and field-conditioned rules leave buttons (write path
    still enforces).
    """
    if not transitions:
        return transitions
    if _principal_can_op(
        cedar_access_spec,
        AccessOperationKind.UPDATE,
        auth_ctx,
        entity_name=entity_name,
    ):
        return transitions
    return []


def gate_kanban_rearrange_for_principal(
    rearrange: str,
    cedar_access_spec: Any,
    auth_ctx: Any,
    *,
    entity_name: str = "",
) -> str:
    """Clear kanban rearrange capability when UPDATE is denied (Linear R4).

    Same chrome class as :func:`gate_queue_transitions_for_principal`: pure
    role rules suppress drag/drop attrs so read-only personas never see a
    grab cursor; field-conditioned rules leave rearrange on (write path
    still enforces). Returns ``""`` or ``"status"``.
    """
    if rearrange != "status":
        return ""
    if _principal_can_op(
        cedar_access_spec,
        AccessOperationKind.UPDATE,
        auth_ctx,
        entity_name=entity_name,
    ):
        return "status"
    return ""


def gate_confirm_action_urls_for_principal(
    *,
    primary_url: str,
    secondary_url: str,
    revoke_url: str,
    cedar_access_spec: Any,
    auth_ctx: Any,
    entity_name: str = "",
) -> tuple[str, str, str]:
    """Clear confirm_action_panel commit/revoke chrome when UPDATE is denied.

    Compile-time stamps ``primary_action_url`` / ``secondary_action_url`` /
    ``revoke_url`` from surface names. Queue transitions already gate on
    UPDATE (cycle 1396); the consent panel still painted Enable / Save draft /
    Revoke for read-only personas until the mutation surface 403'd
    (cycle 1397 — same class of workspace chrome leak).
    """
    if not (primary_url or secondary_url or revoke_url):
        return primary_url, secondary_url, revoke_url
    if _principal_can_op(
        cedar_access_spec,
        AccessOperationKind.UPDATE,
        auth_ctx,
        entity_name=entity_name,
    ):
        return primary_url, secondary_url, revoke_url
    return "", "", ""


def _read_stored_insight(region_name: str) -> Any:
    """Read the stored narrative for a region; a provider error → None (fallback)."""
    try:
        return get_stored_insight(region_name)
    except Exception:
        logger.warning(
            "insight_summary stored-narrative provider failed for %r", region_name, exc_info=True
        )
        return None


# Display-mode groupings used by phase-4 gates.
_GROUPED_MODES: frozenset[str] = frozenset({"KANBAN", "BAR_CHART"})
_SINGLE_DIM_CHART_MODES: frozenset[str] = frozenset(
    {
        "BAR_CHART",
        "LINE_CHART",
        "COMPARISON",
        "INSIGHT_SUMMARY",
    }
)
_MULTI_DIM_MODES: frozenset[str] = frozenset({"PIVOT_TABLE"})


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

    # #1773: aggregates over the region source count the rows the region
    # shows — scope AND the full compiled region `filter:` (literals,
    # current_user terms and the #1305 `current_context` selector). Scope is
    # never replaced (#887): it wins on key collision, and default-deny still
    # gates every aggregate below. `region_filters` names the source entity's
    # columns, so the metric / bucketed helpers take it separately and apply
    # it only to aggregates over `ctx.source`; the same-source-only consumers
    # (pivot, pipeline_steps) take the composed dict.
    region_filters = fetched.region_filters
    agg_scope_filters: dict[str, Any] = {
        **(region_filters or {}),
        **(scope_only_filters or {}),
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
            scope_filters=scope_only_filters,
            delta=ctx_region.delta,  # #884
            source_entity=ctx.source,  # #888 Phase 1
            tones=getattr(ctx_region, "tones", None),  # v0.61.65
            region_filters=region_filters,  # #1773
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

    # Single-dim bucketed aggregates (bar_chart / line_chart /
    # comparison / insight_summary). #887: scope-gated.
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
            scope_filters=scope_only_filters,
            source_entity=ctx.source,
            top_n=comparison_top_n(ctx.ir_region, ctx_region.aggregates, display),  # #1814
            region_filters=region_filters,  # #1773
        )

    # ─── Phase 5: per-display computes ─────────────────────────────────

    # Overlay series (#883): for line chart regions, fire one extra
    # bucketed-aggregate query per overlay. #887: same scope gate.
    overlay_series_data: list[dict[str, Any]] = []
    ir_overlays = (getattr(ctx.ir_region, "overlay_series", None) if ctx.ir_region else None) or []
    if ir_overlays and display == "LINE_CHART" and group_by and not scope_denied:
        for overlay in ir_overlays:
            ovl_source = overlay.source or ctx.source
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
                    scope_filters=scope_only_filters,
                    source_entity=ovl_source,
                    # #1773: region filter names `ctx.source` columns — only a
                    # same-source overlay is narrowed by it.
                    region_filters=region_filters if ovl_source == ctx.source else None,
                )
                overlay_series_data.append({"label": overlay.label, "buckets": overlay_buckets})
            except Exception:
                logger.warning(
                    "Overlay series %r failed — skipping",
                    overlay.label,
                    exc_info=True,
                )

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
            limit=ctx_region.limit,  # #1814
        )
    else:
        comparison_rows = []
        comparison_max = 0.0

    # Insight summary (#1470): deterministic narrative over the grouped aggregate.
    if display == "INSIGHT_SUMMARY" and group_by and bucketed_metrics:
        _gb = group_by if isinstance(group_by, str) else str(group_by)
        group_label = clerk_insight_group_noun(_gb)
        scope_desc = f"across all {group_label}"
        if getattr(ctx.ir_region, "filter", None) is not None:
            scope_desc += " (filtered)"
        insight_narrative = build_insight_inputs(
            bucketed_metrics,
            region=ctx.ir_region,
            group_label=group_label,
            scope_desc=scope_desc,
            outlier_spec=getattr(ctx.ir_region, "outlier", None) or ComparisonOutlierSpec(),
        )
        # #1470 Slice 2a: a pre-computed narrative overlay (or None → deterministic).
        stored_insight = _read_stored_insight(getattr(ctx.ir_region, "name", "") or "")
    else:
        insight_narrative = None
        stored_insight = None

    # Outlier decorator (#1470): per-row flags for one list column.
    outlier_on = getattr(ctx.ir_region, "outlier_on", None) or ""
    if display == "LIST" and outlier_on and not scope_denied:
        outlier_flags = build_outlier_flags(
            items,
            column=outlier_on,
            spec=getattr(ctx.ir_region, "outlier", None) or ComparisonOutlierSpec(),
        )
    else:
        outlier_flags = []
        outlier_on = ""

    # RAG decorator (#1470): per-row band tones for one list column.
    rag_on = getattr(ctx.ir_region, "rag_on", None) or ""
    if display == "LIST" and rag_on and not scope_denied:
        rag_tones = build_rag_tones(
            items, column=rag_on, bands=getattr(ctx.ir_region, "tone_bands", None) or []
        )
    else:
        rag_tones = []
        rag_on = ""

    # Pipeline steps (#890): async per-stage aggregate.
    pipeline_stage_data: list[dict[str, Any]] = []
    if display == "PIPELINE_STEPS":
        pipeline_stage_data = await compute_pipeline_steps(
            ctx_region.pipeline_stages or [],
            ctx.repositories,
            ctx.source,
            agg_scope_filters,  # #1773: scope + region filter
            scope_denied,
        )

    # Confirm action panel (v0.61.72): state_field read + UPDATE chrome gate.
    # primary/secondary/revoke are mutation affordances — clear when denied
    # (parity with queue transitions, cycle 1397). Cycle 1402: fill ``{id}``
    # from the fetched source row before gating so EDIT-path CTAs land on a
    # real form instead of a literal ``{id}`` path segment.
    confirm_state_value: str = ""
    confirm_primary_action_url = ""
    confirm_secondary_action_url = ""
    confirm_revoke_url = ""
    if display == "CONFIRM_ACTION_PANEL":
        confirm_state_value = compute_confirm_action_state(
            items, getattr(ctx_region, "state_field", None)
        )
        row_id = ""
        if items:
            first = items[0] if isinstance(items[0], dict) else {}
            row_id = str(first.get("id") or "")
        (
            confirm_primary_action_url,
            confirm_secondary_action_url,
            confirm_revoke_url,
        ) = gate_confirm_action_urls_for_principal(
            primary_url=fill_row_id_in_url(
                str(getattr(ctx_region, "primary_action_url", "") or ""), row_id
            ),
            secondary_url=fill_row_id_in_url(
                str(getattr(ctx_region, "secondary_action_url", "") or ""), row_id
            ),
            revoke_url=fill_row_id_in_url(str(getattr(ctx_region, "revoke_url", "") or ""), row_id),
            cedar_access_spec=ctx.cedar_access_spec,
            auth_ctx=user_ctx.auth_ctx_for_filters,
            entity_name=ctx.source or "",
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
            scope_filters=agg_scope_filters,  # #1773: same-source only — scope + region filter
        )

    # Queue: state-machine transitions + API endpoint.
    # SM transition buttons are UPDATE chrome — gate like list row chips /
    # detail toolbar (cycles 1390–1392). Compile/compute always stamps the
    # full primary pair; read-only personas still painted Approve|Reject
    # until the PUT 403'd.
    if display == "QUEUE" and ctx.entity_spec:
        queue_transitions, queue_status_field, queue_api_endpoint = compute_queue(
            ctx.entity_spec, ctx.source
        )
        region_ir = ctx.ir_region if ctx.ir_region is not None else ctx_region
        if getattr(region_ir, "transitions", None) == "none":
            # #1663: inspect-before-stamp — cards drill; stamp lives on
            # the record. Role-only pile PUTs are suppressed too.
            queue_transitions = []
        else:
            queue_transitions = gate_queue_transitions_for_principal(
                queue_transitions,
                ctx.cedar_access_spec,
                user_ctx.auth_ctx_for_filters,
                entity_name=ctx.source or "",
            )
    else:
        queue_transitions = []
        queue_status_field = ""
        queue_api_endpoint = ""

    # Kanban rearrange (Linear-class status move) — capability from SM/enum,
    # chrome gated on UPDATE like queue transitions (R4).
    kanban_rearrange = ""
    kanban_status_field = ""
    kanban_api_endpoint = ""
    kanban_allowed_by_id: dict[str, tuple[str, ...]] = {}
    kanban_rank_field = ""
    if display == "KANBAN" and ctx.entity_spec and group_by and not gb_is_bucket:
        (
            kanban_rearrange,
            kanban_status_field,
            kanban_api_endpoint,
            kanban_allowed_by_id,
            kanban_rank_field,
        ) = compute_kanban_rearrange(
            ctx.entity_spec,
            str(group_by),
            ctx.source or "",
            items if isinstance(items, list) else [],
        )
        kanban_rearrange = gate_kanban_rearrange_for_principal(
            kanban_rearrange,
            ctx.cedar_access_spec,
            user_ctx.auth_ctx_for_filters,
            entity_name=ctx.source or "",
        )
        if kanban_rearrange != "status":
            kanban_status_field = ""
            kanban_api_endpoint = ""
            kanban_allowed_by_id = {}
            kanban_rank_field = ""

    # Multi-source tabbed regions.
    source_tabs = ctx_region.source_tabs or []

    # Tabbed list (oral #164): scalar group_by without multi-source tabs.
    tabbed_slices: list[dict[str, Any]] = []
    tab_group = group_by if isinstance(group_by, str) else ""
    if display == "TABBED_LIST" and tab_group and items and not source_tabs:
        tabbed_slices = compute_tabbed_slices(items, tab_group, columns)

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

            known_lenses = [
                str(getattr(lens, "id", "") or "") for lens in (cohort_cfg.lenses or [])
            ]
            active_lens_id = leftover_honest_catalog_id(
                request.query_params.get("lens") or "",
                known_lenses,
                str(getattr(cohort_cfg, "default_lens", "") or ""),
            )
            active_lens = next(
                (
                    lens
                    for lens in (cohort_cfg.lenses or [])
                    if str(getattr(lens, "id", "")) == active_lens_id
                ),
                None,
            )
            if active_lens is not None and getattr(active_lens, "primary_aggregate", None):
                cohort_aggregate_values = await compute_cohort_aggregate_primary(
                    items=items,
                    lens=active_lens,
                    source_entity=ctx.source,
                    repositories=ctx.repositories,
                    # Members are already region-filtered items; the region
                    # filter's source columns don't exist on the aggregated
                    # entity, so only scope composes here (#1773).
                    scope_only_filters=scope_only_filters,
                )

    return RegionRenderInputs(
        items=items,
        columns=columns,
        total=total,
        page=fetched.page,  # #1792
        page_size=fetched.page_size,  # #1792
        metrics=metrics,
        bucketed_metrics=bucketed_metrics,
        kanban_columns=kanban_columns,
        pivot_buckets=pivot_buckets,
        pivot_dim_specs=pivot_dim_specs,
        tabbed_slices=tabbed_slices,
        source_tabs=source_tabs,
        comparison_rows=comparison_rows,
        comparison_max=comparison_max,
        insight_narrative=insight_narrative,
        stored_insight=stored_insight,
        outlier_flags=outlier_flags,
        outlier_on=outlier_on,
        rag_tones=rag_tones,
        rag_on=rag_on,
        pipeline_stage_data=pipeline_stage_data,
        confirm_state_value=confirm_state_value,
        confirm_primary_action_url=confirm_primary_action_url,
        confirm_secondary_action_url=confirm_secondary_action_url,
        confirm_revoke_url=confirm_revoke_url,
        queue_transitions=queue_transitions,
        queue_status_field=queue_status_field,
        queue_api_endpoint=queue_api_endpoint,
        kanban_rearrange=kanban_rearrange,
        kanban_status_field=kanban_status_field,
        kanban_api_endpoint=kanban_api_endpoint,
        kanban_allowed_by_id=kanban_allowed_by_id,
        kanban_rank_field=kanban_rank_field,
        overlay_series_data=overlay_series_data,
        group_by=group_by,
        filter_columns=filter_columns,
        active_filters=active_filters,
        cohort_aggregate_values=cohort_aggregate_values,
    )
