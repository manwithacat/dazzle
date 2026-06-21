"""Workspace layout renderer (v0.20.0).

Converts ``WorkspaceSpec`` from the DSL IR into template-ready context models,
with stage-driven CSS grid classes for different layout patterns.

Stage → Layout mapping:

    FOCUS_METRIC    → Single column, hero stat + supporting regions
    DUAL_PANE_FLOW  → 2-column (list + detail) master-detail
    SCANNER_TABLE   → Full-width table + optional filter sidebar
    MONITOR_WALL    → 2×2 or 2×3 grid for status walls
    COMMAND_CENTER  → 12-col grid with region spans
"""

from __future__ import annotations  # required: forward reference

from typing import Any

from pydantic import BaseModel, Field

from dazzle.core import ir
from dazzle.page import app_paths


def _entity_to_app_url(entity_name: str) -> str:
    """Build the /app/ detail URL pattern for an entity (``/app/{slug}/{id}``)
    via the shared #1426 path SSOT (``dazzle.page.app_paths``)."""
    return app_paths.detail_path("/app", app_paths.entity_slug(entity_name))


def _action_to_url(action: str, app_spec: Any | None = None) -> str:
    """Resolve an ``action_grid`` card target to a URL (#891, #979).

    Three forms accepted, in priority order:

      1. **Literal URL** prefixed with `/` (e.g.
         ``"/app/marking-result?status=flagged"``) — used as-is.
         Authors who need query strings, anchors, or explicit paths
         choose this form.

      2. **Surface name** registered in ``app_spec.surfaces`` (e.g.
         ``cohort_analysis_list`` resolved against a surface whose
         ``entity_ref = "CohortAnalysis"``) → ``/app/cohortanalysis``.
         The slug derives from the *entity*, not from the surface name,
         via the shared ``dazzle.page.app_paths`` SSOT (#1426) — the same
         helper the route generator uses, so link and route agree. Pre-#979
         we slugified the surface name directly, producing
         ``/app/cohort-analysis-list`` which doesn't exist.

      3. **Bare slugified fallback** for legacy / literal-path action
         strings (no matching surface, no matching entity). Same
         ``app_paths.entity_slug`` transform on the action string.
         Preserves backward-compat for action targets that mean
         "send the user to /app/<whatever-this-is>".

    Empty input returns empty string (informational card with no
    click-through).
    """
    if not action:
        return ""
    if action.startswith("/"):
        return action

    # Split optional `?query` suffix so the surface lookup matches
    # against the bare name without dragging the query string through.
    name, query = action, ""
    if "?" in action:
        name, query = action.split("?", 1)

    # Form 2: surface lookup. Resolve to the surface's entity_ref
    # slug, which is what the route generator actually registers.
    if app_spec is not None:
        surfaces = getattr(app_spec, "surfaces", None) or []
        for s in surfaces:
            if getattr(s, "name", None) == name:
                entity_ref = getattr(s, "entity_ref", None) or ""
                if entity_ref:
                    base = app_paths.list_path("/app", app_paths.entity_slug(entity_ref))
                    return f"{base}?{query}" if query else base
                # Surface exists but has no entity_ref — fall through
                # to the legacy slugify path on the surface name.
                break

    # Form 3: legacy slugify fallback. Surface not found — treat the
    # action string as a literal URL fragment to slugify.
    base = app_paths.list_path("/app", app_paths.entity_slug(name))
    return f"{base}?{query}" if query else base


def _flatten_group_by(value: Any) -> str:
    """Reduce IR group_by (str | BucketRef | None) to a string for templates.

    BucketRef is a v0.60.0 time-bucket wrapper — templates see only the
    field name; the unit drove label formatting server-side. Keep the
    typed form on ir_region for runtime routing decisions.
    """
    if value is None:
        return ""
    field_attr = getattr(value, "field", None)
    if field_attr is not None:
        return str(field_attr)
    return str(value)


# =============================================================================
# Context Models
# =============================================================================


class SourceTabContext(BaseModel):
    """Context for a single tab in a multi-source tabbed region."""

    entity_name: str
    label: str = ""
    endpoint: str = ""
    filter_expr: str = ""
    action_url: str = ""


