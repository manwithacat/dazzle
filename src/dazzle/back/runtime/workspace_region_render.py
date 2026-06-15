"""Phase 6 of the workspace region handler — typed-primitive render tail.

Extracted from ``_workspace_region_handler`` in #1057 cut 13 (v0.67.112).
Decomposed into per-family adapter-ctx builders in cut 14 (v0.67.113).

Pipeline (post phases 1-5):

1. Whitelist-gate on ``display_upper`` — every display that has a
   typed-primitive adapter is in one of the family tuples.
2. Dispatch to the family builder (chart / list / card / dashboard /
   specialty) — each builds the per-display ``adapter_ctx`` slice.
3. Call ``WorkspaceRegionAdapter().build(ir_region, adapter_ctx)``
   and feed the resulting surface to ``FragmentRenderer().render()``.
4. Wrap the typed-primitive HTML in the ``<div data-dz-region>``
   chrome and return the string.

Family layout (34 displays):

- **chart** (11): BAR_CHART, LINE_CHART, AREA_CHART, SPARKLINE,
  HISTOGRAM, HEATMAP, FUNNEL_CHART, BAR_TRACK, BULLET, BOX_PLOT, RADAR
- **list** (7): LIST, KANBAN, QUEUE, TIMELINE, GRID, TREE, ACTIVITY_FEED
- **card** (6): DETAIL, PROFILE_CARD, ENTITY_CARD (async), CONFIRM_ACTION_PANEL,
  METRICS, STATUS_LIST
- **dashboard** (6): COHORT_STRIP, DAY_TIMELINE, TASK_INBOX (async),
  PROGRESS, ACTION_GRID, PIPELINE_STEPS
- **specialty** (4): DIAGRAM, SEARCH_BOX, TABBED_LIST, PIVOT_TABLE

The two ``RenderEnv`` + ``RegionRenderInputs`` dataclasses thread
named state into every builder without 8-arg signatures — agents
reading any builder see exactly which fields it consumes via
``env.inputs.<field>`` / ``env.request`` / ``env.user_ctx``.
"""

import html as _html_mod
import logging
from dataclasses import dataclass, field
from typing import Any

from dazzle.back.runtime.workspace_card_data import (
    _build_cohort_cells,
    _build_day_timeline_slots,
    _build_task_inbox_payload,
)
from dazzle.back.runtime.workspace_card_fetchers import (
    _build_entity_card_sections,
    _fetch_entity_card_section_rows,
    _fetch_task_inbox_items_per_source,
)
from dazzle.back.runtime.workspace_context import WorkspaceRegionContext
from dazzle.back.runtime.workspace_region_prelude import RequestUserContext

logger = logging.getLogger(__name__)


@dataclass
class RegionRenderInputs:
    """All shapes produced by phases 1-5 that the typed-primitive
    adapter dispatch consumes.

    Most fields default to an empty shape — only the display whose
    branch reads a given field populates it upstream. The dataclass
    is a single typed contract between the orchestration handler
    and the render tail; adding a new display requires one new
    field here plus one new branch in the relevant family builder.
    """

    items: list[dict[str, Any]] = field(default_factory=list)
    columns: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    metrics: list[dict[str, Any]] = field(default_factory=list)
    bucketed_metrics: list[dict[str, Any]] = field(default_factory=list)
    kanban_columns: list[str] = field(default_factory=list)

    # Per-display pre-computes
    heatmap_matrix: list[dict[str, Any]] = field(default_factory=list)
    heatmap_col_values: list[str] = field(default_factory=list)
    heatmap_thresholds: list[float] = field(default_factory=list)
    histogram_bins: list[dict[str, Any]] = field(default_factory=list)
    box_plot_stats: list[dict[str, Any]] = field(default_factory=list)
    pivot_buckets: list[dict[str, Any]] = field(default_factory=list)
    pivot_dim_specs: list[dict[str, Any]] = field(default_factory=list)
    tree_items: list[dict[str, Any]] = field(default_factory=list)
    source_tabs: list[Any] = field(default_factory=list)
    bar_track_rows: list[dict[str, Any]] = field(default_factory=list)
    bar_track_max: float = 0.0
    bullet_rows: list[dict[str, Any]] = field(default_factory=list)
    bullet_max_value: float = 0.0
    progress_stage_counts: list[dict[str, Any]] = field(default_factory=list)
    progress_total: int = 0
    progress_complete_count: int = 0
    progress_complete_pct: float = 0.0
    action_card_data: list[dict[str, Any]] = field(default_factory=list)
    pipeline_stage_data: list[dict[str, Any]] = field(default_factory=list)
    profile_card_data: dict[str, Any] = field(default_factory=dict)
    confirm_state_value: str = ""
    queue_transitions: list[dict[str, str]] = field(default_factory=list)
    queue_status_field: str = ""
    queue_api_endpoint: str = ""
    overlay_series_data: list[dict[str, Any]] = field(default_factory=list)
    group_by: Any = None  # str | BucketRef | None
    filter_columns: list[dict[str, Any]] = field(default_factory=list)
    active_filters: dict[str, str] = field(default_factory=dict)
    # #1144 Gap 1 phase 2: per-member resolved values for cohort_strip
    # lenses with `primary_aggregate:`. Keyed by member id (the source
    # row's `id` field). Empty when no aggregate-primary lens is active.
    cohort_aggregate_values: dict[str, Any] = field(default_factory=dict)


