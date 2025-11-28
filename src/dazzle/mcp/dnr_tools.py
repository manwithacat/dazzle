"""
DNR (Dazzle Native Runtime) MCP tools.

Tools for interacting with BackendSpec and UISpec through MCP.
Based on DNR-MCP-Spec-v1.md specification.
"""

import json
from typing import Any

try:
    from mcp.types import Tool
except ImportError:
    Tool = None  # type: ignore

# =============================================================================
# DNR State (in-memory for now)
# =============================================================================

# Store active specs (would be persisted in real implementation)
_backend_spec: dict[str, Any] | None = None
_ui_spec: dict[str, Any] | None = None


def set_backend_spec(spec: dict[str, Any]) -> None:
    """Set the active backend spec."""
    global _backend_spec
    _backend_spec = spec


def get_backend_spec() -> dict[str, Any] | None:
    """Get the active backend spec."""
    return _backend_spec


def set_ui_spec(spec: dict[str, Any]) -> None:
    """Set the active UI spec."""
    global _ui_spec
    _ui_spec = spec


def get_ui_spec() -> dict[str, Any] | None:
    """Get the active UI spec."""
    return _ui_spec


# =============================================================================
# Tool Definitions
# =============================================================================


def get_dnr_tools() -> list[Tool]:
    """Get DNR-specific MCP tools."""
    if Tool is None:
        return []

    return [
        # Backend Tools
        Tool(
            name="list_dnr_entities",
            description="List all entities in the DNR BackendSpec with field summaries",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="get_dnr_entity",
            description="Get detailed EntitySpec for a specific entity",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Entity name to retrieve",
                    }
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="list_backend_services",
            description="List available backend services (from BackendSpec) with input/output summaries",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_name": {
                        "type": "string",
                        "description": "Optional filter by entity name",
                    }
                },
                "required": [],
            },
        ),
        Tool(
            name="get_backend_service_spec",
            description="Get the full ServiceSpec JSON for a backend service by name",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Service name to retrieve",
                    }
                },
                "required": ["name"],
            },
        ),
        # UI Tools
        Tool(
            name="list_dnr_components",
            description="List known DNR UI components (primitives and patterns)",
            inputSchema={
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["all", "primitives", "patterns"],
                        "description": "Filter by component kind (default: all)",
                    }
                },
                "required": [],
            },
        ),
        Tool(
            name="get_dnr_component_spec",
            description="Get the full UISpec ComponentSpec for a named component",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Component name to retrieve",
                    }
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="list_workspace_layouts",
            description="List available workspace layout types (from UISpec LayoutSpec)",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="create_uispec_component",
            description="Generate and register a new ComponentSpec in the UISpec",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Component name (PascalCase)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Component description",
                    },
                    "atoms": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Names of primitive/pattern components to compose",
                    },
                    "props_schema_hint": {
                        "type": "string",
                        "description": "Optional textual hint describing expected props",
                    },
                },
                "required": ["name", "description", "atoms"],
            },
        ),
        Tool(
            name="patch_uispec_component",
            description="Modify an existing ComponentSpec using JSON-patch operations",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Component name to patch",
                    },
                    "patch": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "op": {
                                    "type": "string",
                                    "enum": ["add", "remove", "replace"],
                                },
                                "path": {"type": "string"},
                                "value": {},
                            },
                            "required": ["op", "path"],
                        },
                        "description": "JSON Patch operations to apply",
                    },
                },
                "required": ["name", "patch"],
            },
        ),
        Tool(
            name="compose_workspace",
            description="Create or update a WorkspaceSpec wiring components into a layout",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_name": {
                        "type": "string",
                        "description": "Workspace name",
                    },
                    "persona": {
                        "type": "string",
                        "description": "Optional persona for the workspace",
                    },
                    "layout_kind": {
                        "type": "string",
                        "description": "Layout type (singleColumn, twoColumnWithHeader, appShell)",
                    },
                    "region_components": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                        "description": "Map from layout region name to ComponentSpec.name",
                    },
                    "routes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "component": {"type": "string"},
                            },
                            "required": ["path", "component"],
                        },
                        "description": "Route definitions",
                    },
                },
                "required": ["workspace_name", "layout_kind", "region_components", "routes"],
            },
        ),
    ]


