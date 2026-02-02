"""
Workspace converter - converts Dazzle IR WorkspaceSpec to DNR UISpec WorkspaceSpec.

This module transforms Dazzle's workspace definitions into DNR's UI specification format,
leveraging the existing layout engine where possible.
"""

from dazzle.core import ir
from dazzle.core.strings import to_api_plural
from dazzle_ui.specs import (
    AppShellLayout,
    RouteSpec,
    SingleColumnLayout,
    WorkspaceAccessLevel,
    WorkspaceAccessSpec,
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

    # If stage is specified, use it to guide layout selection
    hint = workspace.stage

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


def _find_entity_by_name(
    name: str,
    entities: list[ir.EntitySpec],
) -> ir.EntitySpec | None:
    """Find an entity by name (case-insensitive)."""
    for entity in entities:
        if entity.name.lower() == name.lower():
            return entity
    return None


def _generate_kanban_route(
    region: ir.WorkspaceRegion,
    entity: ir.EntitySpec,
    workspace_prefix: str,
) -> RouteSpec | None:
    """
    Generate a kanban board route for a workspace region.

    Args:
        region: Workspace region with display=kanban
        entity: The entity to display on the board
        workspace_prefix: URL prefix for this workspace

    Returns:
        RouteSpec with KanbanBoard component and metadata, or None if not possible
    """
    group_by = region.group_by
    if not group_by:
        return None

    columns: list[str] = []
    allowed_transitions: dict[str, list[str]] | None = None

    # Check if group_by matches the state machine status field
    if entity.state_machine and entity.state_machine.status_field == group_by:
        columns = list(entity.state_machine.states)
        allowed_transitions = {
            state: sorted(entity.state_machine.get_allowed_targets(state)) for state in columns
        }
    else:
        # Look for an enum field matching group_by
        for field in entity.fields:
            if field.name == group_by and field.type and field.type.enum_values:
                columns = list(field.type.enum_values)
                break

    if not columns:
        return None

    # Build card fields: first 4 non-pk, non-group_by fields
    card_fields: list[dict[str, str]] = []
    for field in entity.fields:
        if field.is_primary_key or field.name == group_by:
            continue
        if field.name in ("created_at", "updated_at"):
            continue
        label = field.name.replace("_", " ").title()
        card_fields.append({"key": field.name, "label": label})
        if len(card_fields) >= 4:
            break

    entity_lower = entity.name.lower()
    api_endpoint = f"/api/{to_api_plural(entity.name)}"

    metadata = {
        "entityName": entity.name,
        "groupByField": group_by,
        "columns": columns,
        "allowedTransitions": allowed_transitions,
        "cardFields": card_fields,
        "apiEndpoint": api_endpoint,
    }

    return RouteSpec(
        path=f"{workspace_prefix}/{entity_lower}/board",
        component="KanbanBoard",
        title=f"{entity.name} Board",
        metadata=metadata,
    )


def _generate_routes_from_surfaces(
    workspace: ir.WorkspaceSpec,
    surfaces: list[ir.SurfaceSpec],
    surface_component_map: dict[str, str],
    is_primary: bool = True,
    entities: list[ir.EntitySpec] | None = None,
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

    # Generate kanban routes for regions with display=kanban
    kanban_is_first = False
    if entities:
        for idx, region in enumerate(workspace.regions):
            if region.display == ir.DisplayMode.KANBAN and region.source:
                entity = _find_entity_by_name(region.source, entities)
                if entity:
                    kanban_route = _generate_kanban_route(region, entity, workspace_prefix)
                    if kanban_route:
                        routes.append(kanban_route)
                        if idx == 0:
                            kanban_is_first = True

    # If kanban is the first region in a primary workspace, add it as root route too
    if kanban_is_first and routes:
        root_path = workspace_prefix if workspace_prefix else "/"
        root_kanban = RouteSpec(
            path=root_path,
            component=routes[0].component,
            title=routes[0].title,
            metadata=routes[0].metadata,
        )
        routes.insert(0, root_kanban)

    # Generate routes for each entity's surfaces
    # v0.14.2: Only include surfaces for entities used in this workspace
    for surface in surfaces:
        entity_name = surface.entity_ref
        if not entity_name:
            continue

        # Filter: only include surfaces for entities in this workspace
        if workspace_entities and entity_name not in workspace_entities:
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

            # Add /entity route (intuitive URL for entity list)
            routes.append(
                RouteSpec(
                    path=f"{workspace_prefix}/{entity_lower}",
                    component=component_name,
                    title=surface.title or f"{entity_name} List",
                )
            )

            # Also add explicit /entity/list route
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
    entities: list[ir.EntitySpec] | None = None,
) -> WorkspaceSpec:
    """
    Convert a Dazzle IR WorkspaceSpec to DNR UISpec WorkspaceSpec.

    Args:
        workspace: Dazzle IR workspace specification
        surfaces: List of all surfaces in the app
        surface_component_map: Mapping of surface names to component names
        is_primary: If True, this workspace gets the root "/" route
        entities: List of all entities in the app (for kanban route generation)

    Returns:
        DNR UISpec workspace specification
    """
    # Infer layout using surfaces
    layout = _infer_layout_from_workspace(workspace, surfaces, surface_component_map)

    # Generate routes from surfaces
    routes = _generate_routes_from_surfaces(
        workspace,
        surfaces,
        surface_component_map,
        is_primary,
        entities=entities,
    )

    # Extract persona from UX spec if available
    persona = None
    if workspace.ux and workspace.ux.persona_variants:
        # Use the first persona variant as the primary persona
        persona = workspace.ux.persona_variants[0].persona

    # Convert access spec if present
    access_spec = None
    if workspace.access:
        access_spec = WorkspaceAccessSpec(
            level=WorkspaceAccessLevel(workspace.access.level.value),
            allow_personas=workspace.access.allow_personas,
            deny_personas=workspace.access.deny_personas,
            redirect_unauthenticated=workspace.access.redirect_unauthenticated,
        )

    return WorkspaceSpec(
        name=workspace.name,
        label=workspace.title,
        description=workspace.purpose,
        persona=persona,
        layout=layout,
        routes=routes,
        access=access_spec,
    )


def convert_workspaces(
    workspaces: list[ir.WorkspaceSpec],
    surfaces: list[ir.SurfaceSpec],
    surface_component_map: dict[str, str],
    entities: list[ir.EntitySpec] | None = None,
) -> list[WorkspaceSpec]:
    """
    Convert a list of Dazzle IR workspaces to DNR UISpec workspaces.

    Args:
        workspaces: List of Dazzle IR workspace specifications
        surfaces: List of all surfaces in the app
        surface_component_map: Mapping of surface names to component names
        entities: List of all entities in the app (for kanban route generation)

    Returns:
        List of DNR UISpec workspace specifications
    """
    # First workspace is primary (gets "/" route), others get workspace-prefixed routes
    return [
        convert_workspace(
            w,
            surfaces,
            surface_component_map,
            is_primary=(i == 0),
            entities=entities,
        )
        for i, w in enumerate(workspaces)
    ]


# =============================================================================
# Persona Route Resolution
# =============================================================================


def compute_persona_default_routes(
    personas: list[ir.PersonaSpec],
    workspaces: list[ir.WorkspaceSpec],
) -> dict[str, str]:
    """
    Compute default routes for personas based on workspace access rules.

    Resolution order:
    1. Persona's explicit default_route (if set in DSL)
    2. First route of persona's default_workspace (if set)
    3. First workspace where access.allow_personas includes this persona
    4. First workspace with access.level == AUTHENTICATED
    5. First workspace (fallback)

    Args:
        personas: List of persona specifications
        workspaces: List of workspace specifications (IR, not UISpec)

    Returns:
        Dict mapping persona_id to their default route
    """
    result: dict[str, str] = {}

    for persona in personas:
        route = _resolve_persona_route(persona, workspaces)
        if route:
            result[persona.id] = route

    return result


def _resolve_persona_route(
    persona: ir.PersonaSpec,
    workspaces: list[ir.WorkspaceSpec],
) -> str | None:
    """Resolve the default route for a single persona."""
    # 1. Explicit default_route
    if persona.default_route:
        return persona.default_route

    # 2. Default workspace
    if persona.default_workspace:
        for i, ws in enumerate(workspaces):
            if ws.name == persona.default_workspace:
                return _workspace_root_route(ws, is_primary=(i == 0))

    # 3. First workspace with explicit persona access
    for i, ws in enumerate(workspaces):
        if ws.access and persona.id in ws.access.allow_personas:
            return _workspace_root_route(ws, is_primary=(i == 0))

    # 4. First workspace with AUTHENTICATED access (any logged-in user)
    for i, ws in enumerate(workspaces):
        if ws.access and ws.access.level == ir.WorkspaceAccessLevel.AUTHENTICATED:
            return _workspace_root_route(ws, is_primary=(i == 0))

    # 5. Fallback to first workspace
    if workspaces:
        return _workspace_root_route(workspaces[0], is_primary=True)

    return None


def _workspace_root_route(workspace: ir.WorkspaceSpec, is_primary: bool) -> str:
    """Get the root route for a workspace."""
    if is_primary:
        return "/"
    return f"/{workspace.name.replace('_', '-')}"