@dataclass
class RenderEnv:
    """Per-request render environment bundled for the family builders.

    Each adapter-ctx builder takes one ``RenderEnv`` parameter rather
    than 7 positional args. The fields are exactly what the family
    builders need:

    - ``ctx`` / ``ir_region``: workspace region context + the IR region
      (the typed configs that the adapter consumes).
    - ``inputs``: every pre-computed shape from phases 1-5.
    - ``request``: needed by displays that read query params
      (COHORT_STRIP's `?lens=`, LIST's date-range/`sort_field`).
    - ``user_ctx``: passed to the per-section async fetchers
      (TASK_INBOX, ENTITY_CARD).
    - ``sort``, ``sort_dir``: LIST display surfaces these to the
      filter chrome.
    """

    ctx: WorkspaceRegionContext
    ir_region: Any
    inputs: RegionRenderInputs
    request: Any
    user_ctx: RequestUserContext
    sort: str | None
    sort_dir: str


# Family membership tuples — adding a new display is one entry here
# plus one branch in the matching family builder. Kept as module-level
# constants so the dispatcher can `display in _CHART_FAMILY` cheaply.
_CHART_FAMILY: frozenset[str] = frozenset(
    {
        "BAR_CHART",
        "LINE_CHART",
        "AREA_CHART",
        "SPARKLINE",
        "HISTOGRAM",
        "HEATMAP",
        "FUNNEL_CHART",
        "BAR_TRACK",
        "BULLET",
        "BOX_PLOT",
        "RADAR",
    }
)

_LIST_FAMILY: frozenset[str] = frozenset(
    {"LIST", "KANBAN", "QUEUE", "TIMELINE", "GRID", "TREE", "ACTIVITY_FEED"}
)

_CARD_FAMILY: frozenset[str] = frozenset(
    {
        "DETAIL",
        "PROFILE_CARD",
        "ENTITY_CARD",
        "CONFIRM_ACTION_PANEL",
        "METRICS",
        # `summary` is an alias for `metrics` (see WorkspaceRegionAdapter._ALIASES)
        # — keep the dispatch family-matched so the adapter sees the same
        # ctx shape for both display values.
        "SUMMARY",
        "STATUS_LIST",
    }
)

_DASHBOARD_FAMILY: frozenset[str] = frozenset(
    {
        "COHORT_STRIP",
        "DAY_TIMELINE",
        "TASK_INBOX",
        "PROGRESS",
        "ACTION_GRID",
        "PIPELINE_STEPS",
    }
)

_SPECIALTY_FAMILY: frozenset[str] = frozenset(
    {"DIAGRAM", "SEARCH_BOX", "TABBED_LIST", "PIVOT_TABLE"}
)

# Full whitelist — union of all families.
_TYPED_REGION_DISPLAYS: frozenset[str] = (
    _CHART_FAMILY | _LIST_FAMILY | _CARD_FAMILY | _DASHBOARD_FAMILY | _SPECIALTY_FAMILY
)


