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


def _entity_to_app_url(entity_name: str) -> str:
    """Build the /app/ detail URL pattern for an entity.

    Matches the convention in server.py: ``/app/{slug}/{id}``
    where slug = entity_name.lower().replace("_", "-").
    """
    slug = entity_name.lower().replace("_", "-")
    return f"/app/{slug}/{{id}}"


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
    aggregates: dict[str, str] = Field(default_factory=dict)
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
    template: str = "workspace/regions/list.html"  # Region display template
    # Diagram data (v0.48.15: DIAGRAM display mode)
    diagram_data: str = ""  # Mermaid diagram source for DIAGRAM regions
    # Region actions (v0.48.15: action buttons on region header)
    region_actions: list[dict[str, str]] = Field(default_factory=list)


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


DISPLAY_TEMPLATE_MAP: dict[str, str] = {
    "LIST": "workspace/regions/list.html",
    "GRID": "workspace/regions/grid.html",
    "METRICS": "workspace/regions/metrics.html",
    "SUMMARY": "workspace/regions/metrics.html",
    "DETAIL": "workspace/regions/detail.html",
    "KANBAN": "workspace/regions/kanban.html",
    "TIMELINE": "workspace/regions/timeline.html",
    "BAR_CHART": "workspace/regions/bar_chart.html",
    "FUNNEL_CHART": "workspace/regions/funnel_chart.html",
    "QUEUE": "workspace/regions/queue.html",
    "TABBED_LIST": "workspace/regions/tabbed_list.html",
    "HEATMAP": "workspace/regions/heatmap.html",
    "PROGRESS": "workspace/regions/progress.html",
    "ACTIVITY_FEED": "workspace/regions/activity_feed.html",
    "TREE": "workspace/regions/tree.html",
    "DIAGRAM": "workspace/regions/diagram.html",
}

# Stage → fold count: how many regions to load eagerly above the fold (#378)
STAGE_FOLD_COUNTS: dict[str, int] = {
    "focus_metric": 3,
    "dual_pane_flow": 4,
    "scanner_table": 2,
    "monitor_wall": 6,
    "command_center": 6,
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
    workspace: Any,
    app_spec: Any | None = None,
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
    if app_spec:
        for _e in app_spec.domain.entities:
            _entity_titles[_e.name] = getattr(_e, "title", "") or _e.name

    regions: list[RegionContext] = []
    ws_regions = workspace.regions

    for idx, region in enumerate(ws_regions):
        display_mode = region.display
        if hasattr(display_mode, "value"):
            display_mode = display_mode.value
        display_mode = str(display_mode).upper()

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

        template = DISPLAY_TEMPLATE_MAP.get(display_mode, "workspace/regions/list.html")

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
            surfaces = app_spec.surfaces
            for s in surfaces:
                if s.name == action_name:
                    entity_ref = s.entity_ref or ""
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
                group_by=region.group_by or "",
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


def _resolve_fk_field(
    source_entity: str,
    target_entity: str,
    app_spec: Any,
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