class RegionContext(BaseModel):
    """Rendering context for a single workspace region."""

    name: str
    title: str = ""
    source: str = ""  # Entity or surface name
    display: str = "LIST"  # LIST, GRID, METRICS, SUMMARY, DETAIL, KANBAN, TABBED_LIST
    endpoint: str = ""  # HTMX data endpoint
    filter_expr: str = ""  # Serialised filter for query params
    sort: list[dict[str, str]] = Field(default_factory=list)
    limit: int | None = None
    empty_message: str = "No data available."
    group_by: str = ""
    aggregates: dict[str, Any] = Field(default_factory=dict)  # str→AggregateRef (ADR-0024)
    action: str = ""  # Surface name for row-click navigation
    action_url: str = ""  # Resolved URL pattern for the action surface
    action_id_field: str = "id"  # Field on the item to use as the URL ID (#614)
    # Multi-source (v0.33.0)
    sources: list[str] = Field(default_factory=list)
    source_tabs: list[SourceTabContext] = Field(default_factory=list)
    # Heatmap fields (v0.44.0)
    heatmap_rows: str = ""
    heatmap_columns: str = ""
    heatmap_value: str = ""
    heatmap_thresholds: list[float] = Field(default_factory=list)
    # Progress fields (v0.44.0)
    progress_stages: list[str] = Field(default_factory=list)
    progress_complete_at: str = ""
    # Date range filtering (v0.44.0)
    date_field: str = ""
    date_range: bool = False
    col_span: int = 12  # Resolved column span (4, 6, 8, or 12)
    hidden: bool = False  # User has hidden this region
    template: str = "workspace/regions/_typed_primitive.html"  # default: typed shim
    # Diagram data (v0.48.15: DIAGRAM display mode)
    diagram_data: str = ""  # Mermaid diagram source for DIAGRAM regions
    # Region actions (v0.48.15: action buttons on region header)
    region_actions: list[dict[str, str]] = Field(default_factory=list)
    # v0.61.26 (#883): line/area chart overlays. Server-rendered SVG primitives
    # behind the data series — no extra DB queries, no JS. Each entry is a
    # plain dict (label/value/style for lines, label/from/to/color for bands)
    # so Jinja can read it without import dance.
    reference_lines: list[dict[str, Any]] = Field(default_factory=list)
    reference_bands: list[dict[str, Any]] = Field(default_factory=list)
    # v0.61.30 (#880): Bullet chart row column references — read off each item.
    bullet_label: str = ""
    bullet_actual: str = ""
    bullet_target: str = ""
    # v0.61.25 (#884): Period-over-period delta config for summary tiles.
    # Threaded through so `_compute_aggregate_metrics(delta=...)` resolves
    # without AttributeError. Forward-ref since IR import would cycle.
    delta: Any | None = None
    # v0.61.52 (#894): project-supplied CSS class on the region's outer
    # wrapper. Empty string when not set. Threaded through to the
    # `cards_for_json` payload so the Alpine card-grid binds it on the
    # `<div :data-card-id>` element.
    css_class: str = ""
    # v0.61.60: kicker line rendered above the region title in the
    # dashboard slot's panel header. Empty string when not set —
    # template branches on truthy value.
    eyebrow: str = ""
    # #1391: declarative live-refresh poll interval (seconds, >= 5). None =
    # no polling. Threaded to the DashboardCard so its HTMX trigger appends
    # `, every Ns`.
    refresh_interval: int | None = None
    # v0.61.53 (#893): bar_track display config — fill denominator and
    # value format string. Defaults preserve the legacy "raw" rendering
    # for non-bar_track displays.
    track_max: float | None = None
    track_format: str = ""
    # v0.61.54 (#891): action_grid CTA cards. Each entry is a plain dict
    # (label / icon / count_label / url / tone) — count resolved at
    # request time by the runtime branch via `_fetch_count_metric`. List
    # of dicts (not the IR type) avoids importing core.ir into the UI
    # render context.
    action_cards: list[dict[str, Any]] = Field(default_factory=list)
    # v0.61.55 (#892): profile_card single-record display config. The
    # avatar/primary fields hold raw column names; secondary + facts
    # carry user-template strings interpolated against the fetched item
    # at request time. profile_stats is a list of {label, value-field}.
    avatar_field: str = ""
    primary: str = ""
    secondary: str = ""
    profile_stats: list[dict[str, str]] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    # v0.61.56 (#890): pipeline_steps stages — each entry is a plain
    # dict (label/caption/value). Runtime branch fires one count query
    # per aggregate-shaped value, and renders literal-string values
    # verbatim (v0.61.66 #4). The render-ready list with resolved
    # values is built at request time as `pipeline_stage_data`.
    pipeline_stages: list[dict[str, Any]] = Field(default_factory=list)
    # v0.61.69 (#3): status_list entries — vertical icon + title + copy +
    # state-pill list. Each entry is a plain dict (title/copy/icon/state)
    # so the template iterates without IR-import dance. Empty list = no
    # entries (template renders the empty-state fallback).
    status_entries: list[dict[str, str]] = Field(default_factory=list)
    # v0.61.65: per-tile palette tokens for `display: metrics`. Map metric
    # name → tone token (positive / warning / destructive / accent /
    # neutral). The metrics template surfaces the tone as a per-tile
    # background tint via the `dz-tone-*` class. AegisMark UX patterns
    # roadmap item #2.
    tones: dict[str, str] = Field(default_factory=dict)
    # v0.61.68: optional notice band rendered above the region body
    # in the dashboard slot (AegisMark UX patterns roadmap item #7).
    # Plain dict {title, body, tone} — empty when no notice declared.
    # The dashboard panel template branches on truthy `card.notice` to
    # emit the band.
    notice: dict[str, str] = Field(default_factory=dict)
    # v0.61.72 (#6): confirm_action_panel — irreversible-action consent
    # primitive. confirmations is a list of {title, caption, required}
    # dicts. state_field names the entity column whose value drives the
    # panel's visual mode (off/pending/live/revoked); state_value is
    # resolved at request time from the fetched row. The action URLs
    # are pre-resolved from the IR's surface refs so the template
    # never needs to know about routing. audit_enabled auto-detects
    # from the entity's `audit:` block — when True the template emits
    # the "recorded in audit log" footer.
    confirmations: list[dict[str, Any]] = Field(default_factory=list)
    state_field: str = ""
    state_value: str = ""
    revoke_url: str = ""
    primary_action_url: str = ""
    secondary_action_url: str = ""
    audit_enabled: bool = False


