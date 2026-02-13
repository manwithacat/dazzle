"""
Prompt definitions for DAZZLE MCP server.

Prompts are reusable instructions that Claude Code can invoke as slash commands.
"""

from typing import Any


def create_prompts() -> list[dict[str, Any]]:
    """
    Create available prompts/slash commands for the MCP server.

    Returns:
        List of prompt definitions with name, description, and arguments
    """
    return [
        {
            "name": "validate",
            "description": "Validate the DAZZLE project DSL and report any errors",
            "arguments": [],
        },
        {
            "name": "review_dsl",
            "description": "Review DSL design and suggest improvements",
            "arguments": [
                {
                    "name": "aspect",
                    "description": "Aspect to review: design, performance, security, or all",
                    "required": False,
                }
            ],
        },
        {
            "name": "code_review",
            "description": "Review generated code artifacts for quality and best practices. NOTE: DNR is the primary runtime - use code generation only for custom deployments.",
            "arguments": [
                {
                    "name": "stack",
                    "description": "Stack to review (docker, base).",
                    "required": True,
                }
            ],
        },
        {
            "name": "suggest_surfaces",
            "description": "Suggest surface definitions for an entity based on CRUD patterns",
            "arguments": [
                {
                    "name": "entity_name",
                    "description": "Name of the entity to suggest surfaces for",
                    "required": True,
                }
            ],
        },
        {
            "name": "optimize_dsl",
            "description": "Suggest optimizations for DSL based on patterns and best practices",
            "arguments": [],
        },
        {
            "name": "getting_started",
            "description": "Get a complete getting started guide for new DAZZLE users",
            "arguments": [],
        },
        {
            "name": "napkin_to_app",
            "description": "Transform a rough narrative spec into a running DAZZLE app. Includes cognition pass (entity discovery, lifecycle analysis, persona extraction, business rules) before DSL generation.",
            "arguments": [
                {
                    "name": "spec_path",
                    "description": "Path to the spec file (markdown or text)",
                    "required": False,
                }
            ],
        },
    ]


# =============================================================================
# System Context for Claude
# =============================================================================

DAZZLE_CONTEXT = """# DAZZLE Assistant Context

You are helping a user work with DAZZLE, a DSL-first toolkit for building applications.

## Quick Start
```bash
dazzle init my-app && cd my-app
dazzle serve
# UI: http://localhost:3000 | API: http://localhost:8000/docs
```

## Key Concepts
- **Entity**: Data model (like a database table)
- **Surface**: UI definition for an entity (list, view, create, edit modes)
- **Workspace**: Dashboard combining multiple data views
- **Persona**: Role-based variants (admin, manager, member)
- **Attention Signal**: Data-driven alerts (critical, warning, notice, info)

## Primary Runtime
Dazzle Runtime runs apps directly from DSL - no code generation needed.
Use `dazzle serve` to run any DAZZLE project.

## Available Tools
When helping users, use these MCP tools:
- `get_workflow_guide("getting_started")` - Complete beginner guide
- `lookup_concept("patterns")` - List available DSL patterns with examples
- `lookup_concept("<pattern>")` - Get specific pattern (crud, dashboard, etc.)
- `get_cli_help("<command>")` - CLI command documentation
- `validate_dsl` - Check project for errors
- `discovery(operation="status")` - Check if capability discovery is available
- `discovery(operation="run", mode="entity_completeness")` - Find missing CRUD surfaces and state machine UI gaps
- `discovery(operation="run", mode="workflow_coherence")` - Validate process/story integrity
- `discovery(operation="run", mode="persona")` - Open-ended persona walkthrough to find UX gaps

## Common User Requests → Tool to Use
- "How do I start?" → get_workflow_guide("getting_started")
- "Add a new entity" → get_workflow_guide("add_entity")
- "Create a dashboard" → get_workflow_guide("add_workspace") or lookup_concept("dashboard")
- "Role-based access" → get_workflow_guide("add_personas") or lookup_concept("role_based_access")
- "What patterns exist?" → lookup_concept("patterns")
- "Run the app" → get_cli_help("serve")
- "Something is broken" → get_workflow_guide("troubleshoot")
- "Create a pitch deck" → get_workflow_guide("pitch_deck") or pitch(operation='scaffold')
- "Review my pitch" → pitch(operation='review')
- "Find gaps in my app" → discovery(operation="run", mode="entity_completeness")
- "Check CRUD coverage" → discovery(operation="run", mode="entity_completeness")
- "Validate workflows" → discovery(operation="run", mode="workflow_coherence")
- "Explore as a persona" → discovery(operation="run", mode="persona")
- "Run discovery" → get_workflow_guide("run_discovery")
"""


def get_dazzle_context() -> str:
    """Return context string for Claude about DAZZLE."""
    return DAZZLE_CONTEXT