# =============================================================================
# Tool Implementations
# =============================================================================


def handle_dnr_tool(name: str, arguments: dict[str, Any]) -> str:
    """Handle DNR tool calls."""

    # Backend tools
    if name == "list_dnr_entities":
        return _list_dnr_entities()
    elif name == "get_dnr_entity":
        return _get_dnr_entity(arguments)
    elif name == "list_backend_services":
        return _list_backend_services(arguments)
    elif name == "get_backend_service_spec":
        return _get_backend_service_spec(arguments)

    # UI tools
    elif name == "list_dnr_components":
        return _list_dnr_components(arguments)
    elif name == "get_dnr_component_spec":
        return _get_dnr_component_spec(arguments)
    elif name == "list_workspace_layouts":
        return _list_workspace_layouts()
    elif name == "create_uispec_component":
        return _create_uispec_component(arguments)
    elif name == "patch_uispec_component":
        return _patch_uispec_component(arguments)
    elif name == "compose_workspace":
        return _compose_workspace(arguments)

    return json.dumps({"error": f"Unknown DNR tool: {name}"})


# =============================================================================
# Backend Tool Implementations
# =============================================================================


def _list_dnr_entities() -> str:
    """List all entities in BackendSpec."""
    spec = get_backend_spec()
    if not spec:
        return json.dumps(
            {
                "status": "no_spec",
                "message": "No BackendSpec loaded. Use AppSpec converter or load a spec first.",
                "entities": [],
            }
        )

    entities = spec.get("entities", [])
    summaries = []
    for entity in entities:
        summaries.append(
            {
                "name": entity.get("name"),
                "label": entity.get("label"),
                "field_count": len(entity.get("fields", [])),
                "relation_count": len(entity.get("relations", [])),
            }
        )

    return json.dumps(
        {
            "count": len(summaries),
            "entities": summaries,
        },
        indent=2,
    )


def _get_dnr_entity(args: dict[str, Any]) -> str:
    """Get detailed EntitySpec."""
    name = args.get("name")
    if not name:
        return json.dumps({"error": "name parameter required"})

    spec = get_backend_spec()
    if not spec:
        return json.dumps({"error": "No BackendSpec loaded"})

    entities = spec.get("entities", [])
    entity = next((e for e in entities if e.get("name") == name), None)

    if not entity:
        return json.dumps(
            {
                "error": f"Entity '{name}' not found",
                "available": [e.get("name") for e in entities],
            }
        )

    return json.dumps(entity, indent=2)


def _list_backend_services(args: dict[str, Any]) -> str:
    """List backend services."""
    entity_filter = args.get("entity_name")

    spec = get_backend_spec()
    if not spec:
        return json.dumps(
            {
                "status": "no_spec",
                "message": "No BackendSpec loaded",
                "services": [],
            }
        )

    services = spec.get("services", [])

    # Apply filter if provided
    if entity_filter:
        services = [
            s for s in services if s.get("domain_operation", {}).get("entity") == entity_filter
        ]

    summaries = []
    for svc in services:
        domain_op = svc.get("domain_operation", {})
        summaries.append(
            {
                "name": svc.get("name"),
                "entity": domain_op.get("entity"),
                "kind": domain_op.get("kind"),
                "input_summary": _summarize_schema(svc.get("inputs", {})),
                "output_summary": _summarize_schema(svc.get("outputs", {})),
            }
        )

    return json.dumps(
        {
            "count": len(summaries),
            "filter": entity_filter,
            "services": summaries,
        },
        indent=2,
    )


def _get_backend_service_spec(args: dict[str, Any]) -> str:
    """Get full ServiceSpec."""
    name = args.get("name")
    if not name:
        return json.dumps({"error": "name parameter required"})

    spec = get_backend_spec()
    if not spec:
        return json.dumps({"error": "No BackendSpec loaded"})

    services = spec.get("services", [])
    service = next((s for s in services if s.get("name") == name), None)

    if not service:
        return json.dumps(
            {
                "error": f"Service '{name}' not found",
                "available": [s.get("name") for s in services],
            }
        )

    return json.dumps({"serviceSpec": service}, indent=2)