def _pick_display_key(columns: list[dict[str, Any]]) -> str:
    """Pick the first non-badge / non-ref column as the visible-row key.

    Used by TREE / GRID / TIMELINE / KANBAN — they all need to know
    which column to render as the card's primary label. Falls back to
    the first column when nothing matches, then to ``"name"`` when
    there are no columns at all.
    """
    return next(
        (c["key"] for c in columns if c.get("type") not in ("badge", "ref")),
        columns[0]["key"] if columns else "name",
    )


# ──────────────────────────── chart family ─────────────────────────────


def _build_chart_adapter_ctx(
    display_upper: str,
    env: RenderEnv,
    base_ctx: dict[str, Any],
) -> dict[str, Any]:
    """Populate adapter_ctx for chart-family displays.

    All chart displays read from one of the pre-computed aggregate
    shapes (``bucketed_metrics`` / ``heatmap_matrix`` /
    ``histogram_bins`` / ``box_plot_stats``). None of them need
    request or auth context.
    """
    from dazzle.core.ir import BucketRef as _BucketRef

    inputs = env.inputs
    ctx_region = env.ctx.ctx_region
    adapter_ctx = dict(base_ctx)

    if display_upper == "BAR_CHART":
        adapter_ctx["buckets"] = inputs.bucketed_metrics
        adapter_ctx["chart_label"] = ctx_region.title
    elif display_upper in ("LINE_CHART", "AREA_CHART"):
        # TimeSeries variants share the same point shape.
        adapter_ctx["points"] = inputs.bucketed_metrics
        adapter_ctx["chart_label"] = ctx_region.title
        adapter_ctx["reference_lines"] = getattr(ctx_region, "reference_lines", [])
        adapter_ctx["reference_bands"] = getattr(ctx_region, "reference_bands", [])
        adapter_ctx["overlay_series_data"] = inputs.overlay_series_data
    elif display_upper == "SPARKLINE":
        adapter_ctx["points"] = inputs.bucketed_metrics
        adapter_ctx["chart_label"] = ctx_region.title
    elif display_upper == "HISTOGRAM":
        adapter_ctx["histogram_bins"] = inputs.histogram_bins
        adapter_ctx["reference_lines"] = getattr(ctx_region, "reference_lines", [])
    elif display_upper == "HEATMAP":
        adapter_ctx["heatmap_matrix"] = inputs.heatmap_matrix
        adapter_ctx["heatmap_col_values"] = inputs.heatmap_col_values
        adapter_ctx["heatmap_thresholds"] = inputs.heatmap_thresholds
        adapter_ctx["total"] = inputs.total
        adapter_ctx["items"] = inputs.items
    elif display_upper == "FUNNEL_CHART":
        adapter_ctx["kanban_columns"] = inputs.kanban_columns
        adapter_ctx["bucketed_metrics"] = inputs.bucketed_metrics
    elif display_upper == "BAR_TRACK":
        adapter_ctx["bar_track_rows"] = inputs.bar_track_rows
        adapter_ctx["bar_track_max"] = inputs.bar_track_max
    elif display_upper == "BULLET":
        adapter_ctx["bullet_rows"] = inputs.bullet_rows
        adapter_ctx["bullet_max_value"] = inputs.bullet_max_value
    elif display_upper == "BOX_PLOT":
        adapter_ctx["box_plot_stats"] = inputs.box_plot_stats
    elif display_upper == "RADAR":
        # Radar consumes (label, value) axis tuples — the bucketed
        # metrics shape is one step richer than what the primitive
        # wants, so we coerce here.
        radar_axes: list[tuple[str, float]] = []
        for entry in inputs.bucketed_metrics or []:
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
        adapter_ctx["chart_label"] = ctx_region.title

    # Quiet the noqa: BucketRef is only used when display is KANBAN
    # (which is list family); keeping the import scoped to this
    # function avoids a top-level import that mypy then warns about.
    _ = _BucketRef
    return adapter_ctx


# ───────────────────────────── list family ─────────────────────────────


