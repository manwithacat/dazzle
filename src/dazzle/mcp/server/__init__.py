"""
DAZZLE MCP Server implementation.

Implements the Model Context Protocol for DAZZLE using the official MCP SDK,
exposing tools for DSL validation, inspection, and code generation.

Supports two modes:
- Normal Mode: When running in a directory with dazzle.toml
- Dev Mode: When running in the Dazzle development environment (has examples/, src/dazzle/)
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, TextContent, Tool
from pydantic import AnyUrl

from dazzle.mcp.dnr_tools_impl import DNR_TOOL_NAMES, handle_dnr_tool

# Import event-first tool handlers (Phase H)
from dazzle.mcp.event_first_tools import (
    handle_add_feedback,
    handle_extract_semantics,
    handle_infer_analytics,
    handle_infer_compliance,
    handle_infer_tenancy,
    handle_list_feedback,
    handle_validate_events,
)
from dazzle.mcp.examples import get_example_metadata
from dazzle.mcp.resources import create_resources
from dazzle.mcp.semantics import get_dsl_patterns, get_semantic_index

from .glossary import get_glossary

# User feedback handlers (Dazzle Bar)
from .handlers.feedback import (
    get_feedback_handler,
    get_feedback_summary_handler,
    list_feedback_handler,
    update_feedback_handler,
)

# Import process tool handlers (Phase 7)
from .handlers.process import (
    get_process_diagram_handler,
    get_process_run_handler,
    inspect_process_handler,
    list_process_runs_handler,
    list_processes_handler,
    propose_processes_handler,
    stories_coverage_handler,
)

# E2E testing handlers (v0.19.0)
from .handlers.testing import (
    check_test_infrastructure_handler,
    get_e2e_test_coverage_handler,
    get_test_tier_guidance_handler,
    list_e2e_flows_handler,
    run_agent_e2e_tests_handler,
    run_e2e_tests_handler,
)
from .handlers_consolidated import dispatch_consolidated_tool
from .state import (
    get_active_project_path,
    get_available_projects,
    get_project_root,
    init_dev_mode,
    is_dev_mode,
    resolve_project_path,
    set_project_root,
    use_consolidated_tools,
)
from .tool_handlers import (
    analyze_patterns,
    find_examples_handler,
    generate_demo_data_handler,
    # DSL Test tools (v0.18.0)
    generate_dsl_tests_handler,
    generate_service_dsl_handler,
    generate_story_stubs_handler,
    generate_tests_from_stories_handler,
    get_active_project_info,
    get_api_pack_handler,
    get_cli_help_handler,
    get_coverage_actions_handler,
    get_demo_blueprint_handler,
    get_dnr_logs_handler,
    get_dsl_spec_handler,
    get_dsl_test_coverage_handler,
    get_entities,
    get_env_vars_for_packs_handler,
    get_mcp_status_handler,
    get_product_spec_handler,
    get_runtime_coverage_gaps_handler,
    get_sitespec_handler,
    get_stories_handler,
    get_surfaces,
    get_test_designs_handler,
    get_test_gaps_handler,
    get_workflow_guide_handler,
    inspect_entity,
    inspect_surface,
    lint_project,
    list_api_packs_handler,
    list_dsl_tests_handler,
    list_modules,
    list_projects,
    lookup_concept_handler,
    lookup_inference_handler,
    propose_demo_blueprint_handler,
    propose_persona_tests_handler,
    propose_stories_from_dsl_handler,
    run_dsl_tests_handler,
    save_demo_blueprint_handler,
    save_runtime_coverage_handler,
    save_stories_handler,
    save_test_designs_handler,
    scaffold_site_handler,
    search_api_packs_handler,
    select_project,
    validate_all_projects,
    validate_dsl,
    validate_sitespec_handler,
)
from .tools import get_all_tools
from .tools_consolidated import get_all_consolidated_tools

# Configure logging to stderr only (stdout is reserved for JSON-RPC protocol)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("dazzle.mcp")

# Create the MCP server instance
server = Server("dazzle")


# ============================================================================
# Tool Handler
# ============================================================================


@server.list_tools()  # type: ignore[no-untyped-call]
async def list_tools_handler() -> list[Tool]:
    """List available DAZZLE tools."""
    if use_consolidated_tools():
        logger.info("Using consolidated tools mode (66 -> 17 tools)")
        return get_all_consolidated_tools()
    return get_all_tools()


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a DAZZLE tool."""

    # Try consolidated tools first if enabled
    if use_consolidated_tools():
        result = await dispatch_consolidated_tool(name, arguments or {})
        if result is not None:
            return [TextContent(type="text", text=result)]

    # Dev mode tools (always handled directly)
    if name == "list_projects":
        result = list_projects()
    elif name == "select_project":
        result = select_project(arguments)
    elif name == "get_active_project":
        result = get_active_project_info()
    elif name == "validate_all_projects":
        result = validate_all_projects()

    # Semantic lookup tools (always available)
    elif name == "lookup_concept":
        result = lookup_concept_handler(arguments)
    elif name == "find_examples":
        result = find_examples_handler(arguments)
    elif name == "get_cli_help":
        result = get_cli_help_handler(arguments)
    elif name == "get_workflow_guide":
        result = get_workflow_guide_handler(arguments)
    elif name == "lookup_inference":
        result = lookup_inference_handler(arguments)
    elif name == "get_product_spec":
        explicit_path = arguments.get("project_path")
        if explicit_path:
            project_path: Path | None = resolve_project_path(explicit_path)
        else:
            project_path = get_active_project_path()
        if not project_path:
            result = json.dumps({"error": "No active project. Use select_project first."})
        else:
            result = get_product_spec_handler(project_path, arguments)

    # Internal/development tools
    elif name == "get_mcp_status":
        result = get_mcp_status_handler(arguments)
    elif name == "get_dnr_logs":
        result = get_dnr_logs_handler(arguments)

    # Infrastructure check tool (no project context needed)
    elif name == "check_test_infrastructure":
        result = check_test_infrastructure_handler()

    # Feedback tools (always available, no project context needed)
    elif name == "add_feedback":
        result = handle_add_feedback(arguments, get_project_root())
    elif name == "list_feedback":
        result = handle_list_feedback(arguments, get_project_root())

    # API Knowledgebase tools (always available)
    elif name == "list_api_packs":
        result = list_api_packs_handler(arguments)
    elif name == "search_api_packs":
        result = search_api_packs_handler(arguments)
    elif name == "get_api_pack":
        result = get_api_pack_handler(arguments)
    elif name == "generate_service_dsl":
        result = generate_service_dsl_handler(arguments)
    elif name == "get_env_vars_for_packs":
        result = get_env_vars_for_packs_handler(arguments)

    # DNR tools (always available)
    elif name in DNR_TOOL_NAMES:
        result = handle_dnr_tool(name, arguments)

    # Story/Behaviour Layer tools (require project context)
    elif name in (
        "get_dsl_spec",
        "propose_stories_from_dsl",
        "save_stories",
        "get_stories",
        "generate_story_stubs",
        "generate_tests_from_stories",
        # Demo Data Blueprint tools
        "propose_demo_blueprint",
        "save_demo_blueprint",
        "get_demo_blueprint",
        "generate_demo_data",
        # UX Coverage Test Design tools
        "propose_persona_tests",
        "get_test_gaps",
        "save_test_designs",
        "get_test_designs",
        # Event-First Architecture tools (Phase H)
        "extract_semantics",
        "validate_events",
        "infer_tenancy",
        "infer_compliance",
        "infer_analytics",
        # ProcessSpec and coverage tools (Phase 7)
        "stories_coverage",
        "propose_processes_from_stories",
        "list_processes",
        "inspect_process",
        "list_process_runs",
        "get_process_run",
        "get_process_diagram",
    ):
        # Try to resolve project path from arguments or state
        explicit_path = arguments.get("project_path") if arguments else None
        try:
            project_path = resolve_project_path(explicit_path)
        except ValueError as e:
            result = json.dumps({"error": str(e)})
            return [TextContent(type="text", text=result)]

        if project_path is None:
            if is_dev_mode():
                result = json.dumps(
                    {
                        "error": "No project selected. Use 'select_project' to choose one, or pass 'project_path' directly.",
                        "available_projects": list(get_available_projects().keys()),
                    }
                )
            else:
                result = json.dumps(
                    {
                        "error": "No dazzle.toml found in project root",
                        "project_root": str(get_project_root()),
                    }
                )
        else:
            if name == "get_dsl_spec":
                result = get_dsl_spec_handler(project_path, arguments)
            elif name == "propose_stories_from_dsl":
                result = propose_stories_from_dsl_handler(project_path, arguments)
            elif name == "save_stories":
                result = save_stories_handler(project_path, arguments)
            elif name == "get_stories":
                result = get_stories_handler(project_path, arguments)
            elif name == "generate_story_stubs":
                result = generate_story_stubs_handler(project_path, arguments)
            elif name == "generate_tests_from_stories":
                result = generate_tests_from_stories_handler(project_path, arguments)
            # Demo Data Blueprint tools
            elif name == "propose_demo_blueprint":
                result = propose_demo_blueprint_handler(project_path, arguments)
            elif name == "save_demo_blueprint":
                result = save_demo_blueprint_handler(project_path, arguments)
            elif name == "get_demo_blueprint":
                result = get_demo_blueprint_handler(project_path, arguments)
            elif name == "generate_demo_data":
                result = generate_demo_data_handler(project_path, arguments)
            # UX Coverage Test Design tools
            elif name == "propose_persona_tests":
                result = propose_persona_tests_handler(project_path, arguments)
            elif name == "get_test_gaps":
                result = get_test_gaps_handler(project_path, arguments)
            elif name == "save_test_designs":
                result = save_test_designs_handler(project_path, arguments)
            elif name == "get_test_designs":
                result = get_test_designs_handler(project_path, arguments)
            elif name == "get_coverage_actions":
                result = get_coverage_actions_handler(project_path, arguments)
            elif name == "get_runtime_coverage_gaps":
                result = get_runtime_coverage_gaps_handler(project_path, arguments)
            elif name == "save_runtime_coverage":
                result = save_runtime_coverage_handler(project_path, arguments)
            # Event-First Architecture tools (Phase H)
            elif name == "extract_semantics":
                result = handle_extract_semantics(arguments, project_path)
            elif name == "validate_events":
                result = handle_validate_events(arguments, project_path)
            elif name == "infer_tenancy":
                result = handle_infer_tenancy(arguments, project_path)
            elif name == "infer_compliance":
                result = handle_infer_compliance(arguments, project_path)
            elif name == "infer_analytics":
                result = handle_infer_analytics(arguments, project_path)
            # ProcessSpec and coverage tools (Phase 7)
            elif name == "stories_coverage":
                result = stories_coverage_handler(project_path, arguments)
            elif name == "propose_processes_from_stories":
                result = propose_processes_handler(project_path, arguments)
            elif name == "list_processes":
                result = list_processes_handler(project_path, arguments)
            elif name == "inspect_process":
                result = inspect_process_handler(project_path, arguments)
            elif name == "list_process_runs":
                result = list_process_runs_handler(project_path, arguments)
            elif name == "get_process_run":
                result = get_process_run_handler(project_path, arguments)
            elif name == "get_process_diagram":
                result = get_process_diagram_handler(project_path, arguments)
            else:
                result = json.dumps({"error": f"Unknown tool: {name}"})

    # Project tools - support explicit project_path or fall back to active project
    elif name in (
        "validate_dsl",
        "list_modules",
        "inspect_entity",
        "inspect_surface",
        "build",
        "analyze_patterns",
        "lint_project",
        # SiteSpec tools
        "get_sitespec",
        "validate_sitespec",
        "scaffold_site",
        # DSL Test tools (v0.18.0)
        "generate_dsl_tests",
        "run_dsl_tests",
        "get_dsl_test_coverage",
        "list_dsl_tests",
        # E2E Test tools (v0.19.0)
        "run_e2e_tests",
        "run_agent_e2e_tests",
        "get_e2e_test_coverage",
        "list_e2e_flows",
        # User Feedback tools (Dazzle Bar)
        "list_user_feedback",
        "get_user_feedback",
        "update_user_feedback",
        "get_user_feedback_summary",
    ):
        # Try to resolve project path from arguments or state
        explicit_path = arguments.get("project_path") if arguments else None
        try:
            project_path = resolve_project_path(explicit_path)
        except ValueError as e:
            result = json.dumps({"error": str(e)})
            return [TextContent(type="text", text=result)]

        if project_path is None:
            if is_dev_mode():
                result = json.dumps(
                    {
                        "error": "No project selected. Use 'list_projects' to see available projects, 'select_project' to choose one, or pass 'project_path' directly.",
                        "available_projects": list(get_available_projects().keys()),
                        "hint": "You can also pass project_path='/path/to/your/project' to any project tool.",
                    }
                )
            else:
                result = json.dumps(
                    {
                        "error": "No dazzle.toml found in project root",
                        "project_root": str(get_project_root()),
                        "hint": "Pass project_path='/path/to/your/project' to specify a different project.",
                    }
                )
        else:
            if name == "validate_dsl":
                result = validate_dsl(project_path)
            elif name == "list_modules":
                result = list_modules(project_path)
            elif name == "inspect_entity":
                result = inspect_entity(project_path, arguments)
            elif name == "inspect_surface":
                result = inspect_surface(project_path, arguments)
            elif name == "analyze_patterns":
                result = analyze_patterns(project_path)
            elif name == "lint_project":
                result = lint_project(project_path, arguments)
            # SiteSpec tools
            elif name == "get_sitespec":
                result = get_sitespec_handler(project_path, arguments)
            elif name == "validate_sitespec":
                result = validate_sitespec_handler(project_path, arguments)
            elif name == "scaffold_site":
                result = scaffold_site_handler(project_path, arguments)
            # DSL Test tools (v0.18.0)
            elif name == "generate_dsl_tests":
                result = generate_dsl_tests_handler(project_path, arguments)
            elif name == "run_dsl_tests":
                result = run_dsl_tests_handler(project_path, arguments)
            elif name == "get_dsl_test_coverage":
                result = get_dsl_test_coverage_handler(project_path, arguments)
            elif name == "list_dsl_tests":
                result = list_dsl_tests_handler(project_path, arguments)
            # E2E Test tools (v0.19.0)
            elif name == "run_e2e_tests":
                result = run_e2e_tests_handler(
                    project_path=str(project_path),
                    priority=arguments.get("priority"),
                    tag=arguments.get("tag"),
                    headless=arguments.get("headless", True),
                )
            elif name == "run_agent_e2e_tests":
                result = run_agent_e2e_tests_handler(
                    project_path=str(project_path),
                    test_id=arguments.get("test_id"),
                    headless=arguments.get("headless", True),
                    model=arguments.get("model"),
                )
            elif name == "get_e2e_test_coverage":
                result = get_e2e_test_coverage_handler(
                    project_path=str(project_path),
                )
            elif name == "list_e2e_flows":
                result = list_e2e_flows_handler(
                    project_path=str(project_path),
                    priority=arguments.get("priority"),
                    tag=arguments.get("tag"),
                    limit=arguments.get("limit", 20),
                )
            elif name == "get_test_tier_guidance":
                result = get_test_tier_guidance_handler(arguments)
            # User Feedback tools (Dazzle Bar)
            elif name == "list_user_feedback":
                import asyncio

                result = json.dumps(
                    asyncio.get_event_loop().run_until_complete(
                        list_feedback_handler(
                            status=arguments.get("status"),
                            category=arguments.get("category"),
                            limit=arguments.get("limit", 20),
                            project_path=str(project_path),
                        )
                    )
                )
            elif name == "get_user_feedback":
                import asyncio

                feedback_id = arguments.get("feedback_id")
                if not feedback_id:
                    return [TextContent(type="text", text="Error: feedback_id is required")]
                result = json.dumps(
                    asyncio.get_event_loop().run_until_complete(
                        get_feedback_handler(
                            feedback_id=feedback_id,
                            project_path=str(project_path),
                        )
                    )
                )
            elif name == "update_user_feedback":
                import asyncio

                feedback_id = arguments.get("feedback_id")
                status = arguments.get("status")
                if not feedback_id or not status:
                    return [
                        TextContent(type="text", text="Error: feedback_id and status are required")
                    ]
                result = json.dumps(
                    asyncio.get_event_loop().run_until_complete(
                        update_feedback_handler(
                            feedback_id=feedback_id,
                            status=status,
                            notes=arguments.get("notes"),
                            project_path=str(project_path),
                        )
                    )
                )
            elif name == "get_user_feedback_summary":
                import asyncio

                result = json.dumps(
                    asyncio.get_event_loop().run_until_complete(
                        get_feedback_summary_handler(
                            project_path=str(project_path),
                        )
                    )
                )
            else:
                result = json.dumps({"error": f"Unknown tool: {name}"})
    else:
        result = json.dumps({"error": f"Unknown tool: {name}"})

    return [TextContent(type="text", text=result)]


