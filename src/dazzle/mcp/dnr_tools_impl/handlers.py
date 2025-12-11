"""
DNR MCP tool handlers.

Implementations for backend, UI, and GraphQL BFF tool calls.
"""

from __future__ import annotations

import json
from typing import Any

from .components import (
    LAYOUT_TYPES,
    PATTERN_COMPONENTS,
    PRIMITIVE_COMPONENTS,
    get_all_component_names,
    get_component_by_name,
    get_valid_layout_kinds,
)
from .state import get_backend_spec, get_or_create_ui_spec, get_ui_spec


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

    # GraphQL BFF tools (v0.6)
    elif name == "get_graphql_schema":
        return _get_graphql_schema(arguments)
    elif name == "list_graphql_types":
        return _list_graphql_types()
    elif name == "list_adapters":
        return _list_adapters()
    elif name == "get_adapter_guide":
        return _get_adapter_guide(arguments)

    # Channel/Messaging tools (v0.9)
    elif name == "list_channels":
        return _list_channels()
    elif name == "get_channel_status":
        return _get_channel_status(arguments)
    elif name == "list_messages":
        return _list_messages(arguments)
    elif name == "get_outbox_status":
        return _get_outbox_status()

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


def _list_dnr_components(args: dict[str, Any]) -> str:
    """List DNR UI components."""
    kind = args.get("kind", "all")

    if kind == "primitives":
        components = list(PRIMITIVE_COMPONENTS)
    elif kind == "patterns":
        components = list(PATTERN_COMPONENTS)
    else:
        components = list(PRIMITIVE_COMPONENTS) + list(PATTERN_COMPONENTS)

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
    builtin = get_component_by_name(name)
    if builtin:
        return json.dumps(
            {
                "componentSpec": {
                    **builtin,
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
    all_component_names = get_all_component_names()
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

    # Add to UISpec
    ui_spec = get_or_create_ui_spec()
    ui_spec["components"].append(component_spec)

    return json.dumps(
        {
            "status": "created",
            "componentSpec": component_spec,
            "location": f"ui_spec.components[{len(ui_spec['components']) - 1}]",
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
    valid_layouts = get_valid_layout_kinds()
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
    ui_spec = get_or_create_ui_spec()

    # Check if workspace already exists
    workspaces = ui_spec.get("workspaces", [])
    existing_idx = next(
        (i for i, w in enumerate(workspaces) if w.get("name") == workspace_name), None
    )

    if existing_idx is not None:
        workspaces[existing_idx] = workspace_spec
        status = "updated"
    else:
        workspaces.append(workspace_spec)
        status = "created"

    ui_spec["workspaces"] = workspaces

    return json.dumps(
        {
            "status": status,
            "workspaceSpec": workspace_spec,
        },
        indent=2,
    )


# =============================================================================
# GraphQL BFF Tool Implementations (v0.6)
# =============================================================================


def _get_graphql_schema(args: dict[str, Any]) -> str:
    """Get the GraphQL schema from BackendSpec."""
    spec = get_backend_spec()
    if not spec:
        return json.dumps(
            {
                "status": "no_spec",
                "message": "No BackendSpec loaded. Select a project first.",
            }
        )

    output_format = args.get("format", "sdl")

    # Try to import GraphQL support
    try:
        from dazzle_dnr_back.graphql.integration import inspect_schema, print_schema
        from dazzle_dnr_back.specs import BackendSpec

        # Convert dict to BackendSpec if needed
        if isinstance(spec, dict):
            backend_spec = BackendSpec.model_validate(spec)
        else:
            backend_spec = spec

        if output_format == "info":
            info = inspect_schema(backend_spec)
            return json.dumps(info, indent=2)
        else:
            sdl = print_schema(backend_spec)
            return json.dumps(
                {
                    "status": "success",
                    "format": "sdl",
                    "schema": sdl,
                },
                indent=2,
            )
    except ImportError:
        return json.dumps(
            {
                "status": "unavailable",
                "message": "GraphQL support not available. Install with: pip install strawberry-graphql",
            }
        )


def _list_graphql_types() -> str:
    """List GraphQL types from BackendSpec entities."""
    spec = get_backend_spec()
    if not spec:
        return json.dumps(
            {
                "status": "no_spec",
                "message": "No BackendSpec loaded. Select a project first.",
                "types": [],
            }
        )

    entities = spec.get("entities", [])
    types = []

    for entity in entities:
        entity_name = entity.get("name", "Unknown")
        fields = entity.get("fields", [])

        # Map entity fields to GraphQL fields
        graphql_fields = []
        for field in fields:
            field_name = field.get("name", "")
            field_type = field.get("type", "String")
            is_required = field.get("required", False) or field.get("pk", False)

            # Map DAZZLE types to GraphQL
            graphql_type = _map_to_graphql_type(field_type)
            if is_required:
                graphql_type += "!"

            graphql_fields.append({"name": field_name, "type": graphql_type})

        types.append(
            {
                "name": entity_name,
                "kind": "OBJECT",
                "fields": graphql_fields,
                "hasQuery": True,
                "hasMutation": True,
            }
        )

        # Add input type
        types.append(
            {
                "name": f"{entity_name}Input",
                "kind": "INPUT_OBJECT",
                "fields": [f for f in graphql_fields if f["name"] != "id"],
            }
        )

    return json.dumps(
        {
            "status": "success",
            "types": types,
            "hint": "Use get_graphql_schema for full SDL",
        },
        indent=2,
    )


def _map_to_graphql_type(dazzle_type: str) -> str:
    """Map DAZZLE field types to GraphQL types."""
    type_lower = dazzle_type.lower()
    if type_lower.startswith("uuid"):
        return "ID"
    elif type_lower.startswith("str"):
        return "String"
    elif type_lower.startswith("int"):
        return "Int"
    elif type_lower.startswith("float") or type_lower.startswith("decimal"):
        return "Float"
    elif type_lower.startswith("bool"):
        return "Boolean"
    elif type_lower.startswith("datetime"):
        return "DateTime"
    elif type_lower.startswith("date"):
        return "Date"
    elif type_lower.startswith("json"):
        return "JSON"
    elif type_lower.startswith("enum"):
        return "String"  # Enums are strings in simplified mapping
    else:
        return "String"


def _list_adapters() -> str:
    """List available adapter patterns for BFF layer."""
    from .adapter_examples import ADAPTERS, SERVICE_PATTERNS

    return json.dumps(
        {
            "status": "success",
            "adapters": ADAPTERS,
            "service_patterns": SERVICE_PATTERNS,
            "hint": "Use get_adapter_guide with service_type for implementation details",
        },
        indent=2,
    )


def _get_adapter_guide(args: dict[str, Any]) -> str:
    """Get implementation guide for a specific adapter type."""
    from .adapter_examples import ADAPTER_GUIDES

    service_type = args.get("service_type", "generic")
    guide = ADAPTER_GUIDES.get(service_type.lower(), ADAPTER_GUIDES["generic"])

    return json.dumps(
        {
            "status": "success",
            "service_type": service_type,
            "guide": guide,
        },
        indent=2,
    )


# =============================================================================
# Channel/Messaging Tool Implementations (v0.9)
# =============================================================================


def _list_channels() -> str:
    """List all messaging channels from BackendSpec."""
    spec = get_backend_spec()
    if not spec:
        return json.dumps(
            {
                "status": "no_spec",
                "message": "No BackendSpec loaded. Select a project first.",
                "channels": [],
            }
        )

    channels = spec.get("channels", [])
    if not channels:
        return json.dumps(
            {
                "status": "no_channels",
                "message": "No channels defined in DSL. Use 'channel' construct to define messaging channels.",
                "channels": [],
                "hint": "Example: channel notifications email provider=auto",
            }
        )

    summaries = []
    for channel in channels:
        summaries.append(
            {
                "name": channel.get("name"),
                "kind": channel.get("kind"),
                "provider": channel.get("provider", "auto"),
                "send_operations": len(channel.get("send_operations", [])),
                "receive_operations": len(channel.get("receive_operations", [])),
            }
        )

    return json.dumps(
        {
            "status": "success",
            "count": len(summaries),
            "channels": summaries,
        },
        indent=2,
    )


def _get_channel_status(args: dict[str, Any]) -> str:
    """Get detailed status for a specific channel."""
    channel_name = args.get("channel_name")
    if not channel_name:
        return json.dumps({"error": "channel_name parameter required"})

    spec = get_backend_spec()
    if not spec:
        return json.dumps({"error": "No BackendSpec loaded. Select a project first."})

    channels = spec.get("channels", [])
    channel = next((c for c in channels if c.get("name") == channel_name), None)

    if not channel:
        return json.dumps(
            {
                "error": f"Channel '{channel_name}' not found",
                "available": [c.get("name") for c in channels],
            }
        )

    # Get runtime status if available
    runtime_status = None
    try:
        import importlib.util

        # Check if dazzle_dnr_back.channels is available
        if importlib.util.find_spec("dazzle_dnr_back.channels"):
            # Note: In real usage, this would connect to the running DNR server
            # For now, return the DSL spec with a note about runtime status
            runtime_status = {"note": "Start DNR server for live status"}
        else:
            runtime_status = {"note": "DNR backend not installed"}
    except Exception:
        runtime_status = {"note": "Could not check DNR backend availability"}

    return json.dumps(
        {
            "status": "success",
            "channel": {
                "name": channel.get("name"),
                "kind": channel.get("kind"),
                "provider": channel.get("provider", "auto"),
                "connection_url": channel.get("connection_url"),
                "send_operations": channel.get("send_operations", []),
                "receive_operations": channel.get("receive_operations", []),
                "config": channel.get("config", {}),
            },
            "runtime": runtime_status,
        },
        indent=2,
    )


def _list_messages(args: dict[str, Any]) -> str:
    """List message schemas from BackendSpec."""
    spec = get_backend_spec()
    if not spec:
        return json.dumps(
            {
                "status": "no_spec",
                "message": "No BackendSpec loaded. Select a project first.",
                "messages": [],
            }
        )

    channel_filter = args.get("channel_name")
    messages = spec.get("messages", [])

    if channel_filter:
        # Filter messages by channel (if they reference a channel)
        messages = [m for m in messages if m.get("channel") == channel_filter]

    if not messages:
        hint = "No messages defined in DSL."
        if channel_filter:
            hint = f"No messages found for channel '{channel_filter}'."
        return json.dumps(
            {
                "status": "no_messages",
                "message": hint,
                "messages": [],
                "hint": "Use 'message' construct to define typed message schemas.",
            }
        )

    summaries = []
    for msg in messages:
        summaries.append(
            {
                "name": msg.get("name"),
                "description": msg.get("description"),
                "field_count": len(msg.get("fields", [])),
                "channel": msg.get("channel"),
            }
        )

    return json.dumps(
        {
            "status": "success",
            "count": len(summaries),
            "filter": channel_filter,
            "messages": summaries,
        },
        indent=2,
    )


def _get_outbox_status() -> str:
    """Get outbox statistics."""
    spec = get_backend_spec()
    if not spec:
        return json.dumps(
            {
                "status": "no_spec",
                "message": "No BackendSpec loaded. Select a project first.",
            }
        )

    # Check if any channels are defined
    channels = spec.get("channels", [])
    if not channels:
        return json.dumps(
            {
                "status": "no_channels",
                "message": "No channels defined - outbox not in use.",
            }
        )

    # Note: Real implementation would connect to running DNR server
    # For now, return a helpful message about how to get live stats
    return json.dumps(
        {
            "status": "info",
            "message": "Outbox statistics require a running DNR server.",
            "hint": "Start the server with 'dazzle dnr serve' then query the /_dazzle/channels endpoint.",
            "channels_defined": len(channels),
            "channel_names": [c.get("name") for c in channels],
        },
        indent=2,
    )
