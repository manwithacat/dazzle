"""
DAZZLE MCP Server implementation.

Implements the Model Context Protocol for DAZZLE using the official MCP SDK,
exposing tools for DSL validation, inspection, and code generation.
"""

import json
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules
from dazzle.core.patterns import detect_crud_patterns, detect_integration_patterns

# Create the MCP server instance
server = Server("dazzle")

# Store project root (set during initialization)
_project_root: Path = Path.cwd()


def set_project_root(path: Path) -> None:
    """Set the project root for the server."""
    global _project_root
    _project_root = path


def get_project_root() -> Path:
    """Get the current project root."""
    return _project_root


# ============================================================================
# Tools
# ============================================================================


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available DAZZLE tools."""
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
            name="build",
            description="Build artifacts for specified stacks",
            inputSchema={
                "type": "object",
                "properties": {
                    "stacks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Stack names to build (default: django_micro_modular)",
                    }
                },
                "required": [],
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
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a DAZZLE tool."""
    project_root = get_project_root()

    if name == "validate_dsl":
        result = _validate_dsl(project_root)
    elif name == "list_modules":
        result = _list_modules(project_root)
    elif name == "inspect_entity":
        result = _inspect_entity(project_root, arguments)
    elif name == "inspect_surface":
        result = _inspect_surface(project_root, arguments)
    elif name == "build":
        result = _build(project_root, arguments)
    elif name == "analyze_patterns":
        result = _analyze_patterns(project_root)
    elif name == "lint_project":
        result = _lint_project(project_root, arguments)
    else:
        result = json.dumps({"error": f"Unknown tool: {name}"})

    return [TextContent(type="text", text=result)]


# ============================================================================
# Tool Implementations
# ============================================================================


def _validate_dsl(project_root: Path) -> str:
    """Validate DSL files in the project."""
    try:
        manifest = load_manifest(project_root)
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        return json.dumps(
            {
                "status": "valid",
                "modules": len(modules),
                "entities": len(app_spec.domain.entities),
                "surfaces": len(app_spec.surfaces),
                "services": len(app_spec.services),
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


def _list_modules(project_root: Path) -> str:
    """List all modules in the project."""
    try:
        manifest = load_manifest(project_root)
        dsl_files = discover_dsl_files(project_root, manifest)
        parsed_modules = parse_modules(dsl_files)

        modules = {}
        for idx, module in enumerate(parsed_modules):
            modules[module.name] = {
                "file": str(dsl_files[idx].relative_to(project_root)),
                "dependencies": module.uses,
            }

        return json.dumps(modules, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def _inspect_entity(project_root: Path, args: dict[str, Any]) -> str:
    """Inspect an entity definition."""
    entity_name = args.get("entity_name")
    if not entity_name:
        return json.dumps({"error": "entity_name required"})

    try:
        manifest = load_manifest(project_root)
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        entity = next((e for e in app_spec.domain.entities if e.name == entity_name), None)
        if not entity:
            return json.dumps({"error": f"Entity '{entity_name}' not found"})

        return json.dumps(
            {
                "name": entity.name,
                "description": entity.title,
                "fields": [
                    {
                        "name": f.name,
                        "type": str(f.type.kind),
                        "required": f.is_required,
                        "modifiers": [str(m) for m in f.modifiers],
                    }
                    for f in entity.fields
                ],
                "constraints": [str(c) for c in entity.constraints] if entity.constraints else [],
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def _inspect_surface(project_root: Path, args: dict[str, Any]) -> str:
    """Inspect a surface definition."""
    surface_name = args.get("surface_name")
    if not surface_name:
        return json.dumps({"error": "surface_name required"})

    try:
        manifest = load_manifest(project_root)
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        surface = next((s for s in app_spec.surfaces if s.name == surface_name), None)
        if not surface:
            return json.dumps({"error": f"Surface '{surface_name}' not found"})

        return json.dumps(
            {
                "name": surface.name,
                "entity": surface.entity_ref,
                "mode": str(surface.mode),
                "description": surface.title,
                "sections": len(surface.sections) if surface.sections else 0,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def _build(project_root: Path, args: dict[str, Any]) -> str:
    """Build artifacts for specified stacks."""
    stacks = args.get("stacks", ["django_micro_modular"])

    try:
        from dazzle.stacks import get_backend

        manifest = load_manifest(project_root)
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        results = {}
        output_dir = project_root / "build"
        output_dir.mkdir(exist_ok=True)

        for stack_name in stacks:
            try:
                stack = get_backend(stack_name)
                stack_output = output_dir / stack_name
                stack.generate(app_spec, stack_output)
                results[stack_name] = f"Built successfully in {stack_output}"
            except Exception as e:
                results[stack_name] = f"Error: {str(e)}"

        return json.dumps(results, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def _analyze_patterns(project_root: Path) -> str:
    """Analyze the project for patterns."""
    try:
        manifest = load_manifest(project_root)
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        crud_patterns = detect_crud_patterns(app_spec)
        integration_patterns = detect_integration_patterns(app_spec)

        return json.dumps(
            {
                "crud_patterns": [
                    {
                        "entity": p.entity_name,
                        "has_create": p.has_create,
                        "has_list": p.has_list,
                        "has_detail": p.has_detail,
                        "has_edit": p.has_edit,
                        "is_complete": p.is_complete,
                        "missing_operations": p.missing_operations,
                    }
                    for p in crud_patterns
                ],
                "integration_patterns": [
                    {
                        "name": p.integration_name,
                        "service": p.service_name,
                        "has_actions": p.has_actions,
                        "has_syncs": p.has_syncs,
                        "action_count": p.action_count,
                        "sync_count": p.sync_count,
                        "connected_entities": list(p.connected_entities or []),
                        "connected_surfaces": list(p.connected_surfaces or []),
                    }
                    for p in integration_patterns
                ],
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def _lint_project(project_root: Path, args: dict[str, Any]) -> str:
    """Run linting on the project."""
    extended = args.get("extended", False)

    try:
        manifest = load_manifest(project_root)
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        warnings, _ = lint_appspec(app_spec, extended=extended)

        return json.dumps(
            {"warnings": len(warnings), "issues": [str(w) for w in warnings]},
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


# ============================================================================
# Server Entry Point
# ============================================================================


async def run_server(project_root: Path | None = None) -> None:
    """Run the DAZZLE MCP server."""
    if project_root:
        set_project_root(project_root)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


# For backwards compatibility
class DazzleMCPServer:
    """Legacy wrapper for the MCP server."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    async def run(self) -> None:
        await run_server(self.project_root)