class WorkspaceContext(BaseModel):
    """Top-level rendering context for a workspace page."""

    name: str
    title: str = ""
    purpose: str = ""
    stage: str = ""
    regions: list[RegionContext] = Field(default_factory=list)
    endpoint: str = ""  # Base API endpoint for workspace data
    sse_url: str = ""  # SSE stream URL (empty = no live updates)
    fold_count: int = 3  # Regions above the fold (eager load); rest use intersect
    context_selector_entity: str = ""  # v0.38.0: entity for context selector
    context_selector_label: str = ""  # Human-readable label for context selector
    context_options_url: str = ""  # API URL to fetch context options


# =============================================================================
# Stage → Grid Mapping
# =============================================================================

STAGE_DEFAULT_SPANS: dict[str, list[int] | int] = {
    "focus_metric": [12, 6],
    "dual_pane_flow": 6,
    "scanner_table": 12,
    "monitor_wall": 6,
    "command_center": [12, 6, 6, 4, 4, 4],
    # v0.61.71 (#5, AegisMark UX patterns roadmap): pair_strip is for
    # consent-flow / authorisation layouts where the page is a stack
    # of explicit (info, action) pairs — three sections × two panels
    # each in AegisMark's SIMS opt-in prototype. Every region is
    # half-width; CSS grid auto-flow stacks them into rows of two.
    # On narrow viewports the responsive rules in the project's
    # bundle (or any consumer's media queries) collapse them to a
    # single column. Sibling to dual_pane_flow but reads more
    # naturally for multi-pair flows.
    "pair_strip": 6,
}


def _default_col_span(stage: str, index: int) -> int:
    pattern = STAGE_DEFAULT_SPANS.get(stage)
    if pattern is None:
        return 12
    if isinstance(pattern, int):
        return pattern
    return pattern[min(index, len(pattern) - 1)]


def _get_admin_region_actions(workspace_name: str, region_name: str) -> list[dict[str, str]]:
    """Get action button definitions for admin workspace regions."""
    if not workspace_name.startswith("_") or not workspace_name.endswith("_admin"):
        return []
    try:
        from dazzle.core.admin_builder import get_region_actions

        return get_region_actions(region_name)
    except ImportError:
        return []


def _build_diagram_data(display_mode: str, app_spec: Any) -> str:
    """Generate a Mermaid entity-relationship diagram for DIAGRAM regions."""
    if display_mode != "DIAGRAM" or app_spec is None:
        return ""
    lines = ["erDiagram"]
    domain = getattr(app_spec, "domain", None)
    if domain is None:
        return ""
    entities = getattr(domain, "entities", [])
    entity_names = {e.name for e in entities}
    for entity in entities:
        if getattr(entity, "domain", "") == "platform":
            continue
        lines.append(f"    {entity.name} {{")
        for field in entity.fields[:8]:
            kind = getattr(field.type, "kind", "str")
            kind_str = kind.value if hasattr(kind, "value") else str(kind)
            lines.append(f"        {kind_str} {field.name}")
        if len(entity.fields) > 8:
            lines.append(f"        string _plus_{len(entity.fields) - 8}_more")
        lines.append("    }")
    for entity in entities:
        if getattr(entity, "domain", "") == "platform":
            continue
        for field in entity.fields:
            ref = getattr(field.type, "ref_entity", None)
            if ref and ref in entity_names:
                label = field.name
                lines.append(f"    {entity.name} }}o--|| {ref} : {label}")
    return "\n".join(lines)