def _build_list_adapter_ctx(
    display_upper: str,
    env: RenderEnv,
    base_ctx: dict[str, Any],
) -> dict[str, Any]:
    """Populate adapter_ctx for list-family displays (row/column views).

    LIST is the foundational list-view contract — sort headers,
    filter bar, date-range picker, CSV export. The others share the
    same `items` + `columns` + `display_key` core.
    """
    from dazzle.core.ir import BucketRef as _BucketRef

    inputs = env.inputs
    ctx = env.ctx
    ctx_region = ctx.ctx_region
    adapter_ctx = dict(base_ctx)

    if display_upper == "LIST":
        adapter_ctx["items"] = inputs.items
        adapter_ctx["columns"] = inputs.columns
        adapter_ctx["total"] = inputs.total
        adapter_ctx["endpoint"] = ctx_region.endpoint
        adapter_ctx["region_name"] = getattr(ctx_region, "name", "")
        adapter_ctx["filter_columns"] = inputs.filter_columns
        adapter_ctx["active_filters"] = inputs.active_filters
        adapter_ctx["date_range"] = getattr(ctx_region, "date_range", False)
        adapter_ctx["date_field"] = getattr(ctx_region, "date_field", "")
        adapter_ctx["date_from"] = env.request.query_params.get("date_from", "")
        adapter_ctx["date_to"] = env.request.query_params.get("date_to", "")
        adapter_ctx["csv_export"] = getattr(ctx_region, "csv_export", False)
        adapter_ctx["sort_field"] = env.sort or ""
        adapter_ctx["sort_dir"] = env.sort_dir
        adapter_ctx["empty_message"] = ctx.surface_empty_message or ctx_region.empty_message
        # #1233 — action_id → POST URL map for row_action buttons.
        adapter_ctx["row_action_routes"] = getattr(ctx, "row_action_routes", None) or {}
        # #1303 — per-row drill-to-detail URL template (empty = no row links).
        adapter_ctx["detail_url_template"] = getattr(ctx, "detail_url_template", "") or ""
    elif display_upper == "KANBAN":
        adapter_ctx["items"] = inputs.items
        adapter_ctx["columns"] = inputs.columns
        adapter_ctx["kanban_columns"] = inputs.kanban_columns
        adapter_ctx["display_key"] = _pick_display_key(inputs.columns)
        adapter_ctx["group_by"] = (
            inputs.group_by.field if isinstance(inputs.group_by, _BucketRef) else inputs.group_by
        )
    elif display_upper == "QUEUE":
        adapter_ctx["items"] = inputs.items
        adapter_ctx["columns"] = inputs.columns
        adapter_ctx["total"] = inputs.total
        adapter_ctx["metrics"] = inputs.metrics
        adapter_ctx["queue_transitions"] = inputs.queue_transitions
        adapter_ctx["queue_status_field"] = inputs.queue_status_field
        adapter_ctx["queue_api_endpoint"] = inputs.queue_api_endpoint
    elif display_upper == "TIMELINE":
        adapter_ctx["items"] = inputs.items
        adapter_ctx["columns"] = inputs.columns
        adapter_ctx["display_key"] = _pick_display_key(inputs.columns)
    elif display_upper == "GRID":
        adapter_ctx["items"] = inputs.items
        adapter_ctx["columns"] = inputs.columns
        adapter_ctx["display_key"] = _pick_display_key(inputs.columns)
        adapter_ctx["entity_name"] = ctx.source
    elif display_upper == "TREE":
        adapter_ctx["tree_items"] = inputs.tree_items
        adapter_ctx["items"] = inputs.items
        adapter_ctx["display_key"] = _pick_display_key(inputs.columns)
    elif display_upper == "ACTIVITY_FEED":
        adapter_ctx["items"] = inputs.items

    return adapter_ctx


# ───────────────────────────── card family ─────────────────────────────