# ============================================================================
# Resource Handlers
# ============================================================================


@server.list_resources()  # type: ignore[no-untyped-call]
async def list_resources() -> list[Resource]:
    """List available DAZZLE resources."""
    resources = []

    # Add documentation resources (always available)
    resources.append(
        Resource(
            uri=AnyUrl("dazzle://docs/glossary"),
            name="DAZZLE Glossary (v0.2)",
            description="Definitions of DAZZLE v0.2 terms (surface, persona, workspace, attention signals, etc.)",
            mimeType="text/markdown",
        )
    )

    resources.append(
        Resource(
            uri=AnyUrl("dazzle://docs/quick-reference"),
            name="DAZZLE Quick Reference",
            description="DSL syntax quick reference with examples",
            mimeType="text/markdown",
        )
    )

    resources.append(
        Resource(
            uri=AnyUrl("dazzle://docs/dsl-reference"),
            name="DAZZLE DSL Reference (v0.2)",
            description="Complete DSL v0.2 reference documentation with UX semantic layer",
            mimeType="text/markdown",
        )
    )

    resources.append(
        Resource(
            uri=AnyUrl("dazzle://semantics/index"),
            name="DAZZLE Semantic Concept Index (v0.2)",
            description="Structured index of all DSL v0.2 concepts with definitions, syntax, and examples",
            mimeType="application/json",
        )
    )

    resources.append(
        Resource(
            uri=AnyUrl("dazzle://examples/catalog"),
            name="Example Projects Catalog",
            description="Catalog of example projects with metadata about features they demonstrate",
            mimeType="application/json",
        )
    )

    resources.append(
        Resource(
            uri=AnyUrl("dazzle://docs/context"),
            name="DAZZLE Context",
            description="Quick reference context for Claude - key concepts, tools, and common workflows",
            mimeType="text/markdown",
        )
    )

    resources.append(
        Resource(
            uri=AnyUrl("dazzle://docs/patterns"),
            name="DSL Patterns",
            description="Common DSL patterns with copy-paste examples (CRUD, dashboard, role-based access, etc.)",
            mimeType="application/json",
        )
    )

    resources.append(
        Resource(
            uri=AnyUrl("dazzle://docs/workflows"),
            name="Workflow Guides",
            description="Step-by-step guides for common tasks (getting_started, add_entity, add_workspace, etc.)",
            mimeType="application/json",
        )
    )

    # Add project-specific resources if we have an active project
    project_path = get_active_project_path()
    if project_path and (project_path / "dazzle.toml").exists():
        project_resources = create_resources(project_path)
        resources.extend(
            [
                Resource(
                    uri=r["uri"],
                    name=r["name"],
                    description=r["description"],
                    mimeType=r.get("mimeType", "text/plain"),
                )
                for r in project_resources
            ]
        )

    return resources


