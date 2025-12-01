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
# Surface Matching
# =============================================================================


def _find_list_surface_for_entity(
    entity_name: str,
    surfaces: list[ir.SurfaceSpec],
    surface_component_map: dict[str, str],
) -> str | None:
    """Find the list surface component for an entity."""
    for surface in surfaces:
        if surface.entity_ref == entity_name and surface.mode == ir.SurfaceMode.LIST:
            return surface_component_map.get(surface.name)
    return None


def _find_surface_by_mode(
    entity_name: str,
    mode: ir.SurfaceMode,
    surfaces: list[ir.SurfaceSpec],
    surface_component_map: dict[str, str],
) -> str | None:
    """Find a surface component by entity and mode."""
    for surface in surfaces:
        if surface.entity_ref == entity_name and surface.mode == mode:
            return surface_component_map.get(surface.name)
    return None


def _get_default_list_component(
    surfaces: list[ir.SurfaceSpec],
    surface_component_map: dict[str, str],
) -> str | None:
    """Get the first list surface component as default."""
    for surface in surfaces:
        if surface.mode == ir.SurfaceMode.LIST:
            return surface_component_map.get(surface.name)
    # Fall back to any surface
    if surfaces:
        return surface_component_map.get(surfaces[0].name)
    return None


# =============================================================================
# Layout Inference
# =============================================================================


def _infer_layout_from_workspace(
    workspace: ir.WorkspaceSpec,
    surfaces: list[ir.SurfaceSpec],
    surface_component_map: dict[str, str],
) -> dict:
    """
    Infer a layout spec from workspace regions.

    Uses heuristics based on region count and names to select appropriate layout.
    """
    regions = workspace.regions

    # If engine_hint is specified, use it to guide layout selection
    hint = workspace.engine_hint

    # Find the main component to use from surfaces
    main_component = _get_default_list_component(surfaces, surface_component_map) or "Page"

    if hint == "focus_metric":
        # Single hero metric with supporting context
        return SingleColumnLayout(main=main_component)
    elif hint == "scanner_table":
        # Large data table with filters
        return SingleColumnLayout(main=main_component)
    elif hint == "monitor_wall":
        # Multiple equal-weight metrics
        return SingleColumnLayout(main=main_component)

    # Default heuristics based on region count
    if len(regions) == 1:
        return SingleColumnLayout(main=main_component)
    elif len(regions) <= 3:
        # Check if we have a natural sidebar candidate
        if any(r.name in ("navigation", "nav", "sidebar", "menu") for r in regions):
            return AppShellLayout(
                sidebar=f"{workspace.name}_sidebar",
                main=main_component,
                header=f"{workspace.name}_header" if len(regions) >= 3 else None,
            )
        else:
            return SingleColumnLayout(main=main_component)
    else:
        # Many regions -> app shell with sidebar navigation
        return AppShellLayout(
            sidebar=f"{workspace.name}_sidebar",
            main=main_component,
            header=f"{workspace.name}_header",
        )