async def _build_card_adapter_ctx(
    display_upper: str,
    env: RenderEnv,
    base_ctx: dict[str, Any],
) -> dict[str, Any]:
    """Populate adapter_ctx for card-family displays (single-record /
    curated panels).

    ENTITY_CARD is async — it fans out per-section queries to
    related entities via ``_fetch_entity_card_section_rows``. The
    other cards read from already-computed shapes upstream.
    """
    inputs = env.inputs
    ctx = env.ctx
    ctx_region = ctx.ctx_region
    adapter_ctx = dict(base_ctx)

    if display_upper == "DETAIL":
        adapter_ctx["item"] = inputs.items[0] if inputs.items else None
        adapter_ctx["fields"] = inputs.columns
    elif display_upper == "PROFILE_CARD":
        adapter_ctx["profile_card_data"] = inputs.profile_card_data
    elif display_upper == "CONFIRM_ACTION_PANEL":
        adapter_ctx["state_value"] = inputs.confirm_state_value
        adapter_ctx["confirmations"] = getattr(ctx_region, "confirmations", [])
        adapter_ctx["primary_action_url"] = getattr(ctx_region, "primary_action_url", "")
        adapter_ctx["secondary_action_url"] = getattr(ctx_region, "secondary_action_url", "")
        adapter_ctx["revoke_url"] = getattr(ctx_region, "revoke_url", "")
        adapter_ctx["audit_enabled"] = getattr(ctx_region, "audit_enabled", False)
    elif display_upper in ("METRICS", "SUMMARY"):
        # `summary` aliases to `metrics` in the adapter (#1058 follow-up).
        adapter_ctx["metrics"] = inputs.metrics
        adapter_ctx["columns"] = inputs.columns
    elif display_upper == "STATUS_LIST":
        adapter_ctx["status_entries"] = getattr(ctx_region, "status_entries", [])
    elif display_upper == "ENTITY_CARD":
        card_cfg = getattr(env.ir_region, "entity_card_config", None)
        if card_cfg is not None:
            # #1017 — per-section fan-out for modes that pull from
            # related entities (mini_bars, stamps, thread_summary).
            rows_per_section = await _fetch_entity_card_section_rows(
                config=card_cfg,
                ctx=ctx,
                request=env.request,
                auth_context=env.user_ctx.auth_ctx_for_filters,
                user_id=env.user_ctx.user_id,
                # #1225: thread context_id so per-section
                # `filter: X = current_context` predicates resolve.
                context_id=env.user_ctx.filter_context.get("current_context"),
            )
            adapter_ctx["entity_card_sections"] = _build_entity_card_sections(
                items=inputs.items,
                config=card_cfg,
                rows_per_section=rows_per_section,
            )
            if inputs.items:
                record = inputs.items[0]
                adapter_ctx["entity_card_record_label"] = str(
                    record.get("name") or record.get("title") or record.get("message") or ""
                )

    return adapter_ctx


# ─────────────────────────── dashboard family ──────────────────────────


async def _build_dashboard_adapter_ctx(
    display_upper: str,
    env: RenderEnv,
    base_ctx: dict[str, Any],
) -> dict[str, Any]:
    """Populate adapter_ctx for dashboard-chrome displays.

    TASK_INBOX is async — it fans out per-source queries to the
    declared inbox sources. The others read from already-computed
    shapes upstream.
    """
    import datetime as _dt

    inputs = env.inputs
    ctx = env.ctx
    ir_region = env.ir_region
    adapter_ctx = dict(base_ctx)

    if display_upper == "COHORT_STRIP":
        cohort_cfg = getattr(ir_region, "cohort_strip_config", None)
        if cohort_cfg is not None:
            active_lens_id = (
                env.request.query_params.get("lens")
                or getattr(cohort_cfg, "default_lens", "")
                or (getattr(cohort_cfg.lenses[0], "id", "") if cohort_cfg.lenses else "")
            )
            adapter_ctx["cohort_active_lens"] = active_lens_id
            adapter_ctx["cohort_cells"] = _build_cohort_cells(
                items=inputs.items,
                config=cohort_cfg,
                active_lens_id=active_lens_id,
                # #1299: the source entity's display_field, so a self-referential
                # `member_via: id` resolves cell labels to the display name
                # instead of the raw UUID.
                source_display_field=str(
                    getattr(getattr(ctx, "entity_spec", None), "display_field", "") or ""
                ),
                # #1148: thread the IR-declared row_action through so
                # each cell can carry a per-row click-to-POST button.
                row_action=getattr(ir_region, "row_action", None),
                # #1144 Gap 1 phase 2: per-member aggregate values
                # resolved upstream in orchestration phase 4.
                cohort_aggregate_values=inputs.cohort_aggregate_values,
                # #1233 — action_id → POST URL map for emitting
                # ``data-dz-row-action-url`` on each row_action button.
                row_action_routes=getattr(env.ctx, "row_action_routes", None),
            )
    elif display_upper == "DAY_TIMELINE":
        day_cfg = getattr(ir_region, "day_timeline_config", None)
        if day_cfg is not None:
            adapter_ctx["day_timeline_slots"] = _build_day_timeline_slots(
                items=inputs.items,
                config=day_cfg,
                now=_dt.datetime.now(_dt.UTC),
                # #1148: thread the IR-declared row_action through so
                # each slot can carry a per-row click-to-POST button.
                row_action=getattr(ir_region, "row_action", None),
                # #1233 — action_id → POST URL map.
                row_action_routes=getattr(env.ctx, "row_action_routes", None),
            )
    elif display_upper == "TASK_INBOX":
        inbox_cfg = getattr(ir_region, "task_inbox_config", None)
        if inbox_cfg is not None:
            # #1015 (v0.67.16) — fan out per-source queries.
            items_per_source = await _fetch_task_inbox_items_per_source(
                config=inbox_cfg,
                ctx=ctx,
                request=env.request,
                auth_context=env.user_ctx.auth_ctx_for_filters,
                user_id=env.user_ctx.user_id,
            )
            inbox_items, inbox_chips = _build_task_inbox_payload(
                items=inputs.items,
                config=inbox_cfg,
                items_per_source=items_per_source,
                # #1303 — drill-gated entity→detail-URL map for per-item drill_url.
                entity_detail_urls=getattr(ctx, "entity_detail_urls", None),
            )
            adapter_ctx["task_inbox_items"] = inbox_items
            adapter_ctx["task_inbox_chips"] = inbox_chips
    elif display_upper == "PROGRESS":
        adapter_ctx["stage_counts"] = inputs.progress_stage_counts
        adapter_ctx["progress_total"] = inputs.progress_total
        adapter_ctx["complete_count"] = inputs.progress_complete_count
        adapter_ctx["complete_pct"] = inputs.progress_complete_pct
        adapter_ctx["items"] = inputs.items
    elif display_upper == "ACTION_GRID":
        adapter_ctx["action_cards"] = inputs.action_card_data
    elif display_upper == "PIPELINE_STEPS":
        adapter_ctx["pipeline_stage_data"] = inputs.pipeline_stage_data

    return adapter_ctx