# Phase 4 region migration deletion sweep (v0.67.52): 33 region kinds
# route through the typed-Fragment substrate. The `WorkspaceRegionAdapter`
# builds the typed primitive (via the `_TYPED_REGION_DISPLAYS` whitelist
# in `workspace_rendering.py`), the runtime renders it via
# `FragmentRenderer`, and the `_typed_primitive.html` shim wraps the
# pre-rendered HTML in the `region_card` chrome.
#
# Pixel parity with the retired Jinja content templates is a non-goal:
# typed primitives produce semantically equivalent, correctly-styled
# HTML — class names, element nesting, and a11y attributes match the
# typed design system rather than the Jinja-template-by-Jinja-template
# legacy markup. Downstream apps that pinned exact Jinja byte sequences
# need to adapt; agents updating example DSL after this ship is the
# expected workflow.
#
# Three kinds still render dedicated Jinja templates: `radar`,
# `audit_history`, `tab_data`. Each lacks a fully-tested adapter
# builder + IR-side data path; future ships graduate them.
_TYPED_SHIM = "workspace/regions/_typed_primitive.html"
DISPLAY_TEMPLATE_MAP: dict[str, str] = {
    # Original #1015–#1018 typed-only region primitives (v0.67.10).
    "COHORT_STRIP": _TYPED_SHIM,
    "DAY_TIMELINE": _TYPED_SHIM,
    "TASK_INBOX": _TYPED_SHIM,
    "ENTITY_CARD": _TYPED_SHIM,
    # Phase 4 migrations (v0.67.46 → v0.67.51 prepared the adapter
    # plumbing; v0.67.52 flips the consumer to actually use it).
    "PROGRESS": _TYPED_SHIM,
    "DETAIL": _TYPED_SHIM,
    "TREE": _TYPED_SHIM,
    "DIAGRAM": _TYPED_SHIM,
    "SEARCH_BOX": _TYPED_SHIM,
    "TABBED_LIST": _TYPED_SHIM,
    "GRID": _TYPED_SHIM,
    "HEATMAP": _TYPED_SHIM,
    "SPARKLINE": _TYPED_SHIM,
    "STATUS_LIST": _TYPED_SHIM,
    "PROFILE_CARD": _TYPED_SHIM,
    "METRICS": _TYPED_SHIM,
    "SUMMARY": _TYPED_SHIM,  # alias for METRICS (adapter dispatches identically)
    "FUNNEL_CHART": _TYPED_SHIM,
    "HISTOGRAM": _TYPED_SHIM,
    "PIVOT_TABLE": _TYPED_SHIM,
    "TIMELINE": _TYPED_SHIM,
    "KANBAN": _TYPED_SHIM,
    "PIPELINE_STEPS": _TYPED_SHIM,
    "QUEUE": _TYPED_SHIM,
    "ACTION_GRID": _TYPED_SHIM,
    "CONFIRM_ACTION_PANEL": _TYPED_SHIM,
    "BAR_CHART": _TYPED_SHIM,
    "LINE_CHART": _TYPED_SHIM,
    "AREA_CHART": _TYPED_SHIM,
    "BAR_TRACK": _TYPED_SHIM,
    "BULLET": _TYPED_SHIM,
    "BOX_PLOT": _TYPED_SHIM,
    "ACTIVITY_FEED": _TYPED_SHIM,
    "LIST": _TYPED_SHIM,
    "RADAR": _TYPED_SHIM,  # Phase 4 region migration (v0.67.70)
    # AUDIT_HISTORY + TAB_DATA: no DSL consumer + no typed adapter; they
    # fall through to the default `_TYPED_SHIM` and render an empty
    # primitive body. Detail-page audit history is served separately by
    # `render_audit_history_region` (not via this map).
}

# Stage → fold count: how many regions to load eagerly above the fold (#378)
STAGE_FOLD_COUNTS: dict[str, int] = {
    "focus_metric": 3,
    "dual_pane_flow": 4,
    "scanner_table": 2,
    "monitor_wall": 6,
    "command_center": 6,
    # v0.61.71 (#5): pair_strip — load three pairs eagerly (six
    # regions). Consent flows tend to be top-to-bottom linear so
    # users see the whole story before scrolling.
    "pair_strip": 6,
}


# =============================================================================
# Builder
# =============================================================================


def _resolve_thresholds(raw: object) -> list[float]:
    """Extract thresholds from a literal list or ParamRef (use default).

    ParamRef objects carry the DSL default — extract it at context-build time
    so that RegionContext passes Pydantic validation. Full tenant-scoped
    resolution happens later in the rendering handler (#572, #575).
    """
    if raw is None:
        return []
    # ParamRef — use the declared default
    if hasattr(raw, "default") and hasattr(raw, "key"):
        default = raw.default
        if isinstance(default, list):
            return [float(v) for v in default]
        return []
    # Already a list of floats
    if isinstance(raw, list):
        return [float(v) for v in raw]
    return []


