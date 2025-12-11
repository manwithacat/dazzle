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
from dazzle.mcp.examples import get_example_metadata
from dazzle.mcp.resources import create_resources
from dazzle.mcp.semantics import get_dsl_patterns, get_semantic_index

from .glossary import get_glossary
from .state import (
    get_active_project_path,
    get_available_projects,
    get_project_root,
    init_dev_mode,
    is_dev_mode,
    set_project_root,
)
from .tool_handlers import (
    analyze_patterns,
    find_examples_handler,
    get_active_project_info,
    get_cli_help_handler,
    get_entities,
    get_mcp_status_handler,
    get_surfaces,
    get_workflow_guide_handler,
    inspect_entity,
    inspect_surface,
    lint_project,
    list_modules,
    list_projects,
    lookup_concept_handler,
    lookup_inference_handler,
    select_project,
    validate_all_projects,
    validate_dsl,
)
from .tools import get_all_tools

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
    return get_all_tools()


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a DAZZLE tool."""

    # Dev mode tools
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

    # Internal/development tools
    elif name == "get_mcp_status":
        result = get_mcp_status_handler(arguments)

    # DNR tools (always available)
    elif name in DNR_TOOL_NAMES:
        result = handle_dnr_tool(name, arguments)

    # Project tools - require active project in dev mode
    elif name in (
        "validate_dsl",
        "list_modules",
        "inspect_entity",
        "inspect_surface",
        "build",
        "analyze_patterns",
        "lint_project",
    ):
        project_path = get_active_project_path()

        if project_path is None:
            if is_dev_mode():
                result = json.dumps(
                    {
                        "error": "No project selected. Use 'list_projects' to see available projects and 'select_project' to choose one.",
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
