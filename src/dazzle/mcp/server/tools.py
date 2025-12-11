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


# Common schema for project_path parameter - allows agents to specify which project to operate on
PROJECT_PATH_SCHEMA = {
    "project_path": {
        "type": "string",
        "description": "Optional: Absolute path to the project directory. If omitted, uses the active project in dev mode or the MCP server's working directory.",
    }
}


def get_project_tools() -> list[Tool]:
    """Get tools that operate on a project."""
    return [
        Tool(
            name="validate_dsl",
            description="Validate all DSL files in a DAZZLE project. Pass project_path if you're working on a project outside the Dazzle examples directory.",
            inputSchema={
                "type": "object",
                "properties": {**PROJECT_PATH_SCHEMA},
                "required": [],
            },
        ),
        Tool(
            name="list_modules",
            description="List all modules in a DAZZLE project. Pass project_path if you're working on a project outside the Dazzle examples directory.",
            inputSchema={
                "type": "object",
                "properties": {**PROJECT_PATH_SCHEMA},
                "required": [],
            },
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
                    },
                    **PROJECT_PATH_SCHEMA,
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
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": ["surface_name"],
            },
        ),
        Tool(
            name="analyze_patterns",
            description="Analyze a project for CRUD and integration patterns. Pass project_path if you're working on a project outside the Dazzle examples directory.",
            inputSchema={
                "type": "object",
                "properties": {**PROJECT_PATH_SCHEMA},
                "required": [],
            },
        ),
        Tool(
            name="lint_project",
            description="Run linting on a DAZZLE project. Pass project_path if you're working on a project outside the Dazzle examples directory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "extended": {
                        "type": "boolean",
                        "description": "Run extended checks",
                    },
                    **PROJECT_PATH_SCHEMA,
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
        Tool(
            name="lookup_inference",
            description="Search for DSL generation hints from SPEC keywords. Returns compact suggestions: fields to add, archetypes to apply, syntax mappings. Use when converting SPEC to DSL.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keywords from SPEC (e.g., 'photo upload', 'created by', 'tester person', 'status fixed')",
                    },
                    "detail": {
                        "type": "string",
                        "enum": ["minimal", "full"],
                        "description": "minimal (default): just suggestions. full: include code examples",
                    },
                    "list_all": {
                        "type": "boolean",
                        "description": "List available trigger keywords instead of searching",
                    },
                },
                "required": [],
            },
        ),
    ]


def get_api_kb_tools() -> list[Tool]:
    """Get API Knowledgebase tools for integration assistance."""
    return [
        Tool(
            name="list_api_packs",
            description="List all available API packs in the knowledgebase. Returns pack names, providers, categories, and descriptions.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="search_api_packs",
            description="Search for API packs by category, provider, or text query. Use to find integrations for payments, accounting, tax, etc.",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Filter by category (e.g., 'payments', 'tax', 'accounting', 'business_data')",
                    },
                    "provider": {
                        "type": "string",
                        "description": "Filter by provider name (e.g., 'Stripe', 'HMRC', 'Xero')",
                    },
                    "query": {
                        "type": "string",
                        "description": "Text search in name, provider, or description",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="get_api_pack",
            description="Get full details of an API pack including auth config, env vars, operations, and foreign models.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pack_name": {
                        "type": "string",
                        "description": "Pack name (e.g., 'stripe_payments', 'hmrc_mtd_vat')",
                    }
                },
                "required": ["pack_name"],
            },
        ),
        Tool(
            name="generate_service_dsl",
            description="Generate DSL service and foreign_model blocks from an API pack. Copy-paste ready code.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pack_name": {
                        "type": "string",
                        "description": "Pack name to generate DSL for",
                    }
                },
                "required": ["pack_name"],
            },
        ),
        Tool(
            name="get_env_vars_for_packs",
            description="Get .env.example content for specified packs or all packs. Use when setting up a new project.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pack_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of pack names. Omit for all packs.",
                    }
                },
                "required": [],
            },
        ),
    ]


def get_internal_tools() -> list[Tool]:
    """Get internal/development tools for MCP management."""
    return [
        Tool(
            name="get_mcp_status",
            description="Get MCP server status including semantic index version. Use to verify the server is using the latest code. In dev mode, can reload modules.",
            inputSchema={
                "type": "object",
                "properties": {
                    "reload": {
                        "type": "boolean",
                        "description": "If true, reload the semantics module to pick up code changes (dev mode only)",
                    }
                },
                "required": [],
            },
        ),
        Tool(
            name="get_dnr_logs",
            description="""Get DNR runtime logs for debugging. Dazzle apps write logs to .dazzle/logs/dnr.log in JSONL format.

LOG FILE LOCATION: {project_dir}/.dazzle/logs/dnr.log

Each line is a complete JSON object with fields:
- timestamp: ISO 8601 format
- level: DEBUG, INFO, WARNING, ERROR
- component: API, UI, Bar, DNR
- message: The log message
- context: Additional structured data (optional)

Use this tool to:
- Monitor the running app for errors
- Debug frontend/backend issues
- Get error summaries for diagnosis

The logs are designed for LLM agent consumption - you can tail the log file directly or use this tool.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "Number of recent log entries to return (default: 50)",
                    },
                    "level": {
                        "type": "string",
                        "enum": ["DEBUG", "INFO", "WARNING", "ERROR"],
                        "description": "Filter by log level (optional)",
                    },
                    "errors_only": {
                        "type": "boolean",
                        "description": "If true, return error summary instead of recent logs",
                    },
                },
                "required": [],
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

    # Add API Knowledgebase tools (always available)
    tools.extend(get_api_kb_tools())

    # Add internal tools (always available, but some features dev-only)
    tools.extend(get_internal_tools())

    return tools
