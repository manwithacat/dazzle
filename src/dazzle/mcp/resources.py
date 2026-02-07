"""
Resource definitions for DAZZLE MCP server.

Resources are data sources that Claude Code can reference using @server:uri syntax.
"""

from pathlib import Path
from typing import Any


def create_static_resources() -> list[dict[str, Any]]:
    """
    Create static resources that are always available (not project-specific).

    Returns:
        List of static resource definitions
    """
    return [
        {
            "uri": "dazzle://docs/context",
            "name": "DAZZLE Context",
            "description": "Quick reference context for Claude - key concepts, tools, and common workflows",
            "mimeType": "text/markdown",
        },
        {
            "uri": "dazzle://docs/patterns",
            "name": "DSL Patterns",
            "description": "Common DSL patterns with copy-paste examples (CRUD, dashboard, role-based access, etc.)",
            "mimeType": "application/json",
        },
        {
            "uri": "dazzle://docs/workflows",
            "name": "Workflow Guides",
            "description": "Step-by-step guides for common tasks (getting_started, add_entity, add_workspace, etc.)",
            "mimeType": "application/json",
        },
        {
            "uri": "dazzle://docs/htmx-templates",
            "name": "HTMX Template Specification",
            "description": "HTMX template patterns, fragment contracts, and LLM cognition strategies for rich UI development",
            "mimeType": "text/markdown",
        },
        {
            "uri": "dazzle://docs/runtime-capabilities",
            "name": "Runtime UI Capabilities",
            "description": "What the runtime renders for each DSL construct: DataTable sort/filter/search, attention signals, persona variants, form widgets",
            "mimeType": "text/markdown",
        },
        {
            "uri": "dazzle://user/profile",
            "name": "User Profile",
            "description": "Adaptive user profile with scored dimensions (technical depth, domain clarity, UX focus) and LLM guidance for adjusting communication register",
            "mimeType": "application/json",
        },
    ]


def create_resources(project_root: Path) -> list[dict[str, Any]]:
    """
    Create available resources for the MCP server.

    Args:
        project_root: Path to the DAZZLE project root

    Returns:
        List of resource definitions with URI, name, and description
    """
    # Project-specific resources only (static resources are added by the server)
    resources: list[dict[str, Any]] = [
        {
            "uri": "dazzle://project/manifest",
            "name": "Project Manifest",
            "description": "dazzle.toml project configuration",
            "mimeType": "text/plain",
        },
        {
            "uri": "dazzle://modules",
            "name": "Project Modules",
            "description": "List of all modules and their dependencies",
            "mimeType": "application/json",
        },
        {
            "uri": "dazzle://entities",
            "name": "Project Entities",
            "description": "All entity definitions in the project",
            "mimeType": "application/json",
        },
        {
            "uri": "dazzle://surfaces",
            "name": "Project Surfaces",
            "description": "All surface definitions in the project",
            "mimeType": "application/json",
        },
    ]

    # Add DSL file resources
    dsl_dir = project_root / "dsl"
    if dsl_dir.exists():
        for dsl_file in dsl_dir.glob("**/*.dsl"):
            relative_path = dsl_file.relative_to(project_root)
            resources.append(
                {
                    "uri": f"dazzle://dsl/{relative_path}",
                    "name": f"DSL: {dsl_file.stem}",
                    "description": f"DSL file: {relative_path}",
                    "mimeType": "text/plain",
                }
            )

    return resources
