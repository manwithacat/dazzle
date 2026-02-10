"""
Consolidated MCP Server tool definitions.

This module reduces token budget by consolidating related tools into single
tools with enum-based operations. Each operation is explicitly listed in the
schema, preserving discoverability for LLMs.

Consolidation strategy:
- 66 original tools → 18 consolidated tools
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
    Get consolidated tools (18 tools replacing 66 original tools).

    Each tool uses an 'operation' enum to specify the action, preserving
    discoverability while reducing schema overhead.
    """
    return [
        # =====================================================================
        # DSL Operations (replaces 7 tools)
        # =====================================================================
        Tool(
            name="dsl",
            description="DSL operations: validate, list_modules, inspect_entity, inspect_surface, analyze, lint, get_spec, fidelity, list_fragments, export_frontend_spec. NOTE: export_frontend_spec produces a LARGE output intended for human developers migrating away from Dazzle — always use 'sections' and/or 'entities' filters to avoid flooding context. Prefer inspect_entity/inspect_surface for LLM queries.",
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
                            "fidelity",
                            "list_fragments",
                            "export_frontend_spec",
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
                    "entity_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Entity names to fetch full details for (for get_spec). Omit for summary.",
                    },
                    "surface_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Surface names to fetch full details for (for get_spec). Omit for summary.",
                    },
                    "surface_filter": {
                        "type": "string",
                        "description": "Filter to a specific surface name (for fidelity)",
                    },
                    "gaps_only": {
                        "type": "boolean",
                        "description": "Omit surfaces with fidelity=1.0 (for fidelity)",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["markdown", "json"],
                        "description": "Output format (for export_frontend_spec, default: markdown)",
                    },
                    "sections": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter to specific sections (for export_frontend_spec). Options: typescript_interfaces, route_map, component_inventory, state_machines, api_contract, workspace_layouts, test_criteria",
                    },
                    "entities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter to specific entity names (for export_frontend_spec)",
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
            description="Story operations: propose, save, get, generate_tests, coverage",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": [
                            "propose",
                            "save",
                            "get",
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
                        "description": "Story IDs (for get: fetch full details; for generate_tests)",
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
                    "test_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Test design IDs to fetch full details (for get)",
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
        # SiteSpec (replaces 3 tools + copy + coherence operations)
        # =====================================================================
        Tool(
            name="sitespec",
            description="SiteSpec operations: get, validate, scaffold, coherence. Copy operations: get_copy, scaffold_copy, review_copy. Use 'coherence' to check if the site feels like a real website (navigation, CTAs, content completeness). Theme operations: get_theme, scaffold_theme, validate_theme, generate_tokens, generate_imagery_prompts.",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": [
                            "get",
                            "validate",
                            "scaffold",
                            "get_copy",
                            "scaffold_copy",
                            "review_copy",
                            "coherence",
                            "get_theme",
                            "scaffold_theme",
                            "validate_theme",
                            "generate_tokens",
                            "generate_imagery_prompts",
                        ],
                        "description": "Operation to perform",
                    },
                    "use_defaults": {
                        "type": "boolean",
                        "description": "Use defaults when missing (for get, get_theme)",
                    },
                    "check_content_files": {
                        "type": "boolean",
                        "description": "Check content files (for validate)",
                    },
                    "product_name": {
                        "type": "string",
                        "description": "Product name (for scaffold, scaffold_copy)",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "Overwrite existing (for scaffold, scaffold_copy, scaffold_theme)",
                    },
                    "business_context": {
                        "type": "string",
                        "description": "Business type hint for coherence check (saas, marketplace, agency, ecommerce)",
                    },
                    "brand_hue": {
                        "type": "number",
                        "description": "Brand hue 0-360 on OKLCH wheel (for scaffold_theme)",
                    },
                    "brand_chroma": {
                        "type": "number",
                        "description": "Brand chroma 0-0.4 (for scaffold_theme)",
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
            description="Semantic analysis: extract, validate_events, tenancy, compliance, analytics, extract_guards",
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
                            "extract_guards",
                        ],
                        "description": "Operation to perform",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": ["operation"],
            },
        ),
        # =====================================================================
        # Processes (replaces 7 tools)
        # =====================================================================
        Tool(
            name="process",
            description="Process operations: propose, save, list, inspect, list_runs, get_run, diagram, coverage",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": [
                            "propose",
                            "save",
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
                    "processes": {
                        "type": "array",
                        "description": "Process definitions to save (for save)",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "Overwrite existing processes with same name (for save)",
                    },
                    "story_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Story IDs (for propose)",
                    },
                    "include_crud": {
                        "type": "boolean",
                        "description": "Include CRUD stories as compose_process proposals (for propose, default: false)",
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
                    "status_filter": {
                        "type": "string",
                        "enum": ["all", "covered", "partial", "uncovered"],
                        "description": "Filter by coverage status (for coverage, default: all)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (for list_runs, coverage; default: 50)",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Skip N results for pagination (for coverage, default: 0)",
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
            description="DSL test operations: generate, run, run_all, coverage, list, create_sessions, diff_personas, verify_story",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": [
                            "generate",
                            "run",
                            "run_all",
                            "coverage",
                            "list",
                            "create_sessions",
                            "diff_personas",
                            "verify_story",
                        ],
                        "description": "Operation to perform",
                    },
                    "save": {
                        "type": "boolean",
                        "description": "Save generated tests (for generate)",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["json", "yaml", "bash"],
                        "description": "Output format (for generate)",
                    },
                    "base_url": {
                        "type": "string",
                        "description": "Server URL (for run, create_sessions, diff_personas)",
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
                    "persona": {
                        "type": "string",
                        "description": "Run tests as specific persona (for run)",
                    },
                    "force": {
                        "type": "boolean",
                        "description": "Force recreate sessions (for create_sessions)",
                    },
                    "route": {
                        "type": "string",
                        "description": "Route to diff (for diff_personas)",
                    },
                    "routes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Routes to diff (for diff_personas)",
                    },
                    "persona_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Persona IDs to compare (for diff_personas, default: all)",
                    },
                    "story_id": {
                        "type": "string",
                        "description": "Story ID to verify (for verify_story)",
                    },
                    "story_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Story IDs to verify (for verify_story, alternative to single story_id)",
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
            description="E2E test operations: check_infra, run, run_agent, coverage, list_flows, tier_guidance, run_viewport, list_viewport_specs, save_viewport_specs",
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
                            "run_viewport",
                            "list_viewport_specs",
                            "save_viewport_specs",
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
                    "viewports": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Viewport names to test (for run_viewport, e.g. ['mobile', 'desktop'])",
                    },
                    "viewport_specs": {
                        "type": "array",
                        "description": "Custom viewport specs to save (for save_viewport_specs)",
                    },
                    "to_dsl": {
                        "type": "boolean",
                        "description": "Save to dsl/ directory (for save_viewport_specs, default: true)",
                    },
                    "persona_id": {
                        "type": "string",
                        "description": "Persona ID for authenticated viewport testing (for run_viewport)",
                    },
                    "persona_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Multiple persona IDs to test (for run_viewport, runs matrix per persona)",
                    },
                    "capture_screenshots": {
                        "type": "boolean",
                        "description": "Capture screenshots for visual regression (for run_viewport)",
                    },
                    "update_baselines": {
                        "type": "boolean",
                        "description": "Update baseline screenshots (for run_viewport)",
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
            description="Status operations: mcp, logs, active_project, telemetry",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["mcp", "logs", "active_project", "telemetry"],
                        "description": "Operation to perform",
                    },
                    "reload": {
                        "type": "boolean",
                        "description": "Reload modules (for mcp)",
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of entries (for logs, telemetry)",
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
                    "tool_name": {
                        "type": "string",
                        "description": "Filter by tool name (for telemetry)",
                    },
                    "since_minutes": {
                        "type": "integer",
                        "description": "Only show invocations from the last N minutes (for telemetry)",
                    },
                    "stats_only": {
                        "type": "boolean",
                        "description": "Only return aggregate stats, no individual invocations (for telemetry)",
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
            description="Knowledge lookup: concept, examples, cli_help, workflow, inference, get_spec. Note: Static content also available via MCP Resources.",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": [
                            "concept",
                            "examples",
                            "cli_help",
                            "workflow",
                            "inference",
                            "get_spec",
                        ],
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
        # Pitch (investor pitch deck generation)
        # =====================================================================
        Tool(
            name="pitch",
            description="Pitch deck operations: scaffold, generate, validate, get, review, update, enrich, init_assets. Generate investor pitch decks from pitchspec.yaml + DSL data. Workflow: scaffold → enrich → update → validate → generate → review → iterate.",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": [
                            "scaffold",
                            "generate",
                            "validate",
                            "get",
                            "review",
                            "update",
                            "enrich",
                            "init_assets",
                        ],
                        "description": "Operation to perform",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["pptx", "narrative", "all"],
                        "description": "Output format (for generate)",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "Overwrite existing (for scaffold)",
                    },
                    "patch": {
                        "type": "object",
                        "description": "Partial pitchspec data to merge (for update)",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": ["operation"],
            },
        ),
        # =====================================================================
        # Contribution (community contribution packaging)
        # =====================================================================
        Tool(
            name="contribution",
            description="Community contribution: templates, create, validate, examples. Package API packs, UI patterns, bug fixes, DSL patterns, and feature requests for sharing with the Dazzle team.",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["templates", "create", "validate", "examples"],
                        "description": "Operation to perform",
                    },
                    "type": {
                        "type": "string",
                        "enum": [
                            "api_pack",
                            "ui_pattern",
                            "bug_fix",
                            "dsl_pattern",
                            "feature_request",
                        ],
                        "description": "Contribution type (for create, validate, examples)",
                    },
                    "title": {
                        "type": "string",
                        "description": "Contribution title (for create)",
                    },
                    "description": {
                        "type": "string",
                        "description": "What this contributes (for create)",
                    },
                    "content": {
                        "type": "object",
                        "description": "Type-specific content (for create, validate)",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Directory to write output files (for create)",
                    },
                },
                "required": ["operation"],
            },
        ),
        # =====================================================================
        # User Management (auth user/session CRUD)
        # =====================================================================
        Tool(
            name="user_management",
            description=(
                "User management operations: list, create, get, update, "
                "reset_password, deactivate, list_sessions, revoke_session, config. "
                "Manage auth users and sessions in SQLite or PostgreSQL."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": [
                            "list",
                            "create",
                            "get",
                            "update",
                            "reset_password",
                            "deactivate",
                            "list_sessions",
                            "revoke_session",
                            "config",
                        ],
                        "description": "Operation to perform",
                    },
                    "email": {
                        "type": "string",
                        "description": "User email (for create, get)",
                    },
                    "user_id": {
                        "type": "string",
                        "description": "User UUID (for get, update, reset_password, deactivate, list_sessions)",
                    },
                    "name": {
                        "type": "string",
                        "description": "Display name (for create)",
                    },
                    "username": {
                        "type": "string",
                        "description": "New display name (for update)",
                    },
                    "roles": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Role names (for create, update)",
                    },
                    "role": {
                        "type": "string",
                        "description": "Filter by role (for list)",
                    },
                    "is_superuser": {
                        "type": "boolean",
                        "description": "Superuser flag (for create, update)",
                    },
                    "is_active": {
                        "type": "boolean",
                        "description": "Active status (for update)",
                    },
                    "active_only": {
                        "type": "boolean",
                        "description": "Only active users/sessions (for list, list_sessions; default: true)",
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Session ID (for revoke_session)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (for list, list_sessions; default: 50)",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Pagination offset (for list; default: 0)",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": ["operation"],
            },
        ),
        # =====================================================================
        # User Profile (adaptive persona inference)
        # =====================================================================
        Tool(
            name="user_profile",
            description=(
                "User profile for adaptive persona inference. "
                "Operations: observe (analyze recent tool invocations), "
                "observe_message (analyze user message vocabulary), "
                "get (return current profile context), "
                "reset (delete and return fresh default)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["observe", "observe_message", "get", "reset"],
                        "description": "Operation to perform",
                    },
                    "message_text": {
                        "type": "string",
                        "description": "User message text (for observe_message)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max invocations to analyze (for observe; default: 50)",
                    },
                    "since_minutes": {
                        "type": "integer",
                        "description": "Only analyze invocations from last N minutes (for observe; default: 30)",
                    },
                },
                "required": ["operation"],
            },
        ),
        # =====================================================================
        # Bootstrap (entry point for naive app requests)
        # =====================================================================
        Tool(
            name="bootstrap",
            description=(
                "Entry point for 'build me an app' requests. Scans for spec files, "
                "runs cognition pass, and returns a mission briefing with agent instructions. "
                "Call this first when a user wants to build an app. Returns structured "
                "guidance for the next steps: either questions to ask the user, or "
                "instructions for DSL generation."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "spec_text": {
                        "type": "string",
                        "description": "Optional: spec text if provided directly by user",
                    },
                    "spec_path": {
                        "type": "string",
                        "description": "Optional: path to spec file",
                    },
                    "project_path": {
                        "type": "string",
                        "description": "Optional: project directory to scan for specs",
                    },
                },
                "required": [],
            },
        ),
        # =====================================================================
        # Spec Analyze (individual cognition operations)
        # =====================================================================
        Tool(
            name="spec_analyze",
            description=(
                "Analyze narrative specs before DSL generation. Operations: "
                "discover_entities (extract nouns/relationships), "
                "identify_lifecycles (find state transitions), "
                "extract_personas (identify user roles), "
                "surface_rules (extract business rules), "
                "generate_questions (surface ambiguities), "
                "refine_spec (produce structured spec from all analyses)"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": [
                            "discover_entities",
                            "identify_lifecycles",
                            "extract_personas",
                            "surface_rules",
                            "generate_questions",
                            "refine_spec",
                        ],
                        "description": "Operation to perform",
                    },
                    "spec_text": {
                        "type": "string",
                        "description": "The narrative spec text to analyze",
                    },
                    "entities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Entity names (for identify_lifecycles, generate_questions)",
                    },
                    "answers": {
                        "type": "object",
                        "description": "Answers to generated questions (for refine_spec)",
                    },
                },
                "required": ["operation"],
            },
        ),
        # =====================================================================
        # Graph (knowledge graph operations)
        # =====================================================================
        Tool(
            name="graph",
            description=(
                "Knowledge graph operations for codebase understanding. Operations: "
                "query (search entities by text), "
                "dependencies (what does X depend on?), "
                "dependents (what depends on X?), "
                "neighbourhood (entities within N hops), "
                "paths (find paths between entities), "
                "stats (graph statistics), "
                "populate (refresh graph from source), "
                "concept (look up a framework concept by name), "
                "inference (find inference patterns matching a query), "
                "related (get related concepts for an entity), "
                "export (export project KG data to JSON), "
                "import (import KG data from JSON)"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": [
                            "query",
                            "dependencies",
                            "dependents",
                            "neighbourhood",
                            "paths",
                            "stats",
                            "populate",
                            "concept",
                            "inference",
                            "related",
                            "export",
                            "import",
                        ],
                        "description": "Operation to perform",
                    },
                    "text": {
                        "type": "string",
                        "description": "Search text (for query)",
                    },
                    "entity_id": {
                        "type": "string",
                        "description": "Entity ID with prefix like file:, module:, class: (for dependencies, dependents, neighbourhood)",
                    },
                    "source_id": {
                        "type": "string",
                        "description": "Source entity ID (for paths)",
                    },
                    "target_id": {
                        "type": "string",
                        "description": "Target entity ID (for paths)",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Traversal depth (for neighbourhood, default: 1)",
                    },
                    "transitive": {
                        "type": "boolean",
                        "description": "Include transitive deps (for dependencies, dependents)",
                    },
                    "relation_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by relation types: imports, contains, inherits, depends_on",
                    },
                    "entity_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by entity types: file, module, class, function",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default: 20)",
                    },
                    "root_path": {
                        "type": "string",
                        "description": "Path to populate from (for populate)",
                    },
                    "name": {
                        "type": "string",
                        "description": "Entity or concept name (for concept, related)",
                    },
                    "data": {
                        "type": "object",
                        "description": "JSON export data to import (for import)",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Path to JSON file to import (for import, alternative to data)",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["merge", "replace"],
                        "description": "Import mode: merge (additive upsert) or replace (wipe and load). Default: merge",
                    },
                },
                "required": ["operation"],
            },
        ),
        # =====================================================================
        # Discovery Operations (capability discovery agent)
        # =====================================================================
        Tool(
            name="discovery",
            description="Capability discovery operations: run (build discovery mission), report (get results), compile (convert observations to proposals), emit (generate DSL from proposals), status (check readiness), verify_all_stories (batch verify accepted stories against API tests). Mode 'headless' runs pure DSL/KG persona journey analysis without a running app. Other modes explore a running Dazzle app as a persona and identify gaps between DSL spec and implementation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": [
                            "run",
                            "report",
                            "compile",
                            "emit",
                            "status",
                            "verify_all_stories",
                        ],
                        "description": "Operation to perform",
                    },
                    "mode": {
                        "type": "string",
                        "enum": [
                            "persona",
                            "entity_completeness",
                            "workflow_coherence",
                            "headless",
                        ],
                        "description": "Discovery mode. 'headless' analyzes persona journeys without a running app (default: persona)",
                    },
                    "persona": {
                        "type": "string",
                        "description": "Persona to explore as (for run/compile/emit, default: admin)",
                    },
                    "base_url": {
                        "type": "string",
                        "description": "Base URL of the running app (for run, default: http://localhost:3000)",
                    },
                    "max_steps": {
                        "type": "integer",
                        "description": "Maximum exploration steps (for run, default: 50)",
                    },
                    "token_budget": {
                        "type": "integer",
                        "description": "Token budget for LLM (for run, default: 200000)",
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Specific session ID (for report/compile/emit)",
                    },
                    "proposal_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific proposal IDs to emit (for emit, default: all)",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": ["operation"],
            },
        ),
        # =====================================================================
        # Pipeline (batch quality audit)
        # =====================================================================
        Tool(
            name="pipeline",
            description=(
                "Full deterministic quality audit in a single call. "
                "Chains: validate → lint → fidelity → test_generate → test_coverage → "
                "story_coverage → process_coverage → test_design_gaps → semantics. "
                "If base_url is provided, also runs all API tests. "
                "Returns structured JSON with per-step results and overall summary."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["run"],
                        "description": "Operation to perform",
                    },
                    "base_url": {
                        "type": "string",
                        "description": "Server URL — if provided, also runs dsl_test(run_all) as final step",
                    },
                    "stop_on_error": {
                        "type": "boolean",
                        "description": "Stop pipeline on first error (default: false, continues collecting results)",
                    },
                    "summary": {
                        "type": "boolean",
                        "description": "Return compact metrics instead of full results (default: true). Set false for full detail.",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": ["operation"],
            },
        ),
        # =====================================================================
        # Policy Analysis (RBAC access control)
        # =====================================================================
        Tool(
            name="policy",
            description=(
                "Policy analysis operations for RBAC access control. "
                "Operations: analyze (find entities without access rules), "
                "conflicts (detect contradictory permit/forbid rules), "
                "coverage (permission matrix: persona x entity x operation), "
                "simulate (trace which rules fire for a given persona + entity + operation)"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["analyze", "conflicts", "coverage", "simulate"],
                        "description": "Operation to perform",
                    },
                    "entity_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter to specific entity names (optional)",
                    },
                    "persona": {
                        "type": "string",
                        "description": "Persona ID (required for simulate)",
                    },
                    "operation_kind": {
                        "type": "string",
                        "enum": ["create", "read", "update", "delete", "list"],
                        "description": "CRUD operation to simulate (required for simulate)",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": ["operation"],
            },
        ),
        # =====================================================================
        # Pulse (founder-ready health report)
        # =====================================================================
        Tool(
            name="pulse",
            description=(
                "Founder-ready project health report. "
                "Operations: run (full report with narrative), "
                "radar (compact 6-axis readiness chart), "
                "persona (view app through a specific persona's eyes). "
                "Returns a Launch Readiness score, 6-axis radar, "
                "decisions needing founder input, recent wins, and blockers. "
                "Output: structured JSON with a 'markdown' field containing "
                "the human-readable report."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["run", "radar", "persona"],
                        "description": "Operation to perform",
                    },
                    "persona": {
                        "type": "string",
                        "description": (
                            "Persona name to view through (required for persona operation)"
                        ),
                    },
                    "business_context": {
                        "type": "string",
                        "description": (
                            "Business type hint for coherence check "
                            "(saas, marketplace, agency, ecommerce)"
                        ),
                    },
                    **PROJECT_PATH_SCHEMA,
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
