"""
Consolidated MCP Server tool definitions.

This module reduces token budget by consolidating related tools into single
tools with enum-based operations. Each operation is explicitly listed in the
schema, preserving discoverability for LLMs.

Consolidation strategy:
- 66 original tools → 17 consolidated tools
- Knowledge tools (5) → MCP Resources (no schema overhead)
- CRUD patterns unified: list/get/inspect → single tool with operation enum

Token savings: ~40-50% reduction in tool schema overhead.
"""

from __future__ import annotations

from mcp.types import Tool

from .state import is_dev_mode


def get_dev_mode_tools() -> list[Tool]:
    """Get tools specific to dev mode (unchanged - 4 tools)."""
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


# Common schema for project_path parameter
PROJECT_PATH_SCHEMA = {
    "project_path": {
        "type": "string",
        "description": "Optional: Absolute path to project directory. If omitted, uses active project.",
    }
}


def get_consolidated_tools() -> list[Tool]:
    """
    Get consolidated tools (13 tools replacing 62 original tools).

    Each tool uses an 'operation' enum to specify the action, preserving
    discoverability while reducing schema overhead.
    """
    return [
        # =====================================================================
        # DSL Operations (replaces 7 tools)
        # =====================================================================
        Tool(
            name="dsl",
            description="DSL operations: validate, list_modules, inspect_entity, inspect_surface, analyze, lint, get_spec",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": [
                            "validate",
                            "list_modules",
                            "inspect_entity",
                            "inspect_surface",
                            "analyze",
                            "lint",
                            "get_spec",
                        ],
                        "description": "Operation to perform",
                    },
                    "name": {
                        "type": "string",
                        "description": "Entity or surface name (for inspect_entity/inspect_surface)",
                    },
                    "extended": {
                        "type": "boolean",
                        "description": "Run extended checks (for lint)",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": ["operation"],
            },
        ),
        # =====================================================================
        # API Packs (replaces 5 tools)
        # =====================================================================
        Tool(
            name="api_pack",
            description="API pack operations: list, search, get, generate_dsl, env_vars",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["list", "search", "get", "generate_dsl", "env_vars"],
                        "description": "Operation to perform",
                    },
                    "pack_name": {
                        "type": "string",
                        "description": "Pack name (for get, generate_dsl)",
                    },
                    "pack_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Pack names (for env_vars)",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query (for search)",
                    },
                    "category": {
                        "type": "string",
                        "description": "Filter by category (for search)",
                    },
                    "provider": {
                        "type": "string",
                        "description": "Filter by provider (for search)",
                    },
                },
                "required": ["operation"],
            },
        ),
        # =====================================================================
        # Stories (replaces 6 tools)
        # =====================================================================
        Tool(
            name="story",
            description="Story operations: propose, save, get, generate_stubs, generate_tests, coverage",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": [
                            "propose",
                            "save",
                            "get",
                            "generate_stubs",
                            "generate_tests",
                            "coverage",
                        ],
                        "description": "Operation to perform",
                    },
                    "entities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by entities (for propose)",
                    },
                    "max_stories": {
                        "type": "integer",
                        "description": "Max stories to propose (default: 30)",
                    },
                    "stories": {
                        "type": "array",
                        "description": "Stories to save (for save)",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "Overwrite existing (for save)",
                    },
                    "status_filter": {
                        "type": "string",
                        "enum": ["all", "accepted", "rejected", "draft"],
                        "description": "Filter by status (for get)",
                    },
                    "story_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Story IDs (for generate_stubs, generate_tests)",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Output directory (for generate_stubs)",
                    },
                    "include_draft": {
                        "type": "boolean",
                        "description": "Include draft stories (for generate_tests)",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": ["operation"],
            },
        ),
        # =====================================================================
        # Demo Data (replaces 4 tools)
        # =====================================================================
        Tool(
            name="demo_data",
            description="Demo data operations: propose, save, get, generate",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["propose", "save", "get", "generate"],
                        "description": "Operation to perform",
                    },
                    "domain_description": {
                        "type": "string",
                        "description": "Domain description (for propose)",
                    },
                    "entities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific entities (for propose, generate)",
                    },
                    "tenant_count": {
                        "type": "integer",
                        "description": "Number of tenants (for propose)",
                    },
                    "quick_mode": {
                        "type": "boolean",
                        "description": "Quick mode (for propose)",
                    },
                    "blueprint": {
                        "type": "object",
                        "description": "Blueprint to save (for save)",
                    },
                    "merge": {
                        "type": "boolean",
                        "description": "Merge with existing (for save)",
                    },
                    "validate": {
                        "type": "boolean",
                        "description": "Validate blueprint (for save)",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["csv", "jsonl"],
                        "description": "Output format (for generate)",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Output directory (for generate)",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": ["operation"],
            },
        ),
        # =====================================================================
        # Test Design (replaces 7 tools + 2 new autonomous operations)
        # =====================================================================
        Tool(
            name="test_design",
            description="Test design operations: propose_persona, gaps, save, get, coverage_actions, runtime_gaps, save_runtime, auto_populate, improve_coverage",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": [
                            "propose_persona",
                            "gaps",
                            "save",
                            "get",
                            "coverage_actions",
                            "runtime_gaps",
                            "save_runtime",
                            "auto_populate",
                            "improve_coverage",
                        ],
                        "description": "Operation to perform",
                    },
                    "persona": {
                        "type": "string",
                        "description": "Persona name (for propose_persona)",
                    },
                    "max_tests": {
                        "type": "integer",
                        "description": "Max tests (for propose_persona)",
                    },
                    "designs": {
                        "type": "array",
                        "description": "Test designs (for save)",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "Overwrite existing (for save)",
                    },
                    "to_dsl": {
                        "type": "boolean",
                        "description": "Save to dsl/ (for save)",
                    },
                    "status_filter": {
                        "type": "string",
                        "enum": [
                            "all",
                            "proposed",
                            "accepted",
                            "implemented",
                            "verified",
                            "rejected",
                        ],
                        "description": "Filter by status (for get)",
                    },
                    "focus": {
                        "type": "string",
                        "enum": ["all", "personas", "entities", "state_machines", "scenarios"],
                        "description": "Focus area (for coverage_actions)",
                    },
                    "max_actions": {
                        "type": "integer",
                        "description": "Max actions (for coverage_actions, runtime_gaps, improve_coverage)",
                    },
                    "max_stories": {
                        "type": "integer",
                        "description": "Max stories to propose (for auto_populate, default: 30)",
                    },
                    "include_test_designs": {
                        "type": "boolean",
                        "description": "Generate test designs from stories (for auto_populate, default: true)",
                    },
                    "coverage_report_path": {
                        "type": "string",
                        "description": "Coverage report path (for runtime_gaps)",
                    },
                    "coverage_data": {
                        "type": "object",
                        "description": "Coverage data (for save_runtime)",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": ["operation"],
            },
        ),
        # =====================================================================
        # SiteSpec (replaces 3 tools)
        # =====================================================================
        Tool(
            name="sitespec",
            description="SiteSpec operations: get, validate, scaffold",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["get", "validate", "scaffold"],
                        "description": "Operation to perform",
                    },
                    "use_defaults": {
                        "type": "boolean",
                        "description": "Use defaults when missing (for get)",
                    },
                    "check_content_files": {
                        "type": "boolean",
                        "description": "Check content files (for validate)",
                    },
                    "product_name": {
                        "type": "string",
                        "description": "Product name (for scaffold)",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "Overwrite existing (for scaffold)",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": ["operation"],
            },
        ),
        # =====================================================================
        # Semantics (replaces 5 tools)
        # =====================================================================
        Tool(
            name="semantics",
            description="Semantic analysis: extract, validate_events, tenancy, compliance, analytics",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": [
                            "extract",
                            "validate_events",
                            "tenancy",
                            "compliance",
                            "analytics",
                        ],
                        "description": "Operation to perform",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": ["operation"],
            },
        ),
        # =====================================================================
        # Feedback (replaces 2 tools)
        # =====================================================================
        Tool(
            name="feedback",
            description="Feedback operations: add, list",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["add", "list"],
                        "description": "Operation to perform",
                    },
                    # For add
                    "pain_point": {
                        "type": "string",
                        "description": "Pain point (for add)",
                    },
                    "expected": {
                        "type": "string",
                        "description": "Expected behavior (for add)",
                    },
                    "observed": {
                        "type": "string",
                        "description": "Observed behavior (for add)",
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "high", "medium", "low"],
                        "description": "Severity (for add, list filter)",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["global", "module", "entity", "field", "surface"],
                        "description": "Scope (for add, list filter)",
                    },
                    "hypothesis": {
                        "type": "string",
                        "description": "Hypothesis (for add)",
                    },
                    "location": {
                        "type": "string",
                        "description": "Location in DSL (for add)",
                    },
                    "resolved": {
                        "type": "boolean",
                        "description": "Filter by resolved (for list)",
                    },
                },
                "required": ["operation"],
            },
        ),
        # =====================================================================
        # Processes (replaces 7 tools)
        # =====================================================================
        Tool(
            name="process",
            description="Process operations: propose, list, inspect, list_runs, get_run, diagram, coverage",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": [
                            "propose",
                            "list",
                            "inspect",
                            "list_runs",
                            "get_run",
                            "diagram",
                            "coverage",
                        ],
                        "description": "Operation to perform",
                    },
                    "process_name": {
                        "type": "string",
                        "description": "Process name (for inspect, diagram)",
                    },
                    "story_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Story IDs (for propose)",
                    },
                    "run_id": {
                        "type": "string",
                        "description": "Run ID (for get_run)",
                    },
                    "status": {
                        "type": "string",
                        "enum": [
                            "pending",
                            "running",
                            "draining",
                            "suspended",
                            "waiting",
                            "completed",
                            "failed",
                            "compensating",
                            "cancelled",
                        ],
                        "description": "Filter by status (for list_runs)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (for list_runs)",
                    },
                    "type": {
                        "type": "string",
                        "enum": ["flowchart", "stateDiagram"],
                        "description": "Diagram type (for diagram)",
                    },
                    "include_compensations": {
                        "type": "boolean",
                        "description": "Include compensations (for diagram)",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": ["operation"],
            },
        ),
        # =====================================================================
        # DSL Tests (replaces 4 tools)
        # =====================================================================
        Tool(
            name="dsl_test",
            description="DSL test operations: generate, run, coverage, list",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["generate", "run", "coverage", "list"],
                        "description": "Operation to perform",
                    },
                    "save": {
                        "type": "boolean",
                        "description": "Save generated tests (for generate)",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["json", "yaml"],
                        "description": "Output format (for generate)",
                    },
                    "base_url": {
                        "type": "string",
                        "description": "Server URL (for run)",
                    },
                    "entity": {
                        "type": "string",
                        "description": "Filter by entity (for run, list)",
                    },
                    "category": {
                        "type": "string",
                        "description": "Filter by category (for run, list)",
                    },
                    "test_id": {
                        "type": "string",
                        "description": "Specific test ID (for run)",
                    },
                    "regenerate": {
                        "type": "boolean",
                        "description": "Regenerate before run (for run)",
                    },
                    "detailed": {
                        "type": "boolean",
                        "description": "Detailed output (for coverage)",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": ["operation"],
            },
        ),
        # =====================================================================
        # E2E Tests (replaces 5 tools)
        # =====================================================================
        Tool(
            name="e2e_test",
            description="E2E test operations: check_infra, run, run_agent, coverage, list_flows, tier_guidance",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": [
                            "check_infra",
                            "run",
                            "run_agent",
                            "coverage",
                            "list_flows",
                            "tier_guidance",
                        ],
                        "description": "Operation to perform",
                    },
                    "headless": {
                        "type": "boolean",
                        "description": "Headless mode (for run, run_agent)",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "Filter by priority (for run, list_flows)",
                    },
                    "tag": {
                        "type": "string",
                        "description": "Filter by tag (for run, list_flows)",
                    },
                    "test_id": {
                        "type": "string",
                        "description": "Specific test ID (for run_agent)",
                    },
                    "model": {
                        "type": "string",
                        "description": "LLM model (for run_agent)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max flows (for list_flows)",
                    },
                    "scenario": {
                        "type": "string",
                        "description": "Test scenario description (for tier_guidance)",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": ["operation"],
            },
        ),
        # =====================================================================
        # Status (replaces 2 tools)
        # =====================================================================
        Tool(
            name="status",
            description="Status operations: mcp, logs",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["mcp", "logs"],
                        "description": "Operation to perform",
                    },
                    "reload": {
                        "type": "boolean",
                        "description": "Reload modules (for mcp)",
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of entries (for logs)",
                    },
                    "level": {
                        "type": "string",
                        "enum": ["DEBUG", "INFO", "WARNING", "ERROR"],
                        "description": "Filter by level (for logs)",
                    },
                    "errors_only": {
                        "type": "boolean",
                        "description": "Show only errors (for logs)",
                    },
                },
                "required": ["operation"],
            },
        ),
        # =====================================================================
        # Knowledge (replaces 5 tools → but now primarily via Resources)
        # This single tool remains for backward compatibility and complex queries
        # =====================================================================
        Tool(
            name="knowledge",
            description="Knowledge lookup: concept, examples, cli_help, workflow, inference. Note: Static content also available via MCP Resources.",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["concept", "examples", "cli_help", "workflow", "inference"],
                        "description": "Operation to perform",
                    },
                    "term": {
                        "type": "string",
                        "description": "Concept/pattern name (for concept)",
                    },
                    "features": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Features to search (for examples)",
                    },
                    "complexity": {
                        "type": "string",
                        "enum": ["beginner", "intermediate", "advanced"],
                        "description": "Complexity level (for examples)",
                    },
                    "command": {
                        "type": "string",
                        "description": "CLI command (for cli_help)",
                    },
                    "workflow": {
                        "type": "string",
                        "description": "Workflow name (for workflow)",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query (for inference)",
                    },
                    "detail": {
                        "type": "string",
                        "enum": ["minimal", "full"],
                        "description": "Detail level (for inference)",
                    },
                    "list_all": {
                        "type": "boolean",
                        "description": "List all triggers (for inference)",
                    },
                },
                "required": ["operation"],
            },
        ),
        # =====================================================================
        # Mailpit (for monitoring feedback during UX testing)
        # =====================================================================
        Tool(
            name="mailpit",
            description="Mailpit operations: list_messages, get_message, search, delete, stats. Monitor feedback and bug reports submitted via Dazzle Bar.",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["list_messages", "get_message", "search", "delete", "stats"],
                        "description": "Operation to perform",
                    },
                    "message_id": {
                        "type": "string",
                        "description": "Message ID (for get_message, delete)",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query (for search)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max messages to return (default 20)",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["bug", "feature", "ux", "general"],
                        "description": "Filter by feedback category (for list_messages)",
                    },
                },
                "required": ["operation"],
            },
        ),
    ]


def get_all_consolidated_tools() -> list[Tool]:
    """Get all tools (dev mode + consolidated)."""
    tools = []

    if is_dev_mode():
        tools.extend(get_dev_mode_tools())

    tools.extend(get_consolidated_tools())

    return tools