@server.read_resource()  # type: ignore[no-untyped-call]
async def read_resource(uri: str) -> str:
    """Read a DAZZLE resource by URI."""

    # Documentation resources
    if uri == "dazzle://docs/glossary":
        return get_glossary()

    elif uri == "dazzle://docs/quick-reference":
        docs_dir = Path(__file__).parent.parent.parent.parent / "docs"
        quick_ref = docs_dir / "DAZZLE_DSL_QUICK_REFERENCE.md"
        if quick_ref.exists():
            return quick_ref.read_text()
        return "Quick reference not found"

    elif uri == "dazzle://docs/dsl-reference":
        docs_dir = Path(__file__).parent.parent.parent.parent / "docs"
        dsl_ref = docs_dir / "v0.2" / "DAZZLE_DSL_REFERENCE.md"
        if dsl_ref.exists():
            return dsl_ref.read_text()
        return "DSL reference not found"

    # Semantic resources
    elif uri == "dazzle://semantics/index":
        return json.dumps(get_semantic_index(), indent=2)

    # Example resources
    elif uri == "dazzle://examples/catalog":
        return json.dumps(get_example_metadata(), indent=2)

    # Context and pattern resources
    elif uri == "dazzle://docs/context":
        from dazzle.mcp.prompts import get_dazzle_context

        return get_dazzle_context()

    elif uri == "dazzle://docs/patterns":
        return json.dumps(get_dsl_patterns(), indent=2)

    elif uri == "dazzle://docs/workflows":
        from dazzle.mcp.cli_help import get_workflow_guide

        workflows = [
            "getting_started",
            "new_project",
            "add_entity",
            "add_workspace",
            "add_personas",
            "add_relationships",
            "add_attention_signals",
            "setup_testing",
            "troubleshoot",
        ]
        result = {name: get_workflow_guide(name) for name in workflows}
        return json.dumps(result, indent=2)

    # Project resources
    elif uri.startswith("dazzle://project/"):
        project_path = get_active_project_path()
        if not project_path:
            return json.dumps({"error": "No active project"})

        if uri == "dazzle://project/manifest":
            manifest_path = project_path / "dazzle.toml"
            if manifest_path.exists():
                return manifest_path.read_text()
            return "Manifest not found"

        elif uri == "dazzle://modules":
            return list_modules(project_path)

        elif uri == "dazzle://entities":
            return get_entities(project_path)

        elif uri == "dazzle://surfaces":
            return get_surfaces(project_path)

    elif uri.startswith("dazzle://dsl/"):
        project_path = get_active_project_path()
        if not project_path:
            return json.dumps({"error": "No active project"})

        # Extract file path from URI
        file_path = uri.replace("dazzle://dsl/", "")
        dsl_file = project_path / file_path
        if dsl_file.exists():
            return dsl_file.read_text()
        return f"DSL file not found: {file_path}"

    return f"Unknown resource: {uri}"


