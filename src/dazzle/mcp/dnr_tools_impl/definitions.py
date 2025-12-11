"""
DNR MCP tool definitions.

Contains Tool objects for backend, UI, and GraphQL BFF tools.
"""

from __future__ import annotations

try:
    from mcp.types import Tool
except ImportError:
    Tool = None  # type: ignore


def get_dnr_tools() -> list[Tool]:
    """Get DNR-specific MCP tools."""
    if Tool is None:
        return []

    return [
        # Backend Tools
        Tool(
            name="list_dnr_entities",
            description="List all entities in the DNR BackendSpec with field summaries. BackendSpec is auto-loaded when you select a project or call get_active_project.",
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
        # GraphQL BFF Tools (v0.6)
        Tool(
            name="get_graphql_schema",
            description="Get the auto-generated GraphQL schema (SDL) from BackendSpec entities. Requires strawberry-graphql to be installed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "format": {
                        "type": "string",
                        "enum": ["sdl", "info"],
                        "description": "Output format: 'sdl' for raw schema, 'info' for structured info",
                    }
                },
                "required": [],
            },
        ),
        Tool(
            name="list_graphql_types",
            description="List all GraphQL types generated from BackendSpec entities with their fields.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="list_adapters",
            description="List available external API adapter patterns and their use cases for the BFF layer.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="get_adapter_guide",
            description="Get a guide for implementing an external API adapter with the BFF pattern.",
            inputSchema={
                "type": "object",
                "properties": {
                    "service_type": {
                        "type": "string",
                        "description": "Type of service (hmrc, payment, email, crm, etc.)",
                    }
                },
                "required": [],
            },
        ),
        # v0.9 Channel/Messaging Tools
        Tool(
            name="list_channels",
            description="List all messaging channels configured in the DSL with their resolution status. Shows email, queue, and stream channels with detected providers.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="get_channel_status",
            description="Get detailed status for a specific messaging channel including provider info, health status, and outbox statistics.",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_name": {
                        "type": "string",
                        "description": "Name of the channel to get status for",
                    }
                },
                "required": ["channel_name"],
            },
        ),
        Tool(
            name="list_messages",
            description="List message schemas defined in the DSL with their fields and validation rules.",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_name": {
                        "type": "string",
                        "description": "Optional filter by channel name",
                    }
                },
                "required": [],
            },
        ),
        Tool(
            name="get_outbox_status",
            description="Get outbox statistics showing pending, processing, sent, and failed message counts.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
    ]


# List of DNR tool names for validation
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
    # v0.6 GraphQL BFF tools
    "get_graphql_schema",
    "list_graphql_types",
    "list_adapters",
    "get_adapter_guide",
    # v0.9 Channel/Messaging tools
    "list_channels",
    "get_channel_status",
    "list_messages",
    "get_outbox_status",
]
