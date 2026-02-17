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


class RegionContext(BaseModel):
    """Rendering context for a single workspace region."""

    name: str
    title: str = ""
    source: str = ""  # Entity or surface name
    display: str = "LIST"  # LIST, GRID, METRICS, SUMMARY, DETAIL
    endpoint: str = ""  # HTMX data endpoint
    filter_expr: str = ""  # Serialised filter for query params
    sort: list[dict[str, str]] = Field(default_factory=list)
    limit: int | None = None
    empty_message: str = "No data available."
    group_by: str = ""
    aggregates: dict[str, str] = Field(default_factory=dict)
    action: str = ""  # Surface name for row-click navigation
    action_url: str = ""  # Resolved URL pattern for the action surface
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
    stage = (getattr(workspace, "stage", "") or "").lower()
    grid_class = STAGE_GRID_MAP.get(stage, STAGE_GRID_MAP["focus_metric"])

    regions: list[RegionContext] = []
    ws_regions = getattr(workspace, "regions", [])

    for idx, region in enumerate(ws_regions):
        display_mode = getattr(region, "display", "LIST")
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
        for s in getattr(region, "sort", []):
            sort_specs.append(
                {
                    "field": getattr(s, "field", ""),
                    "direction": getattr(s, "direction", "asc"),
                }
            )

        source_name = getattr(region, "source", "") or ""
        endpoint = f"/api/workspaces/{workspace.name}/regions/{region.name}" if source_name else ""

        # Serialize IR filter to JSON for the data endpoint
        filter_expr = ""
        region_filter = getattr(region, "filter", None)
        if region_filter is not None:
            filter_expr = _serialize_filter_to_params(region_filter)

        # Resolve action surface → URL pattern
        action_name = getattr(region, "action", None) or ""
        action_url = ""
        if action_name and app_spec:
            surfaces = getattr(app_spec, "surfaces", [])
            for s in surfaces:
                if s.name == action_name:
                    entity_ref = getattr(s, "entity_ref", "") or ""
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

        regions.append(
            RegionContext(
                name=region.name,
                title=getattr(region, "title", "") or region.name.replace("_", " ").title(),
                source=source_name,
                display=display_mode,
                endpoint=endpoint,
                filter_expr=filter_expr,
                sort=sort_specs,
                limit=getattr(region, "limit", None),
                empty_message=getattr(region, "empty_message", None) or "No data available.",
                group_by=getattr(region, "group_by", "") or "",
                aggregates=dict(getattr(region, "aggregates", {}) or {}),
                action=action_name,
                action_url=action_url,
                grid_class=region_grid,
                template=template,
            )
        )

    return WorkspaceContext(
        name=workspace.name,
        title=getattr(workspace, "title", "") or workspace.name.replace("_", " ").title(),
        purpose=getattr(workspace, "purpose", "") or "",
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
    entities = getattr(domain, "entities", [])
    for ent in entities:
        if ent.name != source_entity:
            continue
        for f in getattr(ent, "fields", []):
            ft = getattr(f, "type", None)
            kind = getattr(ft, "kind", None)
            kind_val: str = (
                kind.value
                if kind is not None and hasattr(kind, "value")
                else str(kind)
                if kind
                else ""
            )
            if kind_val == "ref":
                ref_target = getattr(ft, "entity_ref", None) or getattr(ft, "ref_entity", None)
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