# ============================================================================
# Prompt Handlers
# ============================================================================


@server.list_prompts()  # type: ignore[no-untyped-call]
async def list_prompts() -> list[dict[str, Any]]:
    """List available DAZZLE prompts."""
    from dazzle.mcp.prompts import create_prompts

    return create_prompts()


@server.get_prompt()  # type: ignore[no-untyped-call]
async def get_prompt(name: str, arguments: dict[str, str] | None = None) -> str:
    """Get a DAZZLE prompt by name."""
    args = arguments or {}

    if name == "validate":
        return """Please validate the DAZZLE project:

1. Use the validate_dsl tool to check for syntax errors
2. Report any validation errors found
3. If valid, summarize the project structure (modules, entities, surfaces)"""

    elif name == "review_dsl":
        aspect = args.get("aspect", "all")
        return f"""Please review the DAZZLE DSL focusing on: {aspect}

1. Read the DSL files using the dazzle://dsl/* resources
2. Analyze the design based on DAZZLE best practices
3. Check for:
   - Proper entity/surface naming conventions
   - CRUD pattern completeness
   - Appropriate use of personas and UX semantics
   - Security considerations (if aspect=security or all)
   - Performance implications (if aspect=performance or all)
4. Suggest specific improvements with examples"""

    elif name == "code_review":
        stack = args.get("stack", "django_micro_modular")
        return f"""Please review the generated code for stack: {stack}

1. Use the build tool to generate code if not already built
2. Examine the generated code in build/{stack}/
3. Check for:
   - Code quality and best practices
   - Security vulnerabilities
   - Performance issues
   - Proper error handling
4. Suggest improvements"""

    elif name == "suggest_surfaces":
        entity_name = args.get("entity_name", "")
        if not entity_name:
            return "Error: entity_name argument required"

        return f"""Please suggest surface definitions for the {entity_name} entity:

1. Use inspect_entity to examine the {entity_name} entity
2. Determine appropriate CRUD surfaces needed
3. Suggest UX semantics for each surface:
   - Purpose statement
   - Information needs (show, sort, filter, search)
   - Attention signals if applicable
   - Persona variants if needed
4. Provide complete DSL code for the suggested surfaces"""

    elif name == "optimize_dsl":
        return """Please analyze the DSL and suggest optimizations:

1. Use analyze_patterns to detect CRUD and integration patterns
2. Look for:
   - Incomplete CRUD patterns
   - Redundant surface definitions
   - Missing persona variants
   - Opportunities for workspaces
   - Better use of UX semantics
3. Suggest specific DSL improvements with before/after examples"""

    elif name == "getting_started":
        return """Help the user get started with DAZZLE:

1. Use get_workflow_guide("getting_started") to get the complete guide
2. Walk them through:
   - Creating a new project with `dazzle init`
   - Understanding the project structure
   - Writing their first entity and surface in DSL
   - Running with `dazzle dnr serve`
3. Offer to help them customize the starter code for their use case
4. Point them to lookup_concept("patterns") for common patterns they can use"""

    return f"Unknown prompt: {name}"