def _generate_routes_from_surfaces(
    workspace: ir.WorkspaceSpec,
    surfaces: list[ir.SurfaceSpec],
    surface_component_map: dict[str, str],
    is_primary: bool = True,
) -> list[RouteSpec]:
    """
    Generate routes for workspace based on available surfaces.

    Maps surface modes to standard routes:
    - LIST surfaces -> / (root) and /list for primary workspace
    - LIST surfaces -> /workspace-name for secondary workspaces
    - VIEW surfaces -> /detail/:id
    - CREATE surfaces -> /create
    - EDIT surfaces -> /edit/:id

    Args:
        is_primary: If True, this workspace gets the root "/" route.
                   Otherwise, routes are prefixed with workspace name.
    """
    routes: list[RouteSpec] = []
    entities_seen = set()

    # Base path for routes - primary workspace gets "/", others get "/workspace-name"
    workspace_prefix = "" if is_primary else f"/{workspace.name.replace('_', '-')}"

    # Collect entities used in workspace regions
    workspace_entities = set()
    for region in workspace.regions:
        if region.source:
            workspace_entities.add(region.source)

    # If no specific entities, use all surfaces
    if not workspace_entities:
        for surface in surfaces:
            if surface.entity_ref:
                workspace_entities.add(surface.entity_ref)

    # Generate routes for each entity's surfaces
    for surface in surfaces:
        entity_name = surface.entity_ref
        if not entity_name:
            continue

        component_name = surface_component_map.get(surface.name)
        if not component_name:
            continue

        entity_lower = entity_name.lower()

        if surface.mode == ir.SurfaceMode.LIST:
            # First list surface becomes the root route for this workspace
            if entity_name not in entities_seen:
                root_path = workspace_prefix if workspace_prefix else "/"
                routes.append(
                    RouteSpec(
                        path=root_path,
                        component=component_name,
                        title=surface.title or f"{entity_name} List",
                    )
                )
                entities_seen.add(entity_name)

            # Also add explicit /list route
            routes.append(
                RouteSpec(
                    path=f"{workspace_prefix}/{entity_lower}/list",
                    component=component_name,
                    title=surface.title or f"{entity_name} List",
                )
            )

        elif surface.mode == ir.SurfaceMode.VIEW:
            routes.append(
                RouteSpec(
                    path=f"{workspace_prefix}/{entity_lower}/:id",
                    component=component_name,
                    title=surface.title or f"{entity_name} Detail",
                )
            )

        elif surface.mode == ir.SurfaceMode.CREATE:
            routes.append(
                RouteSpec(
                    path=f"{workspace_prefix}/{entity_lower}/create",
                    component=component_name,
                    title=surface.title or f"Create {entity_name}",
                )
            )

        elif surface.mode == ir.SurfaceMode.EDIT:
            routes.append(
                RouteSpec(
                    path=f"{workspace_prefix}/{entity_lower}/:id/edit",
                    component=component_name,
                    title=surface.title or f"Edit {entity_name}",
                )
            )

    # Ensure we have at least one route
    if not routes:
        default_component = _get_default_list_component(surfaces, surface_component_map)
        if default_component:
            root_path = workspace_prefix if workspace_prefix else "/"
            routes.append(
                RouteSpec(
                    path=root_path,
                    component=default_component,
                    title=workspace.title or workspace.name.title(),
                )
            )

    # Sort routes so static paths come before dynamic paths
    # This prevents /task/:id from matching before /task/create
    def route_priority(route: RouteSpec) -> tuple[int, str]:
        path = route.path
        # Count dynamic segments (those starting with :)
        segments = path.split("/")
        dynamic_count = sum(1 for seg in segments if seg.startswith(":"))
        # Static routes (0 dynamic segments) come first, then by path length, then alphabetically
        return (dynamic_count, -len(segments), path)

    routes.sort(key=route_priority)

    return routes


# =============================================================================
# Workspace Conversion
# =============================================================================


def convert_workspace(
    workspace: ir.WorkspaceSpec,
    surfaces: list[ir.SurfaceSpec],
    surface_component_map: dict[str, str],
    is_primary: bool = True,
) -> WorkspaceSpec:
    """
    Convert a Dazzle IR WorkspaceSpec to DNR UISpec WorkspaceSpec.

    Args:
        workspace: Dazzle IR workspace specification
        surfaces: List of all surfaces in the app
        surface_component_map: Mapping of surface names to component names
        is_primary: If True, this workspace gets the root "/" route

    Returns:
        DNR UISpec workspace specification
    """
    # Infer layout using surfaces
    layout = _infer_layout_from_workspace(workspace, surfaces, surface_component_map)

    # Generate routes from surfaces
    routes = _generate_routes_from_surfaces(
        workspace, surfaces, surface_component_map, is_primary
    )

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
    surfaces: list[ir.SurfaceSpec],
    surface_component_map: dict[str, str],
) -> list[WorkspaceSpec]:
    """
    Convert a list of Dazzle IR workspaces to DNR UISpec workspaces.

    Args:
        workspaces: List of Dazzle IR workspace specifications
        surfaces: List of all surfaces in the app
        surface_component_map: Mapping of surface names to component names

    Returns:
        List of DNR UISpec workspace specifications
    """
    # First workspace is primary (gets "/" route), others get workspace-prefixed routes
    return [
        convert_workspace(w, surfaces, surface_component_map, is_primary=(i == 0))
        for i, w in enumerate(workspaces)
    ]