def _summarize_schema(schema: dict[str, Any]) -> str:
    """Create a brief summary of a schema."""
    fields = schema.get("fields", [])
    if not fields:
        return "(empty)"
    return ", ".join(f["name"] for f in fields[:3]) + ("..." if len(fields) > 3 else "")


# =============================================================================
# UI Tool Implementations
# =============================================================================


# Built-in component registry (from DNR-Components-v1.md)
PRIMITIVE_COMPONENTS = [
    {"name": "Page", "category": "primitive", "description": "Top-level container for a screen"},
    {
        "name": "LayoutShell",
        "category": "primitive",
        "description": "Generic shell arranging header/sidebar/content",
    },
    {"name": "Card", "category": "primitive", "description": "Groups related content visually"},
    {
        "name": "DataTable",
        "category": "primitive",
        "description": "Feature-rich table for tabular data",
    },
    {
        "name": "SimpleTable",
        "category": "primitive",
        "description": "Minimal table for static layouts",
    },
    {"name": "Form", "category": "primitive", "description": "Container for form fields"},
    {"name": "Button", "category": "primitive", "description": "Primary clickable action control"},
    {"name": "IconButton", "category": "primitive", "description": "Compact icon-only button"},
    {"name": "Tabs", "category": "primitive", "description": "Tabbed navigation for sibling views"},
    {"name": "TabPanel", "category": "primitive", "description": "Content panel for a tab"},
    {"name": "Modal", "category": "primitive", "description": "Centered overlay dialog"},
    {"name": "Drawer", "category": "primitive", "description": "Side panel overlay"},
    {"name": "Toolbar", "category": "primitive", "description": "Row of actions and controls"},
    {
        "name": "FilterBar",
        "category": "primitive",
        "description": "Quick filters above tables/lists",
    },
    {
        "name": "SearchBox",
        "category": "primitive",
        "description": "Single search input with debounce",
    },
    {"name": "MetricTile", "category": "primitive", "description": "Simple KPI metric display"},
    {"name": "MetricRow", "category": "primitive", "description": "Row of KPI metrics"},
    {"name": "SideNav", "category": "primitive", "description": "Sidebar navigation"},
    {"name": "TopNav", "category": "primitive", "description": "Top navigation bar"},
    {
        "name": "Breadcrumbs",
        "category": "primitive",
        "description": "Hierarchical navigation indicator",
    },
]

PATTERN_COMPONENTS = [
    {"name": "FilterableTable", "category": "pattern", "description": "DataTable with FilterBar"},
    {
        "name": "SearchableList",
        "category": "pattern",
        "description": "List with SearchBox and optional FilterBar",
    },
    {
        "name": "MasterDetailLayout",
        "category": "pattern",
        "description": "Master list + detail panel layout",
    },
    {"name": "WizardForm", "category": "pattern", "description": "Multi-step form workflow"},
    {
        "name": "CRUDPage",
        "category": "pattern",
        "description": "Complete CRUD interface for an entity",
    },
    {
        "name": "MetricsDashboard",
        "category": "pattern",
        "description": "Overview page with metrics and charts",
    },
    {
        "name": "SettingsFormPage",
        "category": "pattern",
        "description": "Single-page settings panel",
    },
]

LAYOUT_TYPES = [
    {
        "kind": "singleColumn",
        "description": "Single column layout with main content",
        "regions": ["main"],
    },
    {
        "kind": "twoColumnWithHeader",
        "description": "Two column layout with header",
        "regions": ["header", "main", "secondary"],
    },
    {
        "kind": "appShell",
        "description": "Application shell with sidebar, header, and main content",
        "regions": ["sidebar", "main", "header", "footer"],
    },
    {
        "kind": "custom",
        "description": "Custom layout with arbitrary regions",
        "regions": ["user-defined"],
    },
]


