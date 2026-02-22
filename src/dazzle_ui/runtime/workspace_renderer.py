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

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from dazzle.core.strings import to_api_plural

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
    # Multi-source (v0.33.0)
    sources: list[str] = Field(default_factory=list)
    source_tabs: list[SourceTabContext] = Field(default_factory=list)
    # CSS
    grid_class: str = ""  # col-span/row-span classes
    template: str = "workspace/regions/list.html"  # Region display template


class WorkspaceContext(BaseModel):
    """Top-level rendering context for a workspace page."""

    name: str
    title: str = ""
    purpose: str = ""
    stage: str = ""
    grid_class: str = "grid grid-cols-1 gap-4"  # Outer grid CSS
    regions: list[RegionContext] = Field(default_factory=list)
    endpoint: str = ""  # Base API endpoint for workspace data
    sse_url: str = ""  # SSE stream URL (empty = no live updates)


# =============================================================================
# Stage → Grid Mapping
# =============================================================================

STAGE_GRID_MAP: dict[str, str] = {
    "focus_metric": "grid grid-cols-1 gap-4",
    "dual_pane_flow": "grid grid-cols-1 md:grid-cols-2 gap-4",
    "scanner_table": "grid grid-cols-1 gap-4",
    "monitor_wall": "grid grid-cols-2 lg:grid-cols-3 gap-4",
    "command_center": "grid grid-cols-12 gap-4",
}

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
}

# Region span classes for command_center stage
COMMAND_CENTER_SPANS: list[str] = [
    "col-span-12",
    "col-span-6",
    "col-span-6",
    "col-span-4",
    "col-span-4",
    "col-span-4",
]


# =============================================================================
# Builder
# =============================================================================


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
    grid_class = STAGE_GRID_MAP.get(stage, STAGE_GRID_MAP["focus_metric"])

    # Build entity name → display title lookup from app spec (#358)
    _entity_titles: dict[str, str] = {}
    if app_spec:
        _domain = getattr(app_spec, "domain", None)
        for _e in _domain.entities if _domain else []:
            _entity_titles[_e.name] = getattr(_e, "title", "") or _e.name

    regions: list[RegionContext] = []
    ws_regions = workspace.regions

    for idx, region in enumerate(ws_regions):
        display_mode = region.display
        if hasattr(display_mode, "value"):
            display_mode = display_mode.value
        display_mode = str(display_mode).upper()

        template = DISPLAY_TEMPLATE_MAP.get(display_mode, "workspace/regions/list.html")

        # Build region grid class based on stage
        region_grid = ""
        if stage == "command_center":
            span_idx = min(idx, len(COMMAND_CENTER_SPANS) - 1)
            region_grid = COMMAND_CENTER_SPANS[span_idx]
        elif stage == "focus_metric" and idx == 0:
            region_grid = "col-span-full"
        elif stage == "dual_pane_flow":
            region_grid = ""  # Grid handles 2-col automatically

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

        # Resolve action surface → URL pattern
        action_name = region.action or ""
        action_url = ""
        if action_name and app_spec:
            surfaces = app_spec.surfaces
            for s in surfaces:
                if s.name == action_name:
                    entity_ref = s.entity_ref or ""
                    if entity_ref:
                        if entity_ref == source_name:
                            # Same entity — use row id
                            action_url = f"/{to_api_plural(entity_ref)}/{{id}}"
                        else:
                            # Cross-entity — find FK field in source entity
                            fk_field = _resolve_fk_field(source_name, entity_ref, app_spec)
                            if fk_field:
                                action_url = f"/{to_api_plural(entity_ref)}/{{{fk_field}}}"
                            else:
                                # Fallback: use row id
                                action_url = f"/{to_api_plural(entity_ref)}/{{id}}"
                    break

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
                tab_action_url = f"/{to_api_plural(src)}/{{id}}"
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
                sources=region_sources,
                source_tabs=source_tabs,
                grid_class=region_grid,
                template=template,
            )
        )

    return WorkspaceContext(
        name=workspace.name,
        title=workspace.title or workspace.name.replace("_", " ").title(),
        purpose=workspace.purpose or "",
        stage=stage,
        grid_class=grid_class,
        regions=regions,
        endpoint=f"/api/workspaces/{workspace.name}",
    )


def _resolve_fk_field(
    source_entity: str,
    target_entity: str,
    app_spec: Any,
) -> str | None:
    """Find the FK field in *source_entity* that references *target_entity*.

    Searches the source entity's fields for a ``ref`` type pointing at the
    target entity.  Returns the field name (e.g. ``"customer_id"``) or None.
    """
    domain = getattr(app_spec, "domain", None)
    if not domain:
        return None
    for ent in domain.entities:
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