def build_workspace_context(
    workspace: ir.WorkspaceSpec,
    app_spec: ir.AppSpec | None = None,
) -> WorkspaceContext:
    """Build a WorkspaceContext from a WorkspaceSpec IR object.

    Args:
        workspace: A ``WorkspaceSpec`` instance from the DSL IR.
        app_spec: Optional ``AppSpec`` for resolving entity metadata.

    Returns:
        WorkspaceContext ready for Jinja2 template rendering.
    """
    stage = (workspace.stage or "").lower()
    fold_count = getattr(workspace, "fold_count", None) or STAGE_FOLD_COUNTS.get(stage, 3)

    # Build entity name → display title lookup from app spec (#358)
    _entity_titles: dict[str, str] = {}
    # v0.61.72 (#6): entity name → entity spec, so confirm_action_panel
    # can auto-detect `audit:` and emit the audit footer when present.
    _entities_by_name: dict[str, Any] = {}
    if app_spec:
        for _e in app_spec.domain.entities:
            _entity_titles[_e.name] = getattr(_e, "title", "") or _e.name
            _entities_by_name[_e.name] = _e

    regions: list[RegionContext] = []
    ws_regions = workspace.regions

    for idx, region in enumerate(ws_regions):
        raw_display = region.display
        display_mode: str = raw_display.value if hasattr(raw_display, "value") else str(raw_display)
        display_mode = display_mode.upper()

        # Cycle 246 — EX-047 aggregate display-mode inference.
        # When a region declares `aggregate: { ... }` but omits an
        # explicit `display:`, the parser default was LIST, which
        # routed the region to the list template and silently dropped
        # the aggregates. Promote to SUMMARY so the metrics template
        # renders the tiles. Confirmed on 4 broken regions across 2
        # apps (simple_task admin_dashboard.metrics,
        # admin_dashboard.team_metrics, team_overview.metrics,
        # fieldtest_hub engineering_dashboard.metrics).
        if display_mode == "LIST" and region.aggregates:
            display_mode = "SUMMARY"

        template = DISPLAY_TEMPLATE_MAP.get(display_mode, _TYPED_SHIM)

        # v0.61.83 (#914): explicit `width:` on the region wins over both
        # the stage default and the kanban auto-promotion. Saved layouts
        # (drag-resize via the dashboard builder) still override this at
        # the layout-restore step in `apply_layout_to_workspace` further
        # down — user resize is the highest signal.
        _explicit_width = getattr(region, "width", None)
        if _explicit_width is not None:
            col_span = _explicit_width
        else:
            col_span = _default_col_span(stage, idx)
            # Kanban needs full width for horizontal scroll to work
            if display_mode == "KANBAN":
                col_span = 12

        # Serialise sort specs
        sort_specs = []
        for s in region.sort:
            sort_specs.append(
                {
                    "field": s.field,
                    "direction": s.direction,
                }
            )

        source_name = region.source or ""
        region_sources = list(region.sources or [])
        endpoint = f"/api/workspaces/{workspace.name}/regions/{region.name}" if source_name else ""

        # Serialize IR filter to JSON for the data endpoint
        filter_expr = ""
        region_filter = region.filter
        if region_filter is not None:
            filter_expr = _serialize_filter_to_params(region_filter)

        # Resolve action surface → URL pattern (must use /app/ prefix for app shell)
        action_name = region.action or ""
        action_url = ""
        action_id_field = "id"
        if action_name and app_spec:
            # v0.61.86 (#916): if `action:` matches a workspace name (not a
            # surface), route to the workspace's app-shell URL with the row
            # identifier as `context_id` query param. Heatmap rows on a
            # pivoted view aggregate across many records, so opening the
            # source-record detail drawer is rarely useful — drilling into
            # a per-row workspace (e.g. `pupil_dashboard` keyed by the
            # `student_profile` row) is the natural action. Workspace lookup
            # comes BEFORE the surface lookup so workspace names take
            # precedence on collision (workspaces and surfaces share a
            # namespace in DSL anyway, but be explicit).
            workspaces = getattr(app_spec, "workspaces", None) or []
            for ws in workspaces:
                if getattr(ws, "name", None) == action_name:
                    action_url = f"/app/workspaces/{action_name}?context_id={{id}}"
                    break

            if not action_url:
                surfaces = app_spec.surfaces
                for surf in surfaces:
                    if surf.name == action_name:
                        entity_ref = surf.entity_ref or ""
                        if entity_ref:
                            if entity_ref == source_name:
                                # Same entity — use row id
                                action_url = _entity_to_app_url(entity_ref)
                            else:
                                # Cross-entity — find FK field in source entity
                                fk_field = _resolve_fk_field(source_name, entity_ref, app_spec)
                                if fk_field:
                                    action_url = _entity_to_app_url(entity_ref)
                                    action_id_field = fk_field
                                else:
                                    # Fallback: use row id
                                    action_url = _entity_to_app_url(entity_ref)
                        break

        # Default: if no explicit action, link rows to the source entity detail view
        if not action_url and source_name:
            action_url = _entity_to_app_url(source_name)

        # Build multi-source tabs
        source_tabs: list[SourceTabContext] = []
        if region_sources:
            source_filters_ir = dict(region.source_filters or {})
            for src in region_sources:
                tab_endpoint = f"/api/workspaces/{workspace.name}/regions/{region.name}/{src}"
                tab_filter = ""
                if src in source_filters_ir:
                    tab_filter = _serialize_filter_to_params(source_filters_ir[src])
                # Per-source action URL: link to the entity's detail page
                tab_action_url = _entity_to_app_url(src)
                # Use entity display title if available, else humanise the name (#358)
                tab_label = _entity_titles.get(src) or src.replace("_", " ").title()
                source_tabs.append(
                    SourceTabContext(
                        entity_name=src,
                        label=tab_label,
                        endpoint=tab_endpoint,
                        filter_expr=tab_filter,
                        action_url=tab_action_url,
                    )
                )

        regions.append(
            RegionContext(
                name=region.name,
                title=getattr(region, "title", "") or region.name.replace("_", " ").title(),
                source=source_name,
                display=display_mode,
                endpoint=endpoint,
                filter_expr=filter_expr,
                sort=sort_specs,
                limit=region.limit,
                empty_message=region.empty_message or "No data available.",
                # Flatten BucketRef → field name for the template-facing context
                # (templates consume `group_by` as a string). The typed IR form
                # (BucketRef) lives on ir_region and drives runtime routing.
                group_by=_flatten_group_by(region.group_by),
                aggregates=dict(region.aggregates or {}),
                action=action_name,
                action_url=action_url,
                action_id_field=action_id_field,
                sources=region_sources,
                source_tabs=source_tabs,
                heatmap_rows=getattr(region, "heatmap_rows", None) or "",
                heatmap_columns=getattr(region, "heatmap_columns", None) or "",
                heatmap_value=getattr(region, "heatmap_value", None) or "",
                heatmap_thresholds=_resolve_thresholds(getattr(region, "heatmap_thresholds", None)),
                progress_stages=list(getattr(region, "progress_stages", None) or []),
                progress_complete_at=getattr(region, "progress_complete_at", None) or "",
                date_field=getattr(region, "date_field", None) or "",
                date_range=bool(getattr(region, "date_range", False)),
                col_span=col_span,
                template=template,
                diagram_data=_build_diagram_data(display_mode, app_spec),
                region_actions=_get_admin_region_actions(workspace.name, region.name),
                reference_lines=[
                    {"label": rl.label, "value": rl.value, "style": rl.style}
                    for rl in (getattr(region, "reference_lines", None) or [])
                ],
                reference_bands=[
                    {
                        "label": rb.label,
                        "from": rb.from_value,
                        "to": rb.to_value,
                        "color": rb.color,
                    }
                    for rb in (getattr(region, "reference_bands", None) or [])
                ],
                bullet_label=getattr(region, "bullet_label", None) or "",
                bullet_actual=getattr(region, "bullet_actual", None) or "",
                bullet_target=getattr(region, "bullet_target", None) or "",
                delta=getattr(region, "delta", None),
                css_class=getattr(region, "css_class", None) or "",  # #894
                eyebrow=getattr(region, "eyebrow", None) or "",  # v0.61.60
                refresh_interval=getattr(region, "refresh_interval", None),  # #1391
                track_max=getattr(region, "track_max", None),  # #893
                track_format=getattr(region, "track_format", None) or "",  # #893
                action_cards=[
                    {
                        "label": c.label,
                        "icon": c.icon,
                        "count": c.count,  # AggregateRef | None (ADR-0024)
                        "url": _action_to_url(c.action, app_spec),  # #979
                        "tone": c.tone,
                    }
                    for c in (getattr(region, "action_cards", None) or [])
                ],  # #891
                avatar_field=getattr(region, "avatar_field", None) or "",  # #892
                primary=getattr(region, "primary", None) or "",  # #892
                secondary=getattr(region, "secondary", None) or "",  # #892
                profile_stats=[
                    {"label": s.label, "value": s.value}
                    for s in (getattr(region, "profile_stats", None) or [])
                ],  # #892
                facts=list(getattr(region, "facts", None) or []),  # #892
                pipeline_stages=[
                    {
                        "label": s.label,
                        "caption": s.caption,
                        "value": s.value,
                        # v0.61.81 (#912): progress was added to PipelineStageSpec
                        # in v0.61.79 (#911) but the IR→template-context boundary
                        # silently dropped it — same bug shape as #910's
                        # profile_stats AttributeError. Parser landed; render
                        # path never received the value. The progress: 0..100
                        # field needs to flow through here too.
                        "progress": s.progress,
                    }
                    for s in (getattr(region, "pipeline_stages", None) or [])
                ],  # #890 + v0.61.66 #4 + v0.61.79 #911 + v0.61.81 #912
                tones=dict(getattr(region, "tones", None) or {}),  # v0.61.65
                notice=(
                    {
                        "title": _notice.title,
                        "body": _notice.body,
                        "tone": _notice.tone,
                    }
                    if (_notice := getattr(region, "notice", None)) is not None
                    else {}
                ),  # v0.61.68 #7
                status_entries=[
                    {
                        "title": e.title,
                        "caption": e.caption,
                        "icon": e.icon,
                        "state": e.state,
                    }
                    for e in (getattr(region, "status_entries", None) or [])
                ],  # v0.61.69 #3
                confirmations=[
                    {
                        "title": c.title,
                        "caption": c.caption,
                        "required": c.required,
                    }
                    for c in (getattr(region, "confirmations", None) or [])
                ],  # v0.61.72 #6
                state_field=getattr(region, "state_field", None) or "",
                # #979: surface-aware URL resolution — resolve to entity slug
                # when the action string matches a surface name in app_spec.
                revoke_url=_action_to_url(getattr(region, "revoke", None) or "", app_spec),
                primary_action_url=_action_to_url(
                    getattr(region, "primary_action", None) or "", app_spec
                ),
                secondary_action_url=_action_to_url(
                    getattr(region, "secondary_action", None) or "", app_spec
                ),
                audit_enabled=(
                    getattr(_entities_by_name.get(source_name or ""), "audit", None) is not None
                ),
            )
        )

    # Context selector (v0.38.0)
    ctx_entity = ""
    ctx_options_url = ""
    ctx_sel = getattr(workspace, "context_selector", None)
    ctx_label = ""
    if ctx_sel:
        ctx_entity = ctx_sel.entity
        ctx_options_url = f"/api/workspaces/{workspace.name}/context-options"
        # Use DSL title if available, else split PascalCase
        ctx_label = _entity_titles.get(ctx_entity, "")
        if not ctx_label or ctx_label == ctx_entity:
            import re

            ctx_label = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", ctx_entity)

    return WorkspaceContext(
        name=workspace.name,
        title=workspace.title or workspace.name.replace("_", " ").title(),
        purpose=workspace.purpose or "",
        stage=stage,
        regions=regions,
        endpoint=f"/api/workspaces/{workspace.name}",
        fold_count=fold_count,
        context_selector_entity=ctx_entity,
        context_selector_label=ctx_label,
        context_options_url=ctx_options_url,
        # #1399 slice 1 — live: on activates the already-wired client SSE
        # connect + sse:entity.* card triggers. Tenant is resolved server-side
        # by the /_ops/sse/events endpoint, so the URL carries no query params.
        sse_url="/_ops/sse/events" if getattr(workspace, "live", False) else "",
    )


