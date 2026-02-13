"""
Tool definitions for DAZZLE MCP server.

Tools are functions that Claude Code can call to interact with DAZZLE projects.
"""

from typing import Any

try:
    from mcp.types import Tool
except ImportError:
    # MCP SDK not available, use dict fallback
    Tool = None  # type: ignore


def create_tools() -> list[dict[str, Any]]:
    """
    Create available tools for the MCP server.

    Returns:
        List of tool definitions with name, description, and input schema
    """
    return [
        {
            "name": "validate_dsl",
            "description": "Validate DAZZLE DSL files in the current project. Checks syntax, links modules, and reports errors.",
            "inputSchema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "list_modules",
            "description": "List all modules in the DAZZLE project with their dependencies and file locations.",
            "inputSchema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "inspect_entity",
            "description": "Inspect a specific entity definition, showing fields, types, and constraints.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "entity_name": {
                        "type": "string",
                        "description": "Name of the entity to inspect (e.g., 'User', 'Task')",
                    }
                },
                "required": ["entity_name"],
            },
        },
        {
            "name": "inspect_surface",
            "description": "Inspect a surface definition, showing mode, sections, and fields.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "surface_name": {
                        "type": "string",
                        "description": "Name of the surface to inspect",
                    }
                },
                "required": ["surface_name"],
            },
        },
        {
            "name": "build",
            "description": "Build artifacts for specified stacks. Generates code from DSL.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "stacks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of stacks to build. Options: express_micro, openapi, docker, terraform",
                    }
                },
                "required": [],
            },
        },
        {
            "name": "analyze_patterns",
            "description": "Analyze the project for CRUD patterns, integrations, and experiences.",
            "inputSchema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "lint_project",
            "description": "Run extended validation with linting rules (naming conventions, dead modules, etc.).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "strict": {
                        "type": "boolean",
                        "description": "Treat warnings as errors",
                        "default": False,
                    }
                },
                "required": [],
            },
        },
    ]


def get_project_tools() -> list[Any]:
    """
    Get list of project-level MCP tools for setup and status checking.

    Returns:
        List of tool names as strings
    """
    tools = create_tools()
    return [tool["name"] for tool in tools]