def _list_dnr_components(args: dict[str, Any]) -> str:
    """List DNR UI components."""
    kind = args.get("kind", "all")

    if kind == "primitives":
        components = PRIMITIVE_COMPONENTS
    elif kind == "patterns":
        components = PATTERN_COMPONENTS
    else:
        components = PRIMITIVE_COMPONENTS + PATTERN_COMPONENTS

    # Add any custom components from UISpec
    ui_spec = get_ui_spec()
    if ui_spec:
        custom_components = [
            {
                "name": c.get("name"),
                "category": "custom",
                "description": c.get("description", ""),
            }
            for c in ui_spec.get("components", [])
            if c.get("category") == "custom"
        ]
        if kind in ("all", "custom"):
            components = components + custom_components

    return json.dumps(
        {
            "count": len(components),
            "components": components,
        },
        indent=2,
    )


def _get_dnr_component_spec(args: dict[str, Any]) -> str:
    """Get full ComponentSpec."""
    name = args.get("name")
    if not name:
        return json.dumps({"error": "name parameter required"})

    # Check built-in components
    all_builtins = {c["name"]: c for c in PRIMITIVE_COMPONENTS + PATTERN_COMPONENTS}
    if name in all_builtins:
        return json.dumps(
            {
                "componentSpec": {
                    **all_builtins[name],
                    "props_schema": {"fields": []},  # Would be defined in component implementation
                    "view": None,  # Built-in components have native implementations
                }
            },
            indent=2,
        )

    # Check custom components in UISpec
    ui_spec = get_ui_spec()
    if ui_spec:
        components = ui_spec.get("components", [])
        component = next((c for c in components if c.get("name") == name), None)
        if component:
            return json.dumps({"componentSpec": component}, indent=2)

    return json.dumps(
        {
            "error": f"Component '{name}' not found",
            "available_primitives": [c["name"] for c in PRIMITIVE_COMPONENTS],
            "available_patterns": [c["name"] for c in PATTERN_COMPONENTS],
        }
    )


def _list_workspace_layouts() -> str:
    """List available workspace layouts."""
    return json.dumps(
        {
            "layouts": LAYOUT_TYPES,
        },
        indent=2,
    )


def _create_uispec_component(args: dict[str, Any]) -> str:
    """Create a new ComponentSpec."""
    name = args.get("name")
    description = args.get("description")
    atoms = args.get("atoms", [])

    if not name:
        return json.dumps({"error": "name parameter required"})
    if not description:
        return json.dumps({"error": "description parameter required"})
    if not atoms:
        return json.dumps({"error": "atoms parameter required (list of component names)"})

    # Validate name format (PascalCase)
    if not name[0].isupper():
        return json.dumps({"error": "Component name must be PascalCase"})

    # Validate atoms exist
    all_component_names = {c["name"] for c in PRIMITIVE_COMPONENTS + PATTERN_COMPONENTS}
    invalid_atoms = [a for a in atoms if a not in all_component_names]
    if invalid_atoms:
        return json.dumps(
            {
                "error": f"Unknown component atoms: {invalid_atoms}",
                "available": list(all_component_names),
            }
        )

    # Create component spec
    component_spec = {
        "kind": "component",
        "name": name,
        "description": description,
        "category": "custom",
        "props_schema": {"fields": []},
        "view": {
            "kind": "element",
            "as": atoms[0] if atoms else "Card",
            "children": [{"kind": "element", "as": atom} for atom in atoms[1:]]
            if len(atoms) > 1
            else [],
        },
        "state": [],
        "actions": [],
    }

    # Add to UISpec (or create new spec)
    global _ui_spec
    if _ui_spec is None:
        _ui_spec = {"name": "unnamed", "components": [], "workspaces": [], "themes": []}

    _ui_spec["components"].append(component_spec)

    return json.dumps(
        {
            "status": "created",
            "componentSpec": component_spec,
            "location": f"ui_spec.components[{len(_ui_spec['components']) - 1}]",
        },
        indent=2,
    )