# ─────────────────────────── specialty family ──────────────────────────


def _build_specialty_adapter_ctx(
    display_upper: str,
    env: RenderEnv,
    base_ctx: dict[str, Any],
) -> dict[str, Any]:
    """Populate adapter_ctx for specialty displays — the odd ones out
    that don't fit chart/list/card/dashboard.

    DIAGRAM: Mermaid source / nodes-edges.
    SEARCH_BOX: source entity + placeholder copy.
    TABBED_LIST: HTMX-driven lazy panels via source_tabs.
    PIVOT_TABLE: multi-dim aggregate — its own pivot_buckets + dim_specs.
    """
    inputs = env.inputs
    ctx = env.ctx
    ctx_region = ctx.ctx_region
    adapter_ctx = dict(base_ctx)

    if display_upper == "DIAGRAM":
        adapter_ctx["nodes"] = getattr(ctx_region, "nodes", []) or []
        adapter_ctx["edges"] = getattr(ctx_region, "edges", []) or []
    elif display_upper == "SEARCH_BOX":
        adapter_ctx["source_entity"] = getattr(ctx, "source", "") or ""
        adapter_ctx["name"] = getattr(ctx_region, "name", "")
        adapter_ctx["placeholder"] = getattr(ctx_region, "search_placeholder", "") or ""
        adapter_ctx["coaching_message"] = getattr(ctx_region, "coaching_message", "") or ""
    elif display_upper == "TABBED_LIST":
        adapter_ctx["region_name"] = getattr(ctx_region, "name", "")
        # The tabbed_list adapter consumes plain dicts (entity_name / key /
        # label / endpoint / eager); the runtime supplies SourceTabContext
        # objects. Normalise to the dict shape so the lazy-tab strip renders
        # (#1388 — before the base endpoint was registered this render path
        # was never reached, so the object→dict gap went unnoticed).
        adapter_ctx["source_tabs"] = [
            st
            if isinstance(st, dict)
            else {
                "entity_name": getattr(st, "entity_name", ""),
                "key": (getattr(st, "entity_name", "") or "").lower(),
                "label": getattr(st, "label", "") or getattr(st, "entity_name", ""),
                "endpoint": getattr(st, "endpoint", ""),
                "eager": bool(getattr(st, "eager", False)),
            }
            for st in (inputs.source_tabs or [])
        ]
    elif display_upper == "PIVOT_TABLE":
        adapter_ctx["pivot_buckets"] = inputs.pivot_buckets
        adapter_ctx["pivot_dim_specs"] = inputs.pivot_dim_specs
        adapter_ctx["bucketed_metrics"] = inputs.bucketed_metrics
        adapter_ctx["columns"] = inputs.columns

    return adapter_ctx