_VALID_COL_SPANS = frozenset({3, 4, 6, 8, 12})


def migrate_v1_to_v2(
    v1_layout: dict[str, Any],
    dsl_region_names: list[str],
) -> dict[str, Any]:
    """Convert a v1 layout ``{order, hidden, widths}`` to v2 card-instance format.

    Hidden cards are dropped (not included).  Ghost regions (names not in
    *dsl_region_names*) are skipped.  DSL regions not listed in the v1 order
    are appended at the end.  Each card receives a unique ``migrated-{i}`` id.
    """
    valid_names = set(dsl_region_names)
    saved_order: list[str] = v1_layout.get("order", [])
    hidden_set: set[str] = set(v1_layout.get("hidden", []))
    widths: dict[str, int] = v1_layout.get("widths", {})

    # Build ordered list: saved order first, then unseen DSL regions
    ordered: list[str] = []
    seen: set[str] = set()
    for name in saved_order:
        if name in valid_names and name not in hidden_set:
            ordered.append(name)
            seen.add(name)
    for name in dsl_region_names:
        if name not in seen and name not in hidden_set:
            ordered.append(name)

    cards: list[dict[str, Any]] = []
    for i, region_name in enumerate(ordered):
        card: dict[str, Any] = {
            "id": f"migrated-{i}",
            "region": region_name,
            "col_span": widths.get(region_name, 0),
            "row_order": i,
        }
        # Only keep valid col_span values; 0 means "use DSL default"
        if card["col_span"] not in _VALID_COL_SPANS:
            card["col_span"] = 0
        cards.append(card)

    return {"version": 2, "cards": cards}


