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


def get_story_tools() -> list[Tool]:
    """Get Behaviour Layer story tools for LLM-assisted story generation."""
    return [
        Tool(
            name="get_dsl_spec",
            description="Get complete DSL specification including entities, surfaces, personas, workspaces, and state machines. Use this as input for story proposal.",
            inputSchema={
                "type": "object",
                "properties": {**PROJECT_PATH_SCHEMA},
                "required": [],
            },
        ),
        Tool(
            name="propose_stories_from_dsl",
            description="Analyze DSL spec and propose behavioural user stories. Stories describe WHAT should happen (outcomes) and WHEN (triggers), not HOW (implementation). Returns draft stories for human review.",
            inputSchema={
                "type": "object",
                "properties": {
                    "entities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional: Focus on specific entities. If omitted, analyzes all entities.",
                    },
                    "max_stories": {
                        "type": "integer",
                        "description": "Maximum number of stories to propose (default: 30)",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": [],
            },
        ),
        Tool(
            name="save_stories",
            description="Save stories to .dazzle/stories/stories.json. Stories are validated before saving. Use overwrite=true to replace existing stories with same IDs.",
            inputSchema={
                "type": "object",
                "properties": {
                    "stories": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "story_id": {"type": "string"},
                                "title": {"type": "string"},
                                "actor": {"type": "string"},
                                "trigger": {
                                    "type": "string",
                                    "enum": [
                                        "form_submitted",
                                        "status_changed",
                                        "timer_elapsed",
                                        "external_event",
                                        "user_click",
                                        "cron_daily",
                                        "cron_hourly",
                                    ],
                                },
                                "scope": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "preconditions": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "happy_path_outcome": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "side_effects": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "constraints": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "variants": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "status": {
                                    "type": "string",
                                    "enum": ["draft", "accepted", "rejected"],
                                },
                            },
                            "required": ["story_id", "title", "actor", "trigger"],
                        },
                        "description": "List of story specifications to save",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "If true, replace stories with matching IDs. If false, skip existing.",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": ["stories"],
            },
        ),
        Tool(
            name="get_stories",
            description="Retrieve stories from .dazzle/stories/. Filter by status to get accepted, rejected, or draft stories.",
            inputSchema={
                "type": "object",
                "properties": {
                    "status_filter": {
                        "type": "string",
                        "enum": ["all", "accepted", "rejected", "draft"],
                        "description": "Filter by status (default: all)",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": [],
            },
        ),
        Tool(
            name="generate_story_stubs",
            description="Generate Python service stubs from accepted stories. Each stub contains the story contract as a docstring and raises NotImplementedError.",
            inputSchema={
                "type": "object",
                "properties": {
                    "story_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of story IDs to generate stubs for. If omitted, generates for all accepted stories.",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Directory for generated stubs (default: 'services')",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": [],
            },
        ),
        Tool(
            name="generate_tests_from_stories",
            description="Generate test designs from accepted stories. Converts behavioural stories (WHAT should happen) into test designs (HOW to verify it). Returns proposed test designs for review before saving with save_test_designs.",
            inputSchema={
                "type": "object",
                "properties": {
                    "story_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of story IDs to generate tests for. If omitted, generates for all accepted stories.",
                    },
                    "include_draft": {
                        "type": "boolean",
                        "description": "If true, also include draft stories (default: false, only accepted stories).",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": [],
            },
        ),
    ]


def get_demo_data_tools() -> list[Tool]:
    """Get Demo Data Blueprint tools for LLM-assisted demo data generation."""
    return [
        Tool(
            name="propose_demo_blueprint",
            description="Analyze DSL and propose a Demo Data Blueprint with field patterns. For large projects (>15 entities), use the 'entities' parameter to generate in batches to avoid truncation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "domain_description": {
                        "type": "string",
                        "description": "1-3 sentence domain description for flavoring data (e.g., 'Residential solar installer CRM for UK households')",
                    },
                    "tenant_count": {
                        "type": "integer",
                        "description": "Number of demo tenants to create (default: 2, uses Alpha/Bravo naming)",
                    },
                    "entities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional: Specific entities to include. Use for large projects to avoid truncation. Generate in batches of 10-15 entities.",
                    },
                    "include_metadata": {
                        "type": "boolean",
                        "description": "Include tenants/personas in output (default: true). Set false when generating additional entity batches.",
                    },
                    "quick_mode": {
                        "type": "boolean",
                        "description": "Quick demo mode: generates minimal patterns (5 rows/entity), prioritizes entities with surfaces. Good for testing.",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": ["domain_description"],
            },
        ),
        Tool(
            name="save_demo_blueprint",
            description="Save a Demo Data Blueprint to .dazzle/demo_data/blueprint.json. Validates against DSL and can merge with existing blueprint for chunked generation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "blueprint": {
                        "type": "object",
                        "description": "DemoDataBlueprint object with project_id, domain_description, tenants, personas, entities",
                        "properties": {
                            "project_id": {"type": "string"},
                            "domain_description": {"type": "string"},
                            "seed": {"type": "integer"},
                            "tenants": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "slug": {"type": "string"},
                                        "notes": {"type": "string"},
                                    },
                                    "required": ["name"],
                                },
                            },
                            "personas": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "persona_name": {"type": "string"},
                                        "description": {"type": "string"},
                                        "default_role": {"type": "string"},
                                        "default_user_count": {"type": "integer"},
                                    },
                                    "required": ["persona_name", "description"],
                                },
                            },
                            "entities": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "row_count_default": {"type": "integer"},
                                        "notes": {"type": "string"},
                                        "tenant_scoped": {"type": "boolean"},
                                        "field_patterns": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "field_name": {"type": "string"},
                                                    "strategy": {
                                                        "type": "string",
                                                        "enum": [
                                                            "static_list",
                                                            "enum_weighted",
                                                            "person_name",
                                                            "company_name",
                                                            "email_from_name",
                                                            "username_from_name",
                                                            "hashed_password_placeholder",
                                                            "free_text_lorem",
                                                            "numeric_range",
                                                            "currency_amount",
                                                            "date_relative",
                                                            "boolean_weighted",
                                                            "foreign_key",
                                                            "composite",
                                                            "custom_prompt",
                                                            "uuid_generate",
                                                        ],
                                                    },
                                                    "params": {"type": "object"},
                                                },
                                                "required": ["field_name", "strategy"],
                                            },
                                        },
                                    },
                                    "required": ["name"],
                                },
                            },
                        },
                        "required": ["project_id", "domain_description"],
                    },
                    "merge": {
                        "type": "boolean",
                        "description": "Merge with existing blueprint (for chunked generation). New entities override existing ones.",
                    },
                    "validate": {
                        "type": "boolean",
                        "description": "Validate blueprint covers all DSL entities (default: true). Returns warnings for missing entities.",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": ["blueprint"],
            },
        ),
        Tool(
            name="get_demo_blueprint",
            description="Load the current Demo Data Blueprint from .dazzle/demo_data/blueprint.json.",
            inputSchema={
                "type": "object",
                "properties": {**PROJECT_PATH_SCHEMA},
                "required": [],
            },
        ),
        Tool(
            name="generate_demo_data",
            description="Generate demo data files from the blueprint. Outputs CSV or JSONL files to demo_data/ directory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "format": {
                        "type": "string",
                        "enum": ["csv", "jsonl"],
                        "description": "Output format (default: csv)",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Output directory relative to project (default: demo_data)",
                    },
                    "entities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific entities to generate. If omitted, generates all.",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": [],
            },
        ),
    ]