# ──────────────────────────── top-level entry ──────────────────────────


async def render_region_html(
    request: Any,
    ctx: WorkspaceRegionContext,
    user_ctx: RequestUserContext,
    inputs: RegionRenderInputs,
    sort: str | None,
    sort_dir: str,
) -> str:
    """Build the typed-primitive HTML body and wrap in region chrome.

    Returns the full ``<div data-dz-region>…</div>`` string ready for
    ``HTMLResponse``. Dispatches to the matching family builder
    (chart / list / card / dashboard / specialty) based on
    ``display_upper`` membership.

    Failures inside the adapter or fragment renderer log at ERROR
    and emit a visible "render failed" placeholder so a broken
    primitive doesn't hide silently.
    """
    display_upper = ctx.ctx_region.display
    typed_primitive_html: str = ""

    if display_upper in _TYPED_REGION_DISPLAYS:
        from dazzle.back.runtime.renderers.region_adapter import WorkspaceRegionAdapter
        from dazzle.render.fragment import FragmentRenderer

        # Adapter wants the lowercase display value (its _BUILDERS keys).
        # `ctx_region.display` is the authoritative post-inference value
        # (e.g. EX-047 promotes a region with `aggregate:` from LIST →
        # SUMMARY); `ir_region.display` is the raw declared value and may
        # still be "list" in that case. The display_upper whitelist gate
        # above already validated against _TYPED_REGION_DISPLAYS, so we
        # use display_upper itself rather than failing the render when
        # ir_region disagrees with the inferred mode (#1082).
        ir_region = ctx.ir_region or ctx.ctx_region
        _display_obj = getattr(ir_region, "display", None)
        _display_val = getattr(_display_obj, "value", None) or str(_display_obj or "")
        _effective_display = (
            _display_val
            if _display_val and _display_val.upper() == display_upper
            else display_upper.lower()
        )
        if _effective_display:
            env = RenderEnv(
                ctx=ctx,
                ir_region=ir_region,
                inputs=inputs,
                request=request,
                user_ctx=user_ctx,
                sort=sort,
                sort_dir=sort_dir,
            )
            base_ctx: dict[str, Any] = {
                "region_url": getattr(ctx.ctx_region, "endpoint", "") or "",
            }

            # Dispatch to the matching family builder.
            if display_upper in _CHART_FAMILY:
                adapter_ctx = _build_chart_adapter_ctx(display_upper, env, base_ctx)
            elif display_upper in _LIST_FAMILY:
                adapter_ctx = _build_list_adapter_ctx(display_upper, env, base_ctx)
            elif display_upper in _CARD_FAMILY:
                adapter_ctx = await _build_card_adapter_ctx(display_upper, env, base_ctx)
            elif display_upper in _DASHBOARD_FAMILY:
                adapter_ctx = await _build_dashboard_adapter_ctx(display_upper, env, base_ctx)
            else:  # _SPECIALTY_FAMILY
                adapter_ctx = _build_specialty_adapter_ctx(display_upper, env, base_ctx)

            try:
                # #1082: pass the post-inference display so the
                # adapter routes correctly even when ir_region.display
                # is still the pre-inference raw value (e.g. "list" for
                # a region whose aggregate: promoted it to SUMMARY).
                surface = WorkspaceRegionAdapter().build(
                    ir_region, adapter_ctx, display_override=_effective_display
                )
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

    # Wrap in region chrome. Every region (typed or not) goes through here
    # — the data-dz-region attrs are the JS handle for live updates.
    region_name_attr = _html_mod.escape(ctx.ctx_region.name, quote=True)
    return (
        f'<div data-dz-region data-dz-region-name="{region_name_attr}" '
        f'id="region-{region_name_attr}">'
        f"{typed_primitive_html or ''}"
        f"</div>"
    )