def apply_layout_preferences(
    ctx: WorkspaceContext,
    user_prefs: dict[str, str],
) -> WorkspaceContext:
    """Merge user layout preferences with DSL defaults.

    Reads ``workspace.{name}.layout`` from *user_prefs* and applies the
    card-instance layout.  Supports both v1 (auto-migrated) and v2 layouts.
    Returns *ctx* unchanged if no preference exists.
    """
    import json

    pref_key = f"workspace.{ctx.name}.layout"
    raw = user_prefs.get(pref_key)
    if not raw:
        return ctx

    try:
        layout = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return ctx

    # Auto-migrate v1 → v2
    dsl_region_names = [r.name for r in ctx.regions]
    if layout.get("version") != 2:
        layout = migrate_v1_to_v2(layout, dsl_region_names)

    # Build region map for deep-copying DSL region templates
    region_map = {r.name: r for r in ctx.regions}

    # Build region instances from v2 cards list
    cards: list[dict[str, Any]] = layout.get("cards", [])
    # Sort by row_order to ensure deterministic ordering
    cards.sort(key=lambda c: c.get("row_order", 0))

    ordered: list[RegionContext] = []
    for card in cards:
        region_name = card.get("region", "")
        if region_name not in region_map:
            # Ghost region — skip
            continue
        # Deep-copy to allow duplicate cards of the same region
        region = region_map[region_name].model_copy(deep=True)
        col_span = card.get("col_span", 0)
        if col_span in _VALID_COL_SPANS:
            region.col_span = col_span
        ordered.append(region)

    # Return a new context to avoid mutating the shared startup object
    return ctx.model_copy(update={"regions": ordered})


def build_catalog(ctx: WorkspaceContext) -> list[dict[str, str]]:
    """Build the widget catalog for a workspace's card picker."""
    return [
        {
            "name": r.name,
            "title": r.title or r.name.replace("_", " ").title(),
            "display": r.display,
            "entity": r.source,
        }
        for r in ctx.regions
    ]