def get_test_design_tools() -> list[Tool]:
    """Get UX Coverage test design tools for LLM-assisted test generation."""
    return [
        Tool(
            name="propose_persona_tests",
            description="Generate test designs from persona goals and workflows. Analyzes the persona's goals and generates high-level test specifications that verify the persona can achieve their objectives.",
            inputSchema={
                "type": "object",
                "properties": {
                    "persona": {
                        "type": "string",
                        "description": "Persona name to generate tests for. If omitted, generates for all personas.",
                    },
                    "max_tests": {
                        "type": "integer",
                        "description": "Maximum number of test designs per persona (default: 10)",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": [],
            },
        ),
        Tool(
            name="get_test_gaps",
            description="Analyze coverage and identify what's missing. Returns untested entities, persona goals, state transitions, surfaces, and scenarios with suggested test designs.",
            inputSchema={
                "type": "object",
                "properties": {**PROJECT_PATH_SCHEMA},
                "required": [],
            },
        ),
        Tool(
            name="save_test_designs",
            description="Save test designs to dsl/tests/designs.json. Test designs are validated before saving. Use overwrite=true to replace existing designs with same IDs.",
            inputSchema={
                "type": "object",
                "properties": {
                    "designs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "test_id": {"type": "string"},
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                                "persona": {"type": "string"},
                                "scenario": {"type": "string"},
                                "trigger": {
                                    "type": "string",
                                    "enum": [
                                        "form_submitted",
                                        "status_changed",
                                        "timer_elapsed",
                                        "external_event",
                                        "user_click",
                                        "page_load",
                                        "cron_daily",
                                        "cron_hourly",
                                    ],
                                },
                                "steps": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "action": {
                                                "type": "string",
                                                "enum": [
                                                    "login_as",
                                                    "logout",
                                                    "navigate_to",
                                                    "create",
                                                    "update",
                                                    "delete",
                                                    "click",
                                                    "fill",
                                                    "select",
                                                    "wait_for",
                                                    "assert_visible",
                                                    "assert_not_visible",
                                                    "assert_text",
                                                    "assert_count",
                                                    "trigger_transition",
                                                    "upload",
                                                    "download",
                                                ],
                                            },
                                            "target": {"type": "string"},
                                            "data": {"type": "object"},
                                            "rationale": {"type": "string"},
                                        },
                                        "required": ["action", "target"],
                                    },
                                },
                                "expected_outcomes": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "entities": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "surfaces": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "tags": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "status": {
                                    "type": "string",
                                    "enum": [
                                        "proposed",
                                        "accepted",
                                        "implemented",
                                        "verified",
                                        "rejected",
                                    ],
                                },
                                "notes": {"type": "string"},
                            },
                            "required": ["test_id", "title"],
                        },
                        "description": "List of test design specifications to save",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "If true, replace designs with matching IDs. If false, skip existing.",
                    },
                    "to_dsl": {
                        "type": "boolean",
                        "description": "If true (default), save to dsl/tests/. If false, save to .dazzle/test_designs/.",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": ["designs"],
            },
        ),
        Tool(
            name="get_test_designs",
            description="Retrieve test designs from dsl/tests/ or .dazzle/test_designs/. Filter by status to get proposed, accepted, implemented, or rejected designs.",
            inputSchema={
                "type": "object",
                "properties": {
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
                        "description": "Filter by status (default: all)",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": [],
            },
        ),
        Tool(
            name="get_coverage_actions",
            description="""Get prioritized actions to increase test design coverage. Returns actionable prompts an LLM can execute directly.

This tool analyzes the current test design coverage and returns:
- Current coverage score and breakdown
- Prioritized list of specific actions to increase coverage
- Complete prompts for each action (ready to execute)
- Code templates where applicable

Use this tool when you want to systematically increase test design coverage. Execute the returned actions in priority order.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "max_actions": {
                        "type": "integer",
                        "description": "Maximum number of actions to return (default: 5)",
                    },
                    "focus": {
                        "type": "string",
                        "enum": ["all", "personas", "entities", "state_machines", "scenarios"],
                        "description": "Focus on a specific area (default: all)",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": [],
            },
        ),
        Tool(
            name="get_runtime_coverage_gaps",
            description="""Analyze runtime UX coverage report to find gaps and generate tests to fill them.

This tool reads a previous runtime coverage report (from CI or local test run) and identifies:
- Routes not visited
- CRUD operations not tested
- UI views not exercised
- Components not tested

Returns actionable test designs that can be saved with save_test_designs and will execute in future test runs.

IMPORTANT: Runtime coverage is expensive to collect (requires running the full E2E test suite). The coverage report should be retained in dsl/tests/runtime_coverage.json.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "coverage_report_path": {
                        "type": "string",
                        "description": "Path to ux_coverage.json. If not provided, looks in dsl/tests/runtime_coverage.json",
                    },
                    "max_actions": {
                        "type": "integer",
                        "description": "Maximum number of test designs to generate (default: 5)",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": [],
            },
        ),
        Tool(
            name="save_runtime_coverage",
            description="""Save a runtime coverage report to dsl/tests/runtime_coverage.json for future analysis.

Use this after a test run to persist the coverage report so it can be used by get_runtime_coverage_gaps.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "coverage_data": {
                        "type": "object",
                        "description": "The coverage report data (from ux_coverage.json)",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": ["coverage_data"],
            },
        ),
    ]


def get_sitespec_tools() -> list[Tool]:
    """Get SiteSpec tools for public site shell management."""
    return [
        Tool(
            name="get_sitespec",
            description="Load the SiteSpec (public site shell configuration) from sitespec.yaml. Returns brand, layout, pages, navigation, and content source references. Use use_defaults=true to get default spec when file doesn't exist.",
            inputSchema={
                "type": "object",
                "properties": {
                    "use_defaults": {
                        "type": "boolean",
                        "description": "If true (default), return default SiteSpec when file doesn't exist. If false, error when missing.",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": [],
            },
        ),
        Tool(
            name="validate_sitespec",
            description="Validate the SiteSpec for semantic correctness. Checks route uniqueness, content file existence, navigation consistency, and production readiness.",
            inputSchema={
                "type": "object",
                "properties": {
                    "check_content_files": {
                        "type": "boolean",
                        "description": "If true (default), check that referenced content files exist.",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": [],
            },
        ),
        Tool(
            name="scaffold_site",
            description="Create default site structure including sitespec.yaml and content templates (terms.md, privacy.md, about.md). Use for new projects.",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_name": {
                        "type": "string",
                        "description": "Product name to use in templates (default: 'My App')",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "If true, overwrite existing files. If false (default), skip existing.",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": [],
            },
        ),
    ]


def get_event_first_tools() -> list[Tool]:
    """Get Event-First Architecture tools (Phase H)."""
    return [
        Tool(
            name="extract_semantics",
            description="Extract semantic elements from AppSpec: entities, commands, events, projections, tenancy signals, and compliance signals. Use for understanding the event-first structure of an application.",
            inputSchema={
                "type": "object",
                "properties": {**PROJECT_PATH_SCHEMA},
                "required": [],
            },
        ),
        Tool(
            name="validate_events",
            description="Validate event-first architecture: event naming conventions, idempotency hazards, and projection necessity. Returns issues with severity and suggestions.",
            inputSchema={
                "type": "object",
                "properties": {**PROJECT_PATH_SCHEMA},
                "required": [],
            },
        ),
        Tool(
            name="infer_tenancy",
            description="Infer multi-tenancy requirements from AppSpec. Detects tenant_id fields, tenant entities, and recommends tenancy mode (single, shared_schema, etc.).",
            inputSchema={
                "type": "object",
                "properties": {**PROJECT_PATH_SCHEMA},
                "required": [],
            },
        ),
        Tool(
            name="infer_compliance",
            description="Infer compliance requirements from AppSpec. Detects PII fields, financial data, and recommends classification and compliance frameworks (GDPR, PCI-DSS, etc.).",
            inputSchema={
                "type": "object",
                "properties": {**PROJECT_PATH_SCHEMA},
                "required": [],
            },
        ),
        Tool(
            name="infer_analytics",
            description="Infer analytics intent from AppSpec. Detects aggregate fields, time-series entities, and dashboard surfaces. Recommends data products.",
            inputSchema={
                "type": "object",
                "properties": {**PROJECT_PATH_SCHEMA},
                "required": [],
            },
        ),
        Tool(
            name="add_feedback",
            description="Record feedback about the DSL or generated code. Use the structured model: pain_point, expected, observed, severity, scope, hypothesis.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pain_point": {
                        "type": "string",
                        "description": "What is the problem or friction point?",
                    },
                    "expected": {
                        "type": "string",
                        "description": "What was expected to happen?",
                    },
                    "observed": {
                        "type": "string",
                        "description": "What actually happened?",
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "high", "medium", "low"],
                        "description": "Severity of the issue",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["global", "module", "entity", "field", "surface"],
                        "description": "Scope of the issue's impact",
                    },
                    "hypothesis": {
                        "type": "string",
                        "description": "Hypothesis about the root cause",
                    },
                    "location": {
                        "type": "string",
                        "description": "Location in DSL or code (e.g., 'entity:Order.status')",
                    },
                },
                "required": ["pain_point", "expected", "observed", "severity", "scope"],
            },
        ),
        Tool(
            name="list_feedback",
            description="List recorded feedback entries. Filter by severity, scope, or resolution status.",
            inputSchema={
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "high", "medium", "low"],
                        "description": "Filter by severity",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["global", "module", "entity", "field", "surface"],
                        "description": "Filter by scope",
                    },
                    "resolved": {
                        "type": "boolean",
                        "description": "Filter by resolution status",
                    },
                },
                "required": [],
            },
        ),
    ]


def get_process_tools() -> list[Tool]:
    """Get ProcessSpec and coverage tools for workflow management."""
    return [
        Tool(
            name="stories_coverage",
            description="Analyze which stories are implemented by processes. Returns coverage percentage and identifies uncovered or partially covered stories. Use after defining processes to verify all acceptance criteria are met.",
            inputSchema={
                "type": "object",
                "properties": {**PROJECT_PATH_SCHEMA},
                "required": [],
            },
        ),
        Tool(
            name="propose_processes_from_stories",
            description="Analyze uncovered stories and propose ProcessSpec implementations. Returns draft DSL code for each proposed process. Use after stories_coverage shows uncovered stories.",
            inputSchema={
                "type": "object",
                "properties": {
                    "story_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional: Specific story IDs to generate processes for. If omitted, generates for all uncovered/partial stories.",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": [],
            },
        ),
        Tool(
            name="list_processes",
            description="List all process definitions in the project. Shows process names, triggers, step counts, and linked stories.",
            inputSchema={
                "type": "object",
                "properties": {**PROJECT_PATH_SCHEMA},
                "required": [],
            },
        ),
        Tool(
            name="inspect_process",
            description="Get detailed information about a process definition. Shows trigger, steps, compensations, inputs/outputs, and linked stories. Use to understand process structure before execution.",
            inputSchema={
                "type": "object",
                "properties": {
                    "process_name": {
                        "type": "string",
                        "description": "Name of the process to inspect",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": ["process_name"],
            },
        ),
        Tool(
            name="list_process_runs",
            description="List process runs with optional filtering by status or process name. Use to monitor running workflows and debug failures. Returns recent runs sorted by start time.",
            inputSchema={
                "type": "object",
                "properties": {
                    "process_name": {
                        "type": "string",
                        "description": "Filter by process name",
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
                        "description": "Filter by run status",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of runs to return (default: 50)",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": [],
            },
        ),
        Tool(
            name="get_process_run",
            description="Get detailed information about a specific process run. Includes step history, context, inputs/outputs, and any errors. Use to debug specific workflow executions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "run_id": {
                        "type": "string",
                        "description": "The unique run ID to retrieve",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": ["run_id"],
            },
        ),
        Tool(
            name="get_process_diagram",
            description="Generate a Mermaid diagram for a process. Returns flowchart or state diagram showing process steps, flow control, human task outcomes, and optionally compensation handlers. Useful for documentation and visualization.",
            inputSchema={
                "type": "object",
                "properties": {
                    "process_name": {
                        "type": "string",
                        "description": "Name of the process to visualize",
                    },
                    "type": {
                        "type": "string",
                        "enum": ["flowchart", "stateDiagram"],
                        "description": "Diagram type: flowchart (default) or stateDiagram",
                    },
                    "include_compensations": {
                        "type": "boolean",
                        "description": "Include saga compensation handlers in diagram (default: false)",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": ["process_name"],
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

    # Add Story/Behaviour Layer tools (always available)
    tools.extend(get_story_tools())

    # Add Demo Data Blueprint tools (always available)
    tools.extend(get_demo_data_tools())

    # Add UX Coverage Test Design tools (always available)
    tools.extend(get_test_design_tools())

    # Add SiteSpec tools (always available)
    tools.extend(get_sitespec_tools())

    # Add Event-First Architecture tools (Phase H)
    tools.extend(get_event_first_tools())

    # Add ProcessSpec and coverage tools (Phase 7)
    tools.extend(get_process_tools())

    # Add internal tools (always available, but some features dev-only)
    tools.extend(get_internal_tools())

    return tools
