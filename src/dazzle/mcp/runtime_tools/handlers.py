"""
the Dazzle runtime MCP tool handlers.

Implementations for backend, UI, and channel tool calls.
"""

import functools
import json
from collections.abc import Callable
from typing import Any

from dazzle.mcp.server.state import get_state

from .components import (
    LAYOUT_TYPES,
    PATTERN_COMPONENTS,
    PRIMITIVE_COMPONENTS,
    get_all_component_names,
    get_component_by_name,
    get_valid_layout_kinds,
)


# Dispatch table built once on first use (see _build_dispatch_table at the bottom of
# this module). `functools.cache` on a parameterless loader replaces the old
# module-scope `global _dispatch_cache` lazy init — no hidden mutable global, and the
# build is thread-safe. The previous module-scope `.update(...)` was an ADR-0005
# violation (import order affected state).
@functools.cache
def _get_dispatch() -> dict[str, Callable[[dict[str, Any]], str]]:
    return _build_dispatch_table()


def handle_runtime_tool(name: str, arguments: dict[str, Any]) -> str:
    """Handle the Dazzle runtime tool calls."""
    handler = _get_dispatch().get(name)
    if handler is None:
        return json.dumps({"error": f"Unknown the Dazzle runtime tool: {name}"})
    try:
        return handler(arguments)
    except Exception as e:
        return json.dumps({"error": str(e)})


# =============================================================================
# Backend Tool Implementations
# =============================================================================


def _list_dnr_entities(_args: dict[str, Any] | None = None) -> str:
    """List all entities from AppSpec."""
    spec = get_state().appspec_data
    if not spec:
        return json.dumps(
            {
                "status": "no_spec",
                "message": "No AppSpec loaded. Select a project first.",
                "entities": [],
            }
        )

    domain = spec.get("domain", {})
    entities = domain.get("entities", [])
    summaries = []
    for entity in entities:
        summaries.append(
            {
                "name": entity.get("name"),
                "label": entity.get("title"),
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

    spec = get_state().appspec_data
    if not spec:
        return json.dumps({"error": "No AppSpec loaded"})

    domain = spec.get("domain", {})
    entities = domain.get("entities", [])
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
    """List surfaces (which drive backend service generation)."""
    entity_filter = args.get("entity_name")

    spec = get_state().appspec_data
    if not spec:
        return json.dumps(
            {
                "status": "no_spec",
                "message": "No AppSpec loaded",
                "surfaces": [],
            }
        )

    surfaces = spec.get("surfaces", [])

    # Apply filter if provided
    if entity_filter:
        surfaces = [s for s in surfaces if s.get("entity_ref") == entity_filter]

    summaries = []
    for surface in surfaces:
        summaries.append(
            {
                "name": surface.get("name"),
                "entity": surface.get("entity_ref"),
                "mode": surface.get("mode"),
                "title": surface.get("title"),
            }
        )

    return json.dumps(
        {
            "count": len(summaries),
            "filter": entity_filter,
            "surfaces": summaries,
        },
        indent=2,
    )


def _get_backend_service_spec(args: dict[str, Any]) -> str:
    """Get full SurfaceSpec (surfaces drive backend service generation)."""
    name = args.get("name")
    if not name:
        return json.dumps({"error": "name parameter required"})

    spec = get_state().appspec_data
    if not spec:
        return json.dumps({"error": "No AppSpec loaded"})

    surfaces = spec.get("surfaces", [])
    surface = next((s for s in surfaces if s.get("name") == name), None)

    if not surface:
        return json.dumps(
            {
                "error": f"Surface '{name}' not found",
                "available": [s.get("name") for s in surfaces],
            }
        )

    return json.dumps({"surfaceSpec": surface}, indent=2)


# =============================================================================
# UI Tool Implementations
# =============================================================================


def _list_dnr_components(args: dict[str, Any]) -> str:
    """List Dazzle UI runtime components."""
    kind = args.get("kind", "all")

    if kind == "primitives":
        components = list(PRIMITIVE_COMPONENTS)
    elif kind == "patterns":
        components = list(PATTERN_COMPONENTS)
    else:
        components = list(PRIMITIVE_COMPONENTS) + list(PATTERN_COMPONENTS)

    # Add any custom components from UISpec
    ui_spec = get_state().ui_spec
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
    ui_spec = get_state().ui_spec
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


def _list_workspace_layouts(_args: dict[str, Any] | None = None) -> str:
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
    ui_spec = get_state().get_or_create_ui_spec()
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

    ui_spec = get_state().ui_spec
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
    ui_spec = get_state().get_or_create_ui_spec()

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
# Channel/Messaging Tool Implementations (v0.9)
# =============================================================================


def _list_channels(_args: dict[str, Any] | None = None) -> str:
    """List all messaging channels from AppSpec."""
    spec = get_state().appspec_data
    if not spec:
        return json.dumps(
            {
                "status": "no_spec",
                "message": "No AppSpec loaded. Select a project first.",
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

    spec = get_state().appspec_data
    if not spec:
        return json.dumps({"error": "No AppSpec loaded. Select a project first."})

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

        # Check if dazzle.http.channels is available
        if importlib.util.find_spec("dazzle.http.channels"):
            # Note: In real usage, this would connect to the running the Dazzle runtime server
            # For now, return the DSL spec with a note about runtime status
            runtime_status = {"note": "Start the Dazzle runtime server for live status"}
        else:
            runtime_status = {"note": "Dazzle backend not installed"}
    except Exception:
        runtime_status = {"note": "Could not check the Dazzle runtime backend availability"}

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
    """List message schemas from AppSpec."""
    spec = get_state().appspec_data
    if not spec:
        return json.dumps(
            {
                "status": "no_spec",
                "message": "No AppSpec loaded. Select a project first.",
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


def _get_outbox_status(_args: dict[str, Any] | None = None) -> str:
    """Get outbox statistics."""
    spec = get_state().appspec_data
    if not spec:
        return json.dumps(
            {
                "status": "no_spec",
                "message": "No AppSpec loaded. Select a project first.",
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

    # Note: Real implementation would connect to running the Dazzle runtime server
    # For now, return a helpful message about how to get live stats
    return json.dumps(
        {
            "status": "info",
            "message": "Outbox statistics require a running the Dazzle runtime server.",
            "hint": "Start the server with 'dazzle serve' then query the /_dazzle/channels endpoint.",
            "channels_defined": len(channels),
            "channel_names": [c.get("name") for c in channels],
        },
        indent=2,
    )


# =============================================================================
# Dispatch Table
# =============================================================================


def _build_dispatch_table() -> dict[str, Callable[[dict[str, Any]], str]]:
    return {
        # Backend tools
        "list_dnr_entities": _list_dnr_entities,
        "get_dnr_entity": _get_dnr_entity,
        "list_backend_services": _list_backend_services,
        "get_backend_service_spec": _get_backend_service_spec,
        # UI tools
        "list_dnr_components": _list_dnr_components,
        "get_dnr_component_spec": _get_dnr_component_spec,
        "list_workspace_layouts": _list_workspace_layouts,
        "create_uispec_component": _create_uispec_component,
        "patch_uispec_component": _patch_uispec_component,
        "compose_workspace": _compose_workspace,
        # Channel/Messaging tools (v0.9)
        "list_channels": _list_channels,
        "get_channel_status": _get_channel_status,
        "list_messages": _list_messages,
        "get_outbox_status": _get_outbox_status,
    }
