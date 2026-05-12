"""Phase 6 of the workspace region handler — typed-primitive render tail.

Extracted from ``_workspace_region_handler`` in #1057 cut 13 (v0.67.112).

Pipeline (post phases 1-5):

1. Whitelist-gate on ``display_upper`` — every display that has a
   typed-primitive adapter is in ``_TYPED_REGION_DISPLAYS``.
2. Build the per-display ``adapter_ctx`` dict from the pre-computed
   data in ``RegionRenderInputs``. Each branch reads the slice the
   adapter consumes for that display family.
3. Call ``WorkspaceRegionAdapter().build(ir_region, adapter_ctx)``
   and feed the resulting surface to ``FragmentRenderer().render()``.
4. Wrap the typed-primitive HTML in the ``<div data-dz-region>``
   chrome and return the string.

The render tail's single input contract is ``RegionRenderInputs`` —
a dataclass bundling every shape produced by phases 1-5 the
adapter dispatchers read. Named-access reads at adapter sites
(``inputs.heatmap_matrix``, ``inputs.bucketed_metrics``) keep the
flow grep-friendly without a 30-arg function signature.

Per-family decomposition (chart/list/card/dashboard/specialty) is
follow-up work — for cut 13 the whole dispatch lives in one
function. Splitting it changes nothing semantically.
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
    field here plus one new ``elif`` branch in ``render_region_html``.
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


# Displays whose adapter builder is mature + whose data shape matches
# the typed-primitive contract. Adding a new display is one entry here
# plus one ``elif`` branch in ``render_region_html``.
_TYPED_REGION_DISPLAYS: tuple[str, ...] = (
    "COHORT_STRIP",
    "DAY_TIMELINE",
    "TASK_INBOX",
    "ENTITY_CARD",
    "PROGRESS",
    "DETAIL",
    "TREE",
    "DIAGRAM",
    "SEARCH_BOX",
    "TABBED_LIST",
    "GRID",
    "HEATMAP",
    "SPARKLINE",
    "STATUS_LIST",
    "PROFILE_CARD",
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
    "BAR_CHART",
    "LINE_CHART",
    "AREA_CHART",
    "BAR_TRACK",
    "BULLET",
    "BOX_PLOT",
    "ACTIVITY_FEED",
    "LIST",
    "RADAR",
)


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
    ``HTMLResponse``. Non-whitelisted displays fall through to an
    empty body wrapped in the chrome (the dispatcher upstream is the
    fallback path for legacy Jinja regions, none of which are left
    after v0.67.70).

    Failures inside the adapter or fragment renderer log at ERROR
    and emit a visible "render failed" placeholder so a broken
    primitive doesn't hide silently.
    """
    import datetime as _dt

    from dazzle.core.ir import BucketRef as _BucketRef

    display_upper = ctx.ctx_region.display
    typed_primitive_html: str = ""

    if display_upper in _TYPED_REGION_DISPLAYS:
        from dazzle.back.runtime.renderers.region_adapter import WorkspaceRegionAdapter
        from dazzle.render.fragment import FragmentRenderer

        # Adapter wants the lowercase display value (its _BUILDERS keys).
        ir_region = ctx.ir_region or ctx.ctx_region
        _display_obj = getattr(ir_region, "display", None)
        _display_val = getattr(_display_obj, "value", None) or str(_display_obj or "")
        if _display_val and _display_val.upper() == display_upper:
            adapter_ctx: dict[str, Any] = {
                "region_url": getattr(ctx.ctx_region, "endpoint", "") or "",
            }

            # Per-display data resolution.
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
                        items=inputs.items,
                        config=_cohort_cfg,
                        active_lens_id=_active_lens_id,
                    )
            elif display_upper == "DAY_TIMELINE":
                _day_cfg = getattr(ir_region, "day_timeline_config", None)
                if _day_cfg is not None:
                    adapter_ctx["day_timeline_slots"] = _build_day_timeline_slots(
                        items=inputs.items,
                        config=_day_cfg,
                        now=_dt.datetime.now(_dt.UTC),
                    )
            elif display_upper == "TASK_INBOX":
                _inbox_cfg = getattr(ir_region, "task_inbox_config", None)
                if _inbox_cfg is not None:
                    # #1015 (v0.67.16) — fan out per-source queries.
                    _items_per_source = await _fetch_task_inbox_items_per_source(
                        config=_inbox_cfg,
                        ctx=ctx,
                        request=request,
                        auth_context=user_ctx.auth_ctx_for_filters,
                        user_id=user_ctx.user_id,
                    )
                    inbox_items, inbox_chips = _build_task_inbox_payload(
                        items=inputs.items,
                        config=_inbox_cfg,
                        items_per_source=_items_per_source,
                    )
                    adapter_ctx["task_inbox_items"] = inbox_items
                    adapter_ctx["task_inbox_chips"] = inbox_chips
            elif display_upper == "PROGRESS":
                adapter_ctx["stage_counts"] = inputs.progress_stage_counts
                adapter_ctx["progress_total"] = inputs.progress_total
                adapter_ctx["complete_count"] = inputs.progress_complete_count
                adapter_ctx["complete_pct"] = inputs.progress_complete_pct
                adapter_ctx["items"] = inputs.items
            elif display_upper == "DETAIL":
                adapter_ctx["item"] = inputs.items[0] if inputs.items else None
                adapter_ctx["fields"] = inputs.columns
            elif display_upper == "TREE":
                adapter_ctx["tree_items"] = inputs.tree_items
                adapter_ctx["items"] = inputs.items
                adapter_ctx["display_key"] = _pick_display_key(inputs.columns)
            elif display_upper == "DIAGRAM":
                adapter_ctx["nodes"] = getattr(ctx.ctx_region, "nodes", []) or []
                adapter_ctx["edges"] = getattr(ctx.ctx_region, "edges", []) or []
            elif display_upper == "SEARCH_BOX":
                adapter_ctx["source_entity"] = getattr(ctx, "source", "") or ""
                adapter_ctx["name"] = getattr(ctx.ctx_region, "name", "")
                adapter_ctx["placeholder"] = getattr(ctx.ctx_region, "search_placeholder", "") or ""
                adapter_ctx["coaching_message"] = (
                    getattr(ctx.ctx_region, "coaching_message", "") or ""
                )
            elif display_upper == "TABBED_LIST":
                adapter_ctx["region_name"] = getattr(ctx.ctx_region, "name", "")
                adapter_ctx["source_tabs"] = inputs.source_tabs
            elif display_upper == "GRID":
                adapter_ctx["items"] = inputs.items
                adapter_ctx["columns"] = inputs.columns
                adapter_ctx["display_key"] = _pick_display_key(inputs.columns)
                adapter_ctx["entity_name"] = ctx.source
            elif display_upper == "HEATMAP":
                adapter_ctx["heatmap_matrix"] = inputs.heatmap_matrix
                adapter_ctx["heatmap_col_values"] = inputs.heatmap_col_values
                adapter_ctx["heatmap_thresholds"] = inputs.heatmap_thresholds
                adapter_ctx["total"] = inputs.total
                adapter_ctx["items"] = inputs.items
            elif display_upper == "SPARKLINE":
                adapter_ctx["points"] = inputs.bucketed_metrics
                adapter_ctx["chart_label"] = ctx.ctx_region.title
            elif display_upper == "STATUS_LIST":
                adapter_ctx["status_entries"] = getattr(ctx.ctx_region, "status_entries", [])
            elif display_upper == "PROFILE_CARD":
                adapter_ctx["profile_card_data"] = inputs.profile_card_data
            elif display_upper == "METRICS":
                adapter_ctx["metrics"] = inputs.metrics
                adapter_ctx["columns"] = inputs.columns
            elif display_upper == "FUNNEL_CHART":
                adapter_ctx["kanban_columns"] = inputs.kanban_columns
                adapter_ctx["bucketed_metrics"] = inputs.bucketed_metrics
            elif display_upper == "HISTOGRAM":
                adapter_ctx["histogram_bins"] = inputs.histogram_bins
                adapter_ctx["reference_lines"] = getattr(ctx.ctx_region, "reference_lines", [])
            elif display_upper == "PIVOT_TABLE":
                adapter_ctx["pivot_buckets"] = inputs.pivot_buckets
                adapter_ctx["pivot_dim_specs"] = inputs.pivot_dim_specs
                adapter_ctx["bucketed_metrics"] = inputs.bucketed_metrics
                adapter_ctx["columns"] = inputs.columns
            elif display_upper == "TIMELINE":
                adapter_ctx["items"] = inputs.items
                adapter_ctx["columns"] = inputs.columns
                adapter_ctx["display_key"] = _pick_display_key(inputs.columns)
            elif display_upper == "KANBAN":
                adapter_ctx["items"] = inputs.items
                adapter_ctx["columns"] = inputs.columns
                adapter_ctx["kanban_columns"] = inputs.kanban_columns
                adapter_ctx["display_key"] = _pick_display_key(inputs.columns)
                adapter_ctx["group_by"] = (
                    inputs.group_by.field
                    if isinstance(inputs.group_by, _BucketRef)
                    else inputs.group_by
                )
            elif display_upper == "PIPELINE_STEPS":
                adapter_ctx["pipeline_stage_data"] = inputs.pipeline_stage_data
            elif display_upper == "QUEUE":
                adapter_ctx["items"] = inputs.items
                adapter_ctx["columns"] = inputs.columns
                adapter_ctx["total"] = inputs.total
                adapter_ctx["metrics"] = inputs.metrics
                adapter_ctx["queue_transitions"] = inputs.queue_transitions
                adapter_ctx["queue_status_field"] = inputs.queue_status_field
                adapter_ctx["queue_api_endpoint"] = inputs.queue_api_endpoint
            elif display_upper == "ACTION_GRID":
                adapter_ctx["action_cards"] = inputs.action_card_data
            elif display_upper == "BAR_CHART":
                adapter_ctx["buckets"] = inputs.bucketed_metrics
                adapter_ctx["chart_label"] = ctx.ctx_region.title
            elif display_upper == "RADAR":
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
                adapter_ctx["chart_label"] = ctx.ctx_region.title
            elif display_upper in ("LINE_CHART", "AREA_CHART"):
                adapter_ctx["points"] = inputs.bucketed_metrics
                adapter_ctx["chart_label"] = ctx.ctx_region.title
                adapter_ctx["reference_lines"] = getattr(ctx.ctx_region, "reference_lines", [])
                adapter_ctx["reference_bands"] = getattr(ctx.ctx_region, "reference_bands", [])
                adapter_ctx["overlay_series_data"] = inputs.overlay_series_data
            elif display_upper == "BAR_TRACK":
                adapter_ctx["bar_track_rows"] = inputs.bar_track_rows
                adapter_ctx["bar_track_max"] = inputs.bar_track_max
            elif display_upper == "BULLET":
                adapter_ctx["bullet_rows"] = inputs.bullet_rows
                adapter_ctx["bullet_max_value"] = inputs.bullet_max_value
            elif display_upper == "BOX_PLOT":
                adapter_ctx["box_plot_stats"] = inputs.box_plot_stats
            elif display_upper == "ACTIVITY_FEED":
                adapter_ctx["items"] = inputs.items
            elif display_upper == "LIST":
                adapter_ctx["items"] = inputs.items
                adapter_ctx["columns"] = inputs.columns
                adapter_ctx["total"] = inputs.total
                adapter_ctx["endpoint"] = ctx.ctx_region.endpoint
                adapter_ctx["region_name"] = getattr(ctx.ctx_region, "name", "")
                adapter_ctx["filter_columns"] = inputs.filter_columns
                adapter_ctx["active_filters"] = inputs.active_filters
                adapter_ctx["date_range"] = getattr(ctx.ctx_region, "date_range", False)
                adapter_ctx["date_field"] = getattr(ctx.ctx_region, "date_field", "")
                adapter_ctx["date_from"] = request.query_params.get("date_from", "")
                adapter_ctx["date_to"] = request.query_params.get("date_to", "")
                adapter_ctx["csv_export"] = getattr(ctx.ctx_region, "csv_export", False)
                adapter_ctx["sort_field"] = sort or ""
                adapter_ctx["sort_dir"] = sort_dir
                adapter_ctx["empty_message"] = (
                    ctx.surface_empty_message or ctx.ctx_region.empty_message
                )
            elif display_upper == "CONFIRM_ACTION_PANEL":
                adapter_ctx["state_value"] = inputs.confirm_state_value
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
                    # #1017 — per-section fan-out for modes that pull
                    # from related entities (mini_bars, stamps,
                    # thread_summary).
                    _rows_per_section = await _fetch_entity_card_section_rows(
                        config=_card_cfg,
                        ctx=ctx,
                        request=request,
                        auth_context=user_ctx.auth_ctx_for_filters,
                        user_id=user_ctx.user_id,
                    )
                    adapter_ctx["entity_card_sections"] = _build_entity_card_sections(
                        items=inputs.items,
                        config=_card_cfg,
                        rows_per_section=_rows_per_section,
                    )
                    if inputs.items:
                        record = inputs.items[0]
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

    # Wrap in region chrome. Every region (typed or not) goes through here
    # — the data-dz-region attrs are the JS handle for live updates.
    region_name_attr = _html_mod.escape(ctx.ctx_region.name, quote=True)
    return (
        f'<div data-dz-region data-dz-region-name="{region_name_attr}" '
        f'id="region-{region_name_attr}">'
        f"{typed_primitive_html or ''}"
        f"</div>"
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