# ============================================================================
# Server Entry Point
# ============================================================================


async def run_server(project_root: Path | None = None) -> None:
    """Run the DAZZLE MCP server."""
    if project_root:
        set_project_root(project_root)
        logger.info(f"Project root set to: {project_root}")
    else:
        logger.info(f"Using default project root: {get_project_root()}")

    # Initialize dev mode detection
    init_dev_mode(get_project_root())

    if is_dev_mode():
        logger.info(f"Running in DEV MODE with {len(get_available_projects())} example projects")
        logger.info(f"Available projects: {list(get_available_projects().keys())}")
        from .state import get_active_project

        logger.info(f"Active project: {get_active_project()}")
    else:
        logger.info("Running in NORMAL MODE")

    logger.info("Starting DAZZLE MCP server...")
    try:
        async with stdio_server() as (read_stream, write_stream):
            logger.info("stdio transport established, running server...")
            await server.run(read_stream, write_stream, server.create_initialization_options())
    except Exception as e:
        logger.exception(f"Server error: {e}")
        raise


# For backwards compatibility
class DazzleMCPServer:
    """Legacy wrapper for the MCP server."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    async def run(self) -> None:
        await run_server(self.project_root)


# Export key items
__all__ = [
    "server",
    "run_server",
    "DazzleMCPServer",
    "set_project_root",
    "get_project_root",
    "is_dev_mode",
    "get_active_project_path",
    "init_dev_mode",
    "call_tool",
    "list_tools_handler",
]