def render_workspace_content_typed(
    workspace: WorkspaceContext,
    catalog: list[dict[str, str]],
    fold_count: int,
    primary_actions: list[dict[str, str]],
    can_edit_layout: bool = False,
) -> str:
    """Render the workspace content via the typed-Fragment substrate.

    Mirror of the legacy `workspace/_content.html` Jinja render call
    (workspace + catalog + fold_count + primary_actions inputs). Composes
    WorkspaceShell wrapping `Sequence(WorkspaceContextSelector?,
    WorkspaceToolbar, DashboardGrid, AddCardRow)` with a sibling
    WorkspaceDrawer, then renders via FragmentRenderer.

    Phase 4B.5.c shipped byte-equivalence vs the legacy template
    against fixture workspaces; this function applies that mapping to
    real production WorkspaceContext / RegionContext shapes."""
    import json

    from dazzle.render.fragment import (
        AddCardRow,
        CardPicker,
        CardPickerEntry,
        DashboardCard,
        DashboardGrid,
        DashboardNotice,
        FragmentRenderer,
        Sequence,
        WorkspaceContextSelector,
        WorkspaceDrawer,
        WorkspacePrimaryAction,
        WorkspaceShell,
        WorkspaceToolbar,
    )

    ws_title = workspace.title or workspace.name.replace("_", " ").title()

    # ── DashboardCard list ──────────────────────────────────────────
    cards: list[DashboardCard] = []
    for index, r in enumerate(workspace.regions):
        card_id = f"card-{index}"
        eager = index < (fold_count or 0)
        notice_dict = r.notice or {}
        notice = (
            DashboardNotice(
                title=notice_dict.get("title", ""),
                body=notice_dict.get("body", ""),
                tone=notice_dict.get("tone") or "neutral",
            )
            if notice_dict.get("title")
            else None
        )
        cards.append(
            DashboardCard(
                card_id=card_id,
                name=r.name,
                title=r.title or r.name.replace("_", " ").title(),
                display=r.display,
                col_span=r.col_span,
                row_order=index,
                hx_endpoint=f"/api/workspaces/{workspace.name}/regions/{r.name}",
                eager=eager,
                sse_enabled=bool(workspace.sse_url),
                eyebrow=r.eyebrow,
                css_class=getattr(r, "css_class", "") or "",
                notice=notice,
                refresh_interval=getattr(r, "refresh_interval", None),  # #1391
                edit_enabled=can_edit_layout,
            )
        )

    # ── CardPicker ───────────────────────────────────────────────────
    picker_entries = tuple(
        CardPickerEntry(
            name=c["name"],
            title=c["title"],
            entity=c.get("entity", ""),
            display=c.get("display", ""),
        )
        for c in catalog
    )
    picker = CardPicker(
        entries=picker_entries,
        catalog_json=json.dumps(catalog, sort_keys=True),
    )

    # ── WorkspacePrimaryAction list ─────────────────────────────────
    typed_actions = tuple(
        WorkspacePrimaryAction(label=a["label"], route=a["route"]) for a in primary_actions
    )

    # ── Optional context selector ───────────────────────────────────
    inner_pieces: list[object] = []
    if workspace.context_options_url:
        label = workspace.context_selector_label or workspace.context_selector_entity.replace(
            "_", " "
        )
        inner_pieces.append(
            WorkspaceContextSelector(
                workspace_name=workspace.name,
                options_url=workspace.context_options_url,
                label=label,
            )
        )

    inner_pieces.append(WorkspaceToolbar())
    inner_pieces.append(
        DashboardGrid(
            cards=tuple(cards),
            sse_url=workspace.sse_url or "",
            edit_enabled=can_edit_layout,
        )
    )
    inner_pieces.append(AddCardRow(picker=picker))

    shell = WorkspaceShell(
        workspace_name=workspace.name,
        title=ws_title,
        primary_actions=typed_actions,
        fold_count=fold_count if fold_count is not None else 0,
        body=Sequence(children=tuple(inner_pieces)),
    )

    renderer = FragmentRenderer()
    return renderer.render(shell) + renderer.render(WorkspaceDrawer())


def _resolve_fk_field(
    source_entity: str,
    target_entity: str,
    app_spec: ir.AppSpec,
) -> str | None:
    """Find the FK field in *source_entity* that references *target_entity*.

    Searches the source entity's fields for a ``ref`` type pointing at the
    target entity.  Returns the field name (e.g. ``"customer_id"``) or None.
    """
    if not app_spec:
        return None
    for ent in app_spec.domain.entities:
        if ent.name != source_entity:
            continue
        for f in ent.fields:
            kind = f.type.kind
            kind_val: str = (
                kind.value
                if kind is not None and hasattr(kind, "value")
                else str(kind)
                if kind
                else ""
            )
            if kind_val == "ref":
                ref_target = getattr(f.type, "ref_entity", None)
                if ref_target == target_entity:
                    field_name: str = f.name
                    return field_name
    return None


def _serialize_filter_to_params(condition: Any) -> str:
    """Serialize a ConditionExpr to a JSON string for the region data endpoint."""
    import json

    if hasattr(condition, "model_dump"):
        return json.dumps(condition.model_dump(exclude_none=True))
    if isinstance(condition, dict):
        return json.dumps(condition)
    return ""
