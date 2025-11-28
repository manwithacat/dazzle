"""
Workspace converter - converts Dazzle IR WorkspaceSpec to DNR UISpec WorkspaceSpec.

This module transforms Dazzle's workspace definitions into DNR's UI specification format,
leveraging the existing layout engine where possible.
"""

from dazzle.core import ir
from dazzle_dnr_ui.specs import (
    AppShellLayout,
    RouteSpec,
    SingleColumnLayout,
    WorkspaceSpec,
)

# =============================================================================
# Layout Inference
# =============================================================================


def _infer_layout_from_workspace(workspace: ir.WorkspaceSpec) -> dict:
    """
    Infer a layout spec from workspace regions.

    Uses heuristics based on region count and names to select appropriate layout.
    """
    regions = workspace.regions

    # If engine_hint is specified, use it to guide layout selection
    hint = workspace.engine_hint

    if hint == "focus_metric":
        # Single hero metric with supporting context
        return SingleColumnLayout(main="FocusMetricView")
    elif hint == "scanner_table":
        # Large data table with filters
        return SingleColumnLayout(main="ScannerTableView")
    elif hint == "monitor_wall":
        # Multiple equal-weight metrics
        return SingleColumnLayout(main="MonitorWallView")

    # Default heuristics based on region count
    if len(regions) == 1:
        return SingleColumnLayout(main=f"{workspace.name}_main")
    elif len(regions) <= 3:
        # Check if we have a natural sidebar candidate
        if any(r.name in ("navigation", "nav", "sidebar", "menu") for r in regions):
            return AppShellLayout(
                sidebar=f"{workspace.name}_sidebar",
                main=f"{workspace.name}_main",
                header=f"{workspace.name}_header" if len(regions) >= 3 else None,
            )
        else:
            return SingleColumnLayout(main=f"{workspace.name}_main")
    else:
        # Many regions -> app shell with sidebar navigation
        return AppShellLayout(
            sidebar=f"{workspace.name}_sidebar",
            main=f"{workspace.name}_main",
            header=f"{workspace.name}_header",
        )


def _generate_routes_from_regions(
    workspace: ir.WorkspaceSpec,
) -> list[RouteSpec]:
    """
    Generate routes for workspace based on regions.

    Each region that can be displayed independently gets a route.
    """
    routes: list[RouteSpec] = []

    # Default route
    routes.append(
        RouteSpec(
            path="/",
            component=f"{workspace.name.title()}Overview",
            title=workspace.title or workspace.name.title(),
        )
    )

    # Route per region (for regions that make sense as standalone views)
    for region in workspace.regions:
        # Skip aggregate-only regions
        if region.aggregates and not region.source:
            continue

        routes.append(
            RouteSpec(
                path=f"/{region.name}",
                component=f"{region.name.title()}View",
                title=region.name.replace("_", " ").title(),
            )
        )

    return routes


# =============================================================================
# Workspace Conversion
# =============================================================================


def convert_workspace(workspace: ir.WorkspaceSpec) -> WorkspaceSpec:
    """
    Convert a Dazzle IR WorkspaceSpec to DNR UISpec WorkspaceSpec.

    Args:
        workspace: Dazzle IR workspace specification

    Returns:
        DNR UISpec workspace specification
    """
    # Infer layout
    layout = _infer_layout_from_workspace(workspace)

    # Generate routes
    routes = _generate_routes_from_regions(workspace)

    # Extract persona from UX spec if available
    persona = None
    if workspace.ux and workspace.ux.persona_variants:
        # Use the first persona variant as the primary persona
        persona = workspace.ux.persona_variants[0].persona

    return WorkspaceSpec(
        name=workspace.name,
        label=workspace.title,
        description=workspace.purpose,
        persona=persona,
        layout=layout,
        routes=routes,
    )


def convert_workspaces(
    workspaces: list[ir.WorkspaceSpec],
) -> list[WorkspaceSpec]:
    """
    Convert a list of Dazzle IR workspaces to DNR UISpec workspaces.

    Args:
        workspaces: List of Dazzle IR workspace specifications

    Returns:
        List of DNR UISpec workspace specifications
    """
    return [convert_workspace(w) for w in workspaces]
