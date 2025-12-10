"""
MCP Server tool definitions.

This module contains the tool schema definitions for the MCP server.
"""

from __future__ import annotations

from mcp.types import Tool

from .state import is_dev_mode


def get_dev_mode_tools() -> list[Tool]:
    """Get tools specific to dev mode."""
    return [
        Tool(
            name="list_projects",
            description="List all available example projects in the Dazzle dev environment",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="select_project",
            description="Select an example project to work with",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "Name of the example project to select",
                    }
                },
                "required": ["project_name"],
            },
        ),
        Tool(
            name="get_active_project",
            description="Get the currently selected project",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="validate_all_projects",
            description="Validate all example projects at once",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
    ]


def get_project_tools() -> list[Tool]:
    """Get tools that operate on a project."""
    return [
        Tool(
            name="validate_dsl",
            description="Validate all DSL files in the DAZZLE project",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="list_modules",
            description="List all modules in the DAZZLE project",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="inspect_entity",
            description="Inspect a specific entity definition",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_name": {
                        "type": "string",
                        "description": "Name of the entity to inspect",
                    }
                },
                "required": ["entity_name"],
            },
        ),
        Tool(
            name="inspect_surface",
            description="Inspect a specific surface definition",
            inputSchema={
                "type": "object",
                "properties": {
                    "surface_name": {
                        "type": "string",
                        "description": "Name of the surface to inspect",
                    }
                },
                "required": ["surface_name"],
            },
        ),
        Tool(
            name="analyze_patterns",
            description="Analyze the project for CRUD and integration patterns",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="lint_project",
            description="Run linting on the DAZZLE project",
            inputSchema={
                "type": "object",
                "properties": {
                    "extended": {
                        "type": "boolean",
                        "description": "Run extended checks",
                    }
                },
                "required": [],
            },
        ),
        Tool(
            name="lookup_concept",
            description="Look up DAZZLE DSL v0.2 concepts OR patterns by name. Returns definition, syntax, examples, and copy-paste code. Use 'patterns' to list all available patterns (crud, dashboard, role_based_access, kanban_board, etc.).",
            inputSchema={
                "type": "object",
                "properties": {
                    "term": {
                        "type": "string",
                        "description": "DSL concept or pattern to look up (e.g., 'persona', 'workspace', 'crud', 'dashboard', 'patterns')",
                    }
                },
                "required": ["term"],
            },
        ),
        Tool(
            name="find_examples",
            description="Find example projects demonstrating specific DSL features. Useful for learning how to use v0.2 features like personas, workspaces, attention signals, etc.",
            inputSchema={
                "type": "object",
                "properties": {
                    "features": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of features to search for (e.g., ['persona', 'workspace'])",
                    },
                    "complexity": {
                        "type": "string",
                        "description": "Complexity level: 'beginner', 'intermediate', or 'advanced'",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="get_cli_help",
            description="Get help for dazzle CLI commands. Use this when the user asks how to run, build, test, or deploy a DAZZLE app. Returns command syntax, options, and examples.",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "CLI command to get help for (e.g., 'dnr serve', 'test run', 'init'). Omit for overview.",
                    }
                },
                "required": [],
            },
        ),
        Tool(
            name="get_workflow_guide",
            description="Get step-by-step guide for common DAZZLE workflows. Use 'getting_started' for new users. Each workflow includes complete code examples.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workflow": {
                        "type": "string",
                        "description": "Workflow name: 'getting_started', 'new_project', 'add_entity', 'add_workspace', 'add_personas', 'add_relationships', 'add_attention_signals', 'setup_testing', or 'troubleshoot'",
                    }
                },
                "required": ["workflow"],
            },
        ),
    ]


def get_all_tools() -> list[Tool]:
    """Get all available tools based on current mode."""
    from dazzle.mcp.dnr_tools_impl import get_dnr_tools

    tools = []

    # Add dev mode tools if in dev mode
    if is_dev_mode():
        tools.extend(get_dev_mode_tools())

    # Add project tools (always available)
    tools.extend(get_project_tools())

    # Add DNR tools (always available)
    tools.extend(get_dnr_tools())

    return tools
