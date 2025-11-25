"""
Resource definitions for DAZZLE MCP server.

Resources are data sources that Claude Code can reference using @server:uri syntax.
"""

from pathlib import Path
from typing import Any


def create_resources(project_root: Path) -> list[dict[str, Any]]:
    """
    Create available resources for the MCP server.

    Args:
        project_root: Path to the DAZZLE project root

    Returns:
        List of resource definitions with URI, name, and description
    """
    resources = [
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