def _patch_uispec_component(args: dict[str, Any]) -> str:
    """Patch an existing ComponentSpec."""
    name = args.get("name")
    patch = args.get("patch", [])

    if not name:
        return json.dumps({"error": "name parameter required"})
    if not patch:
        return json.dumps({"error": "patch parameter required"})

    ui_spec = get_ui_spec()
    if not ui_spec:
        return json.dumps({"error": "No UISpec loaded"})

    components = ui_spec.get("components", [])
    component_idx = next((i for i, c in enumerate(components) if c.get("name") == name), None)

    if component_idx is None:
        return json.dumps(
            {
                "error": f"Component '{name}' not found",
                "available": [c.get("name") for c in components],
            }
        )

    # Apply patches (simplified - real implementation would use jsonpatch)
    component = components[component_idx]
    for op in patch:
        operation = op.get("op")
        path = op.get("path", "").lstrip("/").split("/")
        value = op.get("value")

        if operation == "replace" and len(path) == 1:
            component[path[0]] = value
        elif operation == "add" and len(path) == 1:
            component[path[0]] = value
        elif operation == "remove" and len(path) == 1:
            component.pop(path[0], None)
        # More complex path handling would be needed for nested patches

    return json.dumps(
        {
            "status": "patched",
            "componentSpec": component,
        },
        indent=2,
    )


def _compose_workspace(args: dict[str, Any]) -> str:
    """Create or update a WorkspaceSpec."""
    workspace_name = args.get("workspace_name")
    persona = args.get("persona")
    layout_kind = args.get("layout_kind")
    region_components = args.get("region_components", {})
    routes = args.get("routes", [])

    if not workspace_name:
        return json.dumps({"error": "workspace_name required"})
    if not layout_kind:
        return json.dumps({"error": "layout_kind required"})
    if not region_components:
        return json.dumps({"error": "region_components required"})

    # Validate layout kind
    valid_layouts = {lt["kind"] for lt in LAYOUT_TYPES}
    if layout_kind not in valid_layouts:
        return json.dumps(
            {
                "error": f"Invalid layout_kind: {layout_kind}",
                "valid_layouts": list(valid_layouts),
            }
        )

    # Build layout spec
    if layout_kind == "singleColumn":
        layout = {"kind": "singleColumn", "main": region_components.get("main", "")}
    elif layout_kind == "twoColumnWithHeader":
        layout = {
            "kind": "twoColumnWithHeader",
            "header": region_components.get("header", ""),
            "main": region_components.get("main", ""),
            "secondary": region_components.get("secondary", ""),
        }
    elif layout_kind == "appShell":
        layout = {
            "kind": "appShell",
            "sidebar": region_components.get("sidebar", ""),
            "main": region_components.get("main", ""),
            "header": region_components.get("header"),
            "footer": region_components.get("footer"),
        }
    else:
        layout = {"kind": "custom", "regions": region_components}

    # Create workspace spec
    workspace_spec = {
        "name": workspace_name,
        "persona": persona,
        "layout": layout,
        "routes": routes,
    }

    # Add to UISpec
    global _ui_spec
    if _ui_spec is None:
        _ui_spec = {"name": "unnamed", "components": [], "workspaces": [], "themes": []}

    # Check if workspace already exists
    workspaces = _ui_spec.get("workspaces", [])
    existing_idx = next(
        (i for i, w in enumerate(workspaces) if w.get("name") == workspace_name), None
    )

    if existing_idx is not None:
        workspaces[existing_idx] = workspace_spec
        status = "updated"
    else:
        workspaces.append(workspace_spec)
        status = "created"

    _ui_spec["workspaces"] = workspaces

    return json.dumps(
        {
            "status": status,
            "workspaceSpec": workspace_spec,
        },
        indent=2,
    )


# =============================================================================
# DNR Tool Names
# =============================================================================

DNR_TOOL_NAMES = [
    "list_dnr_entities",
    "get_dnr_entity",
    "list_backend_services",
    "get_backend_service_spec",
    "list_dnr_components",
    "get_dnr_component_spec",
    "list_workspace_layouts",
    "create_uispec_component",
    "patch_uispec_component",
    "compose_workspace",
]
